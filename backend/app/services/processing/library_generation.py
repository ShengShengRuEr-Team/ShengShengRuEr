"""Generate in independent child revisions without taking the shared edit head."""

from copy import deepcopy
from types import SimpleNamespace

from sqlalchemy import select

from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.module3.contracts import fingerprint
from app.module3.providers import freeze, secret
from app.schemas_library import EvaluationCandidates
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import orchestration as o
from app.services.processing import workflows as w


def independent(revision):
    return (
        revision.workflow_contract == "library.v1"
        and revision.origin_manifest.get("candidate_only") is True
    )


def generate(db, workflow_id, payload, user_id, key, settings):
    old, digest, body = w.begin_command(
        db, user_id, "library_generate", key, workflow_id, payload
    )
    if old:
        return old
    evaluation = isinstance(payload, EvaluationCandidates)
    if evaluation:
        workflow = w.get_workflow(db, workflow_id)
        if not workflow.exam_paper_id:
            raise w.conflict("SOURCE_REQUIRED", "评测前须完成来源组装")
        paper = e.paper_lock(db, workflow.exam_paper_id)
        workflow = w.get_workflow(db, workflow_id, lock=True)
        if workflow.current_revision_id != payload.evaluation_source_revision_id:
            raise w.conflict("SOURCE_CHANGED", "评测来源修订已变化")
        parent = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
        source, _ = o.stage_payload(db, parent, "source", settings)
        snapshot = c.canonical_snapshot(c.projection(source))
        head = SimpleNamespace(
            row_version=paper.library_row_version,
            revision_id=parent.id,
            current_save_version_id=None,
        )
        current = None
    else:
        paper, workflow, head, current, snapshot = e.context(db, workflow_id, lock=True)
    e.available(db, workflow, paper)
    e.preconditions(head, snapshot, payload)
    parent = db.get(m.ProcessingWorkflowRevision, head.revision_id)
    source, projection = o.stage_payload(db, parent, "source", settings)
    if any(
        c.canonical_snapshot(c.projection(source))[name] != snapshot[name]
        for name in c.SOURCE_SECTIONS
    ):
        raise w.conflict(
            "SOURCE_REVIEW_REQUIRED", "当前内容须先重新组装来源并完成核听确认"
        )
    qids = set(payload.question_src_ids)
    if len(qids) != len(payload.question_src_ids) or not qids <= {
        q["_src_id"] for q in snapshot["questions"]
    }:
        raise c.invalid("生成范围须为当前卷中不重复的题目源身份")
    approval = db.scalar(
        select(m.ProcessingStageApproval)
        .where(
            m.ProcessingStageApproval.revision_id == parent.id,
            m.ProcessingStageApproval.stage == "source",
            m.ProcessingStageApproval.dependency_hash == projection["dependency_hash"],
        )
        .order_by(m.ProcessingStageApproval.created_at.desc())
        .limit(1)
    )
    if evaluation and payload.evaluation_source_hash != projection["dependency_hash"]:
        raise w.conflict("SOURCE_CHANGED", "评测冻结来源已变化")
    if not evaluation and (
        not approval
        or approval.decision != "approved"
        or not approval.items.get("listening_items")
    ):
        raise w.conflict("SOURCE_REVIEW_REQUIRED", "候选生成前必须有真实来源与核听确认")
    method = freeze(payload.provider, settings)
    secret(method, settings)
    prior = {
        k: deepcopy(getattr(workflow, k))
        for k in (
            "current_revision_id",
            "current_task_id",
            "processing_state",
            "content_review_state",
            "error_review_state",
            "publication_state",
        )
    }
    revision = w.copy_revision(
        db,
        workflow,
        parent,
        user_id,
        payload.reason,
        parent.document_mode,
        parent.listening_pages,
    )
    revision.workflow_contract = "library.v1"
    revision.materials_manifest, revision.materials_hash = (
        deepcopy(parent.materials_manifest),
        parent.materials_hash,
    )
    revision.materials_frozen_at = parent.materials_frozen_at
    revision.stage_fingerprints = {
        k: deepcopy(v)
        for k, v in parent.stage_fingerprints.items()
        if k in {"align", "source"}
    }
    revision.origin_manifest = {
        "candidate_only": True,
        "source_revision_id": str(parent.id),
        "provider_method": method,
        "source_approval_id": str(approval.id) if approval else None,
        "return_processing_state": prior["processing_state"],
    }
    if evaluation:
        revision.origin_manifest = {
            **revision.origin_manifest,
            "evaluation_only": True,
            "evaluation_id": str(payload.evaluation_id),
            "listening_review": {
                "state": "waived_by_user",
                "actual_listening_performed": False,
                "reference": payload.listening_waiver_reference,
                "operator_user_id": user_id,
            },
        }
    revision.method_manifest_hash = fingerprint(
        {"rules": revision.rules_manifest, "provider": method}
    )
    task = o.queue_task(db, workflow, revision, "annotate", user_id, settings)
    task.request = {
        **task.request,
        "annotation_question_src_ids": sorted(qids),
        "candidate_only": True,
    }
    task.input_hash = fingerprint(
        {
            "request": task.request,
            "method": task.method_hash,
            "materials": revision.materials_hash,
        }
    )
    for name, value in prior.items():
        setattr(workflow, name, value)
    workflow.processing_state = "queued"
    db.flush()
    if current:
        db.add(
            l.LibraryVersionReference(
                save_version_id=current.id,
                kind="candidate_source",
                reference=str(revision.id),
            )
        )
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        "library_generate",
        key,
        digest,
        body,
        {
            "task_id": str(task.id),
            "stage": "annotate",
            "candidate_only": True,
            "question_src_ids": sorted(qids),
            "row_version": workflow.row_version,
        },
        state="accepted",
    )
