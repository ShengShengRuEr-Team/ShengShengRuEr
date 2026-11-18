"""Explicit stage commands and durable gates shared by HTTP and the worker."""

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.core.errors import AppError
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.db.models_listening import ExamPaper
from app.module3.annotation_identity import materials_hash, rules_manifest
from app.module3.contracts import controlled_path, file_hash, fingerprint
from app.schemas_processing import TaskRequest
from app.services.processing import tasks, uploads
from app.services.processing import workflows as w

WAITING = {
    "align": "awaiting_alignment",
    "source": "awaiting_source",
    "sample": "awaiting_sample",
}
NEXT_STAGE = {"align": "assemble", "source": "annotate_sample", "sample": "annotate"}


def environment_ready(settings):
    return all(
        Path(value).is_file()
        for value in (settings.m3_asr_python, settings.m3_ocr_python)
        if value
    ) and bool(
        settings.m3_asr_python
        and settings.m3_ocr_python
        and settings.m3_path("m3_model_root").is_dir()
    )


def artifact_payload(db, artifact_id, settings):
    row = db.get(p.ProcessingArtifact, artifact_id)
    if not row:
        raise w.conflict("ARTIFACT_CHANGED", "阶段产物不存在")
    path = controlled_path(settings.m3_path("m3_artifacts_dir"), row.storage_key)
    if file_hash(path) != row.artifact_hash:
        raise w.conflict("ARTIFACT_CHANGED", "阶段产物完整性校验失败")
    return json.loads(path.read_text(encoding="utf-8")), row


def stage_payload(db, revision, stage, settings):
    projection = revision.stage_fingerprints.get(stage)
    if not projection:
        raise AppError(404, "该阶段尚无结果")
    content, row = artifact_payload(db, projection["artifact_id"], settings)
    if row.artifact_hash != projection["artifact_hash"]:
        raise w.conflict("ARTIFACT_CHANGED", "阶段引用不匹配")
    return content, projection


def queue_task(db, workflow, revision, stage, user_id, settings):
    if revision.rules_manifest["manifest_hash"] != rules_manifest()["manifest_hash"]:
        raise w.conflict("ARTIFACT_CHANGED", "生成方法已更新，请创建新修订后处理")
    rows = [uploads.selected_upload(db, revision.id, kind) for kind in w.MATERIAL_KINDS]
    if any(row is None or row.state != "ready" for row in rows):
        raise w.conflict("MATERIALS_REQUIRED", "三份当前材料须全部验证成功")
    materials = [db.get(p.MaterialSource, row.material_id) for row in rows]
    for material in materials:
        tasks.verify_material(material, settings)
    paper = (
        db.get(ExamPaper, workflow.exam_paper_id) if workflow.exam_paper_id else None
    )
    code = paper.exam_paper_code if paper else materials[0].exam_paper_code
    pages = {
        material.id: revision.listening_pages.get(kind, [])
        for kind, material in zip(w.MATERIAL_KINDS, materials, strict=True)
        if revision.listening_pages.get(kind)
    }
    request = {
        "exam_paper": {
            "exam_paper_code": code,
            **{
                k: getattr(workflow, k)
                for k in ("exam_level", "exam_year", "exam_month", "paper_set")
            },
        },
        "material_ids": [material.id for material in materials],
        "document_mode": revision.document_mode,
        "material_pages": pages,
        "text_source": "reference",
        "reference_preparation": "auto",
        "dictionary_snapshot_sha256": revision.rules_manifest["dictionary_sha256"],
        "profile_version": "M3-WIN64-1.1.0",
        "stop_after": "align",
    }
    if stage in {"annotate_sample", "annotate"}:
        source_task = tasks.get_task(
            db, UUID(revision.stage_fingerprints["source"]["task_id"])
        )
        request.update(
            {
                key: source_task.request[key]
                for key in (
                    "expected_question_count",
                    "expected_question_count_source",
                    "expected_question_ranges",
                )
            }
        )
    if stage == "assemble":
        aligned = revision.stage_fingerprints["align"]
        request.update(
            stop_after="assemble", reuse_alignment_task_id=aligned["task_id"]
        )
        source_task = tasks.get_task(db, UUID(aligned["task_id"]))
        source_artifact = db.scalar(
            select(p.ProcessingArtifact)
            .where(
                p.ProcessingArtifact.task_id == source_task.id,
                p.ProcessingArtifact.stage == "reference",
            )
            .order_by(p.ProcessingArtifact.id.desc())
            .limit(1)
        )
        reference, _ = artifact_payload(db, source_artifact.id, settings)
        structure = reference.get("trusted_question_structure", {})
        if (
            not structure
            or structure.get("source") != "original_paper_question_headings"
        ):
            raise w.conflict("SOURCE_REQUIRED", "缺少原卷独立提取的可信题量")
        request.update(
            expected_question_count=structure["question_count"],
            expected_question_count_source={
                "document": materials[0].storage_key,
                "sha256": materials[0].sha256,
                "locator": "original_paper_question_headings",
            },
            expected_question_ranges=[
                {k: group[k] for k in ("section", "start", "end")}
                for group in structure["groups"]
            ],
        )
    previous = (
        tasks.get_task(db, workflow.current_task_id)
        if workflow.current_task_id
        else None
    )
    task = tasks.create_task(db, TaskRequest.model_validate(request), user_id, settings)
    task.workflow_id, task.revision_id = workflow.id, revision.id
    task.parent_task_id = workflow.current_task_id
    task.method = {
        **task.method,
        "prompt_version": "m3.annotations.v7",
        "rule_version": "m3.checks.v3",
        "rules_manifest": revision.rules_manifest,
    }
    task.method_hash = fingerprint(task.method)
    task.request = {
        **task.request,
        "workflow_stage": stage,
        **{
            key: previous.request[key]
            for key in ("repair_plan", "reuse_final_projection")
            if previous and key in previous.request
        },
    }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials_hash": revision.materials_hash,
        }
    )
    workflow.current_task_id = task.id
    workflow.processing_state, workflow.updated_at = "queued", func.now()
    workflow.row_version += 1
    workflow.updated_by = user_id
    db.flush()
    return task


def start(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(db, user_id, "start", key, workflow_id, payload)
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if (
        revision.materials_frozen_at
        or workflow.processing_state != "awaiting_materials"
    ):
        raise w.conflict("VERSION_CONFLICT", "当前修订已开始，请查询已有操作")
    if not environment_ready(settings):
        raise w.conflict("ENVIRONMENT_BLOCKED", "处理/OCR环境或模型目录未配置")
    uploads.expire_uploads(db)
    rows = [uploads.selected_upload(db, revision.id, kind) for kind in w.MATERIAL_KINDS]
    if any(row is None or row.state != "ready" for row in rows):
        raise w.conflict("MATERIALS_REQUIRED", "三份当前材料须全部验证成功")
    manifest = [
        {
            "kind": row.kind,
            "sha256": row.actual_sha256,
            "material_id": row.material_id,
            "upload_id": str(row.id),
            "pages": revision.listening_pages.get(row.kind, []),
        }
        for row in rows
    ]
    revision.materials_manifest = {row["kind"]: row for row in manifest}
    revision.materials_hash = materials_hash(
        [
            {k: v for k, v in row.items() if k not in {"material_id", "upload_id"}}
            for row in manifest
        ],
        revision.document_mode,
    )
    revision.materials_frozen_at = db.scalar(select(func.now()))
    task = queue_task(db, workflow, revision, "align", user_id, settings)
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "start",
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


def approve_stage(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "stage_approval", key, workflow_id, payload
    )
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if workflow.processing_state != WAITING[payload.stage]:
        raise w.conflict("VERSION_CONFLICT", "当前不在该阶段确认点")
    content, projection = stage_payload(db, revision, payload.stage, settings)
    if payload.stage == "source" and payload.decision == "approved":
        from app.services.processing.validation import validate_result

        source_task = tasks.get_task(db, UUID(projection["task_id"]))
        issues = [
            issue
            for issue in validate_result(content, source_task.request)
            if issue["issue_code"]
            not in {
                "PRIMARY_SKILL_MISSING",
                "ANSWER_EVIDENCE_MISSING",
                "DISTRACTOR_ASSESSMENT_MISSING",
            }
        ]
        if issues:
            raise w.conflict(
                "SOURCE_REQUIRED",
                "来源缺失或结构错误须先依据原件校正",
                issues=[
                    {"code": r["issue_code"], "reference": r.get("src_id")}
                    for r in issues[:30]
                ],
            )
    if (
        projection["dependency_hash"] != payload.expected_stage_dependency_hash
        or projection["artifact_hash"] != payload.artifact_hash
    ):
        raise w.conflict("ARTIFACT_CHANGED", "阶段产物或依赖已变化")
    expected = (
        {s["_src_id"] for s in content["segments"] if s["segment_type"] == "body"}
        if payload.stage == "align"
        else {
            q["_src_id"]
            for q in content["questions"][: 5 if payload.stage == "sample" else None]
        }
    )
    if payload.stage == "sample":
        from app.module3.distractor_annotations import validate_option_relations

        sample = {**content, "questions": content["questions"][:5]}
        if payload.decision == "approved":
            validate_option_relations(sample)
        expected |= {a["_src_id"] for a in content.get("distractor_assessments", [])}
    items = payload.items
    if (
        {item.reference for item in items} != expected
        or len(items) != len(expected)
        or (
            payload.decision == "approved"
            and any(item.decision != "approved" for item in items)
        )
    ):
        raise w.conflict("REVIEW_INCOMPLETE", "阶段确认须逐项覆盖真实来源对象")
    if payload.review_basis == "user_confirmation" and (
        payload.stage != "align" or not payload.approval_reference
    ):
        raise AppError(422, "核听确认须保留实际审批来源")
    from uuid import uuid4

    approval = m.ProcessingStageApproval(
        id=uuid4(),
        revision_id=revision.id,
        stage=payload.stage,
        artifact_hash=payload.artifact_hash,
        dependency_hash=payload.expected_stage_dependency_hash,
        decision=payload.decision,
        items={
            "items": [item.model_dump() for item in items],
            "review_basis": payload.review_basis,
            "approval_reference": payload.approval_reference,
            "reviewer_kind": payload.reviewer_kind,
        },
        operator_user_id=user_id,
    )
    db.add(approval)
    workflow.row_version += 1
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "stage_approval",
        key,
        digest,
        body,
        {"approval_id": str(approval.id), "row_version": workflow.row_version},
    )


def continue_stage(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "continue", key, workflow_id, payload
    )
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if workflow.processing_state != WAITING[payload.stage]:
        raise w.conflict("VERSION_CONFLICT", "当前不在该阶段确认点")
    _, projection = stage_payload(db, revision, payload.stage, settings)
    if projection["dependency_hash"] != payload.expected_stage_dependency_hash:
        raise w.conflict("ARTIFACT_CHANGED", "阶段依赖已变化")
    approval = db.scalar(
        select(m.ProcessingStageApproval)
        .where(
            m.ProcessingStageApproval.revision_id == revision.id,
            m.ProcessingStageApproval.stage == payload.stage,
            m.ProcessingStageApproval.dependency_hash
            == payload.expected_stage_dependency_hash,
        )
        .order_by(
            m.ProcessingStageApproval.created_at.desc(),
            m.ProcessingStageApproval.id.desc(),
        )
        .limit(1)
    )
    if not approval or approval.decision != "approved":
        raise w.conflict("STAGE_APPROVAL_REQUIRED", "须先保存当前阶段的逐项确认")
    target = NEXT_STAGE[payload.stage]
    if payload.stage == "source":
        previous = tasks.get_task(db, workflow.current_task_id)
        plan = previous.request.get("repair_plan")
        if plan and plan.get("sample_valid"):
            target = "annotate"
    task = queue_task(db, workflow, revision, target, user_id, settings)
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "continue",
        key,
        digest,
        body,
        {"task_id": str(task.id), "stage": target, "row_version": workflow.row_version},
        state="accepted",
    )


def stop(db, workflow_id, payload, user_id, key):
    old, digest, body = w.begin_command(db, user_id, "stop", key, workflow_id, payload)
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    if workflow.processing_state not in {"queued", "running", "stopping"}:
        raise w.conflict("VERSION_CONFLICT", "当前没有可停止的执行")
    commands = db.scalars(
        select(m.ProcessingWorkflowCommand)
        .where(
            m.ProcessingWorkflowCommand.revision_id == revision.id,
            m.ProcessingWorkflowCommand.state.in_(["accepted", "running"]),
        )
        .with_for_update()
    ).all()
    had_running = False
    for command in commands:
        had_running |= command.state == "running"
        command.state, command.execution_token, command.lease_expires_at = (
            "stopped",
            None,
            None,
        )
    if workflow.current_task_id and any(
        command.result.get("task_id") for command in commands
    ):
        task = tasks.get_task(db, workflow.current_task_id, lock=True)
        task.state = "stopping" if had_running else "stopped"
        task.lease_token, task.expires_at = None, None
    workflow.processing_state = "stopping" if had_running else "stopped"
    if any(command.result.get("stage") == "publish" for command in commands):
        workflow.publication_state = "stopped"
    workflow.row_version += 1
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "stop",
        key,
        digest,
        body,
        {
            "processing_state": workflow.processing_state,
            "row_version": workflow.row_version,
        },
    )


def retry(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(db, user_id, "retry", key, workflow_id, payload)
    if old:
        return old
    workflow, revision = w.locked_current(db, workflow_id, payload)
    previous = db.get(m.ProcessingWorkflowCommand, payload.retry_of_operation_id)
    if (
        not previous
        or previous.revision_id != revision.id
        or previous.state not in {"failed", "stopped"}
        or workflow.processing_state not in {"failed", "stopped"}
    ):
        raise w.conflict("VERSION_CONFLICT", "仅可显式重试当前修订的失败或已停止操作")
    if previous.result.get("stage") == "publish":
        raise w.conflict(
            "PUBLICATION_RETRY_REQUIRED", "发布重试须使用原最终结果与已有pending批次"
        )
    # Unknown charges remain visible and count at their reserved amount. They
    # do not block an explicit retry; reservation still enforces shared budgets.
    recovery_task = tasks.get_task(db, UUID(previous.result["task_id"]))
    if revision.rules_manifest != rules_manifest():
        from app.services.processing.candidate_recovery import runtime_compatible
        from app.services.processing.reprocessing import child_revision

        if (
            previous.result["stage"] != "annotate_sample"
            or revision.final_result_hash
            or not runtime_compatible(revision.rules_manifest, rules_manifest())
        ):
            raise w.conflict("ARTIFACT_CHANGED", "生成方法变化，请按新修订重新核对依赖")
        parent = revision
        originals = []
        for stage in ("align", "source"):
            projection = parent.stage_fingerprints.get(stage)
            approval = db.scalar(
                select(m.ProcessingStageApproval)
                .where(
                    m.ProcessingStageApproval.revision_id == parent.id,
                    m.ProcessingStageApproval.stage == stage,
                )
                .order_by(m.ProcessingStageApproval.created_at.desc())
                .limit(1)
            )
            if (
                not projection
                or not approval
                or approval.decision != "approved"
                or approval.dependency_hash != projection["dependency_hash"]
            ):
                raise w.conflict(
                    "APPROVAL_REQUIRED", "运行修复须保留实际核听和来源确认记录"
                )
            stage_payload(db, parent, stage, settings)
            originals.append(approval)
        revision = child_revision(
            db,
            workflow,
            parent,
            user_id,
            "独立Worker运行修复；原件及来源内容未变，逐题复验已保存候选",
        )
        for approval in originals:
            db.add(
                m.ProcessingStageApproval(
                    id=__import__("uuid").uuid4(),
                    revision_id=revision.id,
                    stage=approval.stage,
                    artifact_hash=approval.artifact_hash,
                    dependency_hash=approval.dependency_hash,
                    decision="approved",
                    items={
                        "reused_items": approval.items,
                        "runtime_repair_from": str(parent.id),
                    },
                    operator_user_id=user_id,
                    reused_approval_id=approval.id,
                )
            )
    task = queue_task(
        db, workflow, revision, previous.result["stage"], user_id, settings
    )
    task.parent_task_id = recovery_task.id
    task.request = {**task.request, "recovery_task_id": str(recovery_task.id)}
    if (
        previous.result["stage"] == "assemble"
        and db.scalar(
            select(p.ProcessingArtifact.id)
            .where(
                p.ProcessingArtifact.task_id == recovery_task.id,
                p.ProcessingArtifact.stage == "assembly_extract",
            )
            .limit(1)
        )
        is not None
    ):
        # Reuse only through assembly_scan's material/model/image integrity gates.
        task.request = {
            **task.request,
            "reuse_assembly_scan_task_id": str(recovery_task.id),
        }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials_hash": revision.materials_hash,
        }
    )
    result = {
        "task_id": str(task.id),
        "stage": previous.result["stage"],
        "row_version": workflow.row_version,
    }
    # The immutable retry linkage is stored on the command before its first commit.
    command = m.ProcessingWorkflowCommand(
        id=__import__("uuid").uuid4(),
        workflow_id=workflow.id,
        revision_id=revision.id,
        action="retry",
        idempotency_key=key,
        request_hash=digest,
        request=body,
        expected_workflow_version=payload.expected_workflow_version,
        state="accepted",
        result=result,
        retry_of_operation_id=previous.id,
        created_by=user_id,
    )
    db.add(command)
    db.flush()
    w.add_event(db, workflow, revision, command, user_id, "retry", result)
    db.commit()
    return command
