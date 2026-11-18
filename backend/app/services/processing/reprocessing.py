"""Explicit repair plans and source-only corrections with dependency proofs."""

import copy
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import (
    question_input_hash,
    rules_manifest,
    sample_dependency_hash,
)
from app.module3.contracts import fingerprint, result_hash
from app.services.processing import orchestration as o
from app.services.processing import tasks
from app.services.processing import workflows as w


def ancestor_revision(db, revision, task):
    """A receipt may come only from the same workflow's actual ancestor chain."""
    if task.workflow_id != revision.workflow_id:
        return False
    current = revision
    while current:
        if current.id == task.revision_id:
            return True
        current = (
            db.get(m.ProcessingWorkflowRevision, current.parent_revision_id)
            if current.parent_revision_id
            else None
        )
    return False


def context(db, workflow_id, payload, settings, *, allow_source=False):
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if workflow.processing_state in {
        "queued",
        "running",
        "stopping",
    } or workflow.publication_state in {
        "preparing",
        "pending_batch",
        "validating",
        "activating",
    }:
        raise w.conflict("WORKFLOW_BUSY", "请先等待或停止当前操作")
    stage = (
        "final"
        if revision.final_result_hash
        else "source"
        if allow_source
        else "sample"
        if "sample" in revision.stage_fingerprints
        else "final"
    )
    content, _ = o.stage_payload(db, revision, stage, settings)
    if result_hash(content) != payload.expected_result_hash:
        raise w.conflict("ARTIFACT_CHANGED", "父结果身份变化")
    return workflow, revision, content


def build_plan(db, revision, content, selected, feedback):
    questions = {q["_src_id"]: q for q in content["questions"]}
    if len(selected) != len(set(selected)) or not set(selected) <= questions.keys():
        raise w.conflict("VERSION_CONFLICT", "修复题目不存在或重复")
    manifest = rules_manifest()
    method_same = manifest == revision.rules_manifest
    # Shared method changes invalidate every candidate and the sample gate.
    affected = set(selected) if method_same else set(questions)
    if not revision.final_result_hash:
        # A sample contains source for the whole paper, but receipts for at most
        # five questions. Unattempted questions cannot be declared reusable.
        generated = {
            r["question_src_id"] for r in content.get("generation_receipts", [])
        }
        affected |= set(questions) - generated
    sample_ids = {q["_src_id"] for q in content["questions"][:5]}
    projection = revision.stage_fingerprints.get("sample")
    approval = db.scalar(
        select(m.ProcessingStageApproval)
        .where(
            m.ProcessingStageApproval.revision_id == revision.id,
            m.ProcessingStageApproval.stage == "sample",
        )
        .order_by(
            m.ProcessingStageApproval.created_at.desc(),
            m.ProcessingStageApproval.id.desc(),
        )
        .limit(1)
    )
    sample_valid = bool(
        method_same
        and not affected & sample_ids
        and projection
        and approval
        and approval.decision == "approved"
        and approval.dependency_hash == projection["dependency_hash"]
        and projection["dependency_hash"] == sample_dependency_hash(content, manifest)
    )
    if not sample_valid:
        affected |= sample_ids
    plan = {
        "parent_revision_id": str(revision.id),
        "parent_result_hash": revision.final_result_hash or result_hash(content),
        "selected_question_ids": sorted(selected),
        "affected_question_ids": sorted(affected),
        "reusable_question_ids": sorted(set(questions) - affected),
        "sample_valid": sample_valid,
        "sample_dependency_hash": sample_dependency_hash(content, manifest),
        "sample_approval_id": str(approval.id) if sample_valid else None,
        "rules_manifest_hash": manifest["manifest_hash"],
        "feedback": feedback,
        "generation_count": len(affected),
        "review_count": len(questions),
        "cost_scope": "persistent audio-wide ledger, including retries",
        "invalidated_approvals": ["final"] + ([] if sample_valid else ["sample"]),
    }
    return {**plan, "plan_hash": fingerprint(plan)}


def preview(db, workflow_id, payload, settings):
    _, revision, content = context(db, workflow_id, payload, settings)
    return build_plan(db, revision, content, payload.question_src_ids, payload.feedback)


def child_revision(db, workflow, parent, user_id, reason):
    # Material copying is shared with ordinary child revisions, but no intermediate
    # command/commit is created: repair and pointer switch form one transaction.
    revision = w.copy_revision(
        db,
        workflow,
        parent,
        user_id,
        reason,
        parent.document_mode,
        parent.listening_pages,
    )
    revision.materials_manifest = copy.deepcopy(parent.materials_manifest)
    revision.materials_hash = parent.materials_hash
    revision.materials_frozen_at = db.scalar(select(func.now()))
    revision.stage_fingerprints = {
        key: copy.deepcopy(value)
        for key, value in parent.stage_fingerprints.items()
        if key in {"align", "source"}
    }
    return revision


def clone_sample_gate(db, revision, parent, plan, user_id):
    original = db.get(m.ProcessingStageApproval, UUID(plan["sample_approval_id"]))
    revision.stage_fingerprints = {
        **revision.stage_fingerprints,
        "sample": copy.deepcopy(parent.stage_fingerprints["sample"]),
    }
    db.add(
        m.ProcessingStageApproval(
            id=uuid4(),
            revision_id=revision.id,
            stage="sample",
            artifact_hash=original.artifact_hash,
            dependency_hash=plan["sample_dependency_hash"],
            decision="approved",
            items={"reused_items": original.items, "dependency_proof": plan},
            operator_user_id=user_id,
            reused_approval_id=original.id,
        )
    )


def execute(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "reprocess", key, workflow_id, payload
    )
    if old:
        return old
    workflow, parent, content = context(db, workflow_id, payload, settings)
    plan = build_plan(db, parent, content, payload.question_src_ids, payload.feedback)
    if payload.expected_plan_hash != plan["plan_hash"]:
        raise w.conflict("PLAN_CHANGED", "修复范围或方法变化，请重新预览", plan=plan)
    revision = child_revision(db, workflow, parent, user_id, payload.feedback)
    if plan["sample_valid"]:
        clone_sample_gate(db, revision, parent, plan, user_id)
    # This server-created control artifact cannot be supplied as a client result.
    stage = "annotate" if plan["sample_valid"] else "annotate_sample"
    task = o.queue_task(db, workflow, revision, stage, user_id, settings)
    task.request = {
        **task.request,
        "repair_plan": plan,
        "reuse_final_projection": parent.stage_fingerprints[
            "final" if parent.final_result_hash else "sample"
        ],
    }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials_hash": revision.materials_hash,
        }
    )
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "reprocess",
        key,
        digest,
        body,
        {
            "task_id": str(task.id),
            "stage": stage,
            "plan": plan,
            "row_version": workflow.row_version,
        },
        state="accepted",
    )


def correct_source(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "source_correction", key, workflow_id, payload
    )
    if old:
        return old
    workflow, parent, content = context(
        db, workflow_id, payload, settings, allow_source=True
    )
    source, source_projection = o.stage_payload(db, parent, "source", settings)
    corrected = copy.deepcopy(source)
    questions = {q["_src_id"]: q for q in corrected["questions"]}
    seen = set()
    for change in payload.changes:
        question = questions.get(change.question_src_id)
        field = (change.question_src_id, change.field)
        material = next(
            (
                v
                for v in parent.materials_manifest.values()
                if v["material_id"] == change.material_id
            ),
            None,
        )
        if (
            not question
            or field in seen
            or question.get(change.field) != change.expected_value
        ):
            raise w.conflict("VERSION_CONFLICT", "校正对象或前值不匹配")
        if (
            not material
            or material["kind"] not in {"paper", "answer"}
            or (material.get("pages") and change.page not in material["pages"])
        ):
            raise w.conflict("SOURCE_REQUIRED", "校正必须定位本修订有效原件页码")
        if change.field == "correct_option" and change.value not in (
            "A",
            "B",
            "C",
            "D",
        ):
            raise w.conflict("SOURCE_REQUIRED", "来源答案须为基准选项A—D")
        question[change.field] = change.value
        seen.add(field)
    changed = {
        q["_src_id"]
        for q in corrected["questions"]
        if question_input_hash(
            source, next(x for x in source["questions"] if x["_src_id"] == q["_src_id"])
        )
        != question_input_hash(corrected, q)
    }
    if not changed:
        raise w.conflict("SOURCE_REQUIRED", "校正没有改变任何来源内容")
    plan = build_plan(db, parent, content, sorted(changed), payload.reason)
    if not parent.final_result_hash:
        plan["affected_question_ids"] = [q["_src_id"] for q in content["questions"]]
        plan["reusable_question_ids"] = []
        plan["generation_count"] = len(content["questions"])
    # Recompute sample validity against the corrected inputs as well.
    plan["sample_valid"] = plan["sample_valid"] and sample_dependency_hash(
        corrected, rules_manifest()
    ) == sample_dependency_hash(content, rules_manifest())
    revision = child_revision(db, workflow, parent, user_id, payload.reason)
    stage = "annotate" if plan["sample_valid"] else "annotate_sample"
    plan["plan_hash"] = fingerprint({k: v for k, v in plan.items() if k != "plan_hash"})
    corrected["rules_manifest"] = revision.rules_manifest
    task = o.queue_task(db, workflow, revision, stage, user_id, settings)
    from app.module3.workflow_worker import record_artifact

    artifact = record_artifact(db, None, task, "source", corrected, settings)
    revision.stage_fingerprints = {
        **revision.stage_fingerprints,
        "source": {
            "task_id": str(task.id),
            "artifact_id": artifact.id,
            "artifact_hash": artifact.artifact_hash,
            "dependency_hash": fingerprint(
                {
                    "content": artifact.artifact_hash,
                    "materials": revision.materials_hash,
                    "rules": revision.rules_manifest["manifest_hash"],
                }
            ),
        },
    }
    if plan["sample_valid"]:
        clone_sample_gate(db, revision, parent, plan, user_id)
    # A source change always returns to an explicit source confirmation first.
    task.state, task.stage = "awaiting_confirmation", "source"
    workflow.processing_state = "awaiting_source"
    task.request = {
        **task.request,
        "repair_plan": plan,
        **(
            {"reuse_final_projection": parent.stage_fingerprints["final"]}
            if parent.final_result_hash
            else {}
        ),
    }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials_hash": revision.materials_hash,
        }
    )
    db.add(
        p.ProcessingCorrection(
            task_id=task.id,
            parent_task_id=parent.final_task_id or UUID(source_projection["task_id"]),
            before_hash=result_hash(source),
            after_hash=result_hash(corrected),
            before_payload=source,
            after_payload=corrected,
            changes=[change.model_dump() for change in payload.changes],
            reason=payload.reason,
            source_refs=[
                {"material_id": c.material_id, "page": c.page, "locator": c.locator}
                for c in payload.changes
            ],
            operator_user_id=user_id,
        )
    )
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "source_correction",
        key,
        digest,
        body,
        {
            "task_id": str(task.id),
            "stage": "source",
            "plan": plan,
            "row_version": workflow.row_version,
        },
    )


def correct_alignment(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "alignment_correction", key, workflow_id, payload
    )
    if old:
        return old
    workflow, parent = w.locked_current(db, workflow_id, payload)
    if workflow.processing_state in {
        "queued",
        "running",
        "stopping",
    } or workflow.publication_state in {
        "preparing",
        "pending_batch",
        "validating",
        "activating",
    }:
        raise w.conflict("WORKFLOW_BUSY", "请先停止或等待当前处理/发布操作")
    projection = parent.stage_fingerprints.get("align")
    if (
        not projection
        or projection["artifact_hash"] != payload.expected_alignment_artifact_hash
    ):
        raise w.conflict("VERSION_CONFLICT", "对齐前值身份已变化")
    rows = [segment.model_dump(mode="json") for segment in payload.reference_segments]
    if len({row["segment_id"] for row in rows}) != len(rows):
        raise w.conflict("SOURCE_REQUIRED", "校正后的原文句身份不能重复")
    for row in rows:
        material = next(
            (
                db.get(p.MaterialSource, v["material_id"])
                for v in parent.materials_manifest.values()
                if v["sha256"] == row["source_sha256"] and v["kind"] == "answer"
            ),
            None,
        )
        if not material or material.storage_key != row["source_storage_key"]:
            raise w.conflict("SOURCE_REQUIRED", "校正后的逐句原文须定位本修订答案原件")
        tasks.verify_material(material, settings)
        selected_pages = parent.listening_pages.get("answer", [])
        if selected_pages and not set(row["source_pages"]) <= set(selected_pages):
            raise w.conflict("SOURCE_REQUIRED", "逐句原文页码不在已选择来源内")
    source_task = tasks.get_task(db, UUID(projection["task_id"]))
    reference = db.scalar(
        select(p.ProcessingArtifact)
        .where(
            p.ProcessingArtifact.task_id == source_task.id,
            p.ProcessingArtifact.stage == "reference",
        )
        .order_by(p.ProcessingArtifact.id.desc())
        .limit(1)
    )
    before, _ = o.artifact_payload(db, reference.id, settings)
    if before.get("segments") == rows:
        raise w.conflict("SOURCE_REQUIRED", "未发生原文或对齐搜索范围变化")
    revision = child_revision(db, workflow, parent, user_id, payload.reason)
    revision.stage_fingerprints = {}
    task = o.queue_task(db, workflow, revision, "align", user_id, settings)
    structure = before.get("trusted_question_structure")
    if not structure or structure.get("source") != "original_paper_question_headings":
        raise w.conflict("SOURCE_REQUIRED", "缺少原卷独立提取的题组来源，须先重新提取")
    task.request = {
        **task.request,
        "reference_preparation": "provided",
        "reference_segments": rows,
        "corrected_reference_structure": structure,
    }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials_hash": revision.materials_hash,
        }
    )
    db.add(
        p.ProcessingCorrection(
            task_id=task.id,
            parent_task_id=source_task.id,
            before_hash=fingerprint(before),
            after_hash=fingerprint({"segments": rows}),
            before_payload=before,
            after_payload={"segments": rows},
            changes={"kind": "source_reference_realignment"},
            reason=payload.reason,
            source_refs={"basis": payload.source_basis, "references": rows},
            operator_user_id=user_id,
        )
    )
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "alignment_correction",
        key,
        digest,
        body,
        {
            "task_id": str(task.id),
            "stage": "align",
            "row_version": workflow.row_version,
        },
        state="accepted",
    )
