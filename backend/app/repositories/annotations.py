"""Current-only annotations. Legacy errors are excluded without changing visibility."""

from sqlalchemy import select, text

from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import ERROR_RULE_VERSION, rules_manifest
from app.repositories import listening
from app.services.processing import publication, reading
from app.services.processing import workflows as w
from app.services.processing.candidate_recovery import runtime_compatible


def current_annotations(db, paper_id, expected_batch_id, cursor, limit):
    paper = listening.get_paper(db, paper_id)
    if not paper:
        from app.core.errors import not_found

        raise not_found()
    batch = listening.get_current_batch(db, paper_id)
    if expected_batch_id is not None and (not batch or batch.id != expected_batch_id):
        raise w.conflict("CURRENT_BATCH_CHANGED", "正式批次已变化，请整体刷新详情")
    if cursor and expected_batch_id is None:
        raise w.conflict("CURRENT_BATCH_CHANGED", "分页须绑定首次读取的正式批次")
    revision = (
        db.scalar(
            select(m.ProcessingWorkflowRevision).where(
                m.ProcessingWorkflowRevision.batch_id == batch.id
            )
        )
        if batch
        else None
    )
    if not revision:
        return {
            "batch_id": batch.id if batch else None,
            "result_hash": batch.result_hash if batch else None,
            "annotation_state": "legacy_pending",
            "items": [],
            "next_cursor": None,
        }
    current_method = rules_manifest()
    if not runtime_compatible(revision.rules_manifest, current_method):
        return {
            "batch_id": batch.id,
            "result_hash": revision.final_result_hash,
            "annotation_state": "method_pending",
            "items": [],
            "next_cursor": None,
        }
    session = db.scalar(
        select(m.ProcessingReviewSession).where(
            m.ProcessingReviewSession.revision_id == revision.id,
            m.ProcessingReviewSession.result_hash == revision.final_result_hash,
        )
    )
    task = db.get(p.ProcessingTask, revision.final_task_id)
    if not task:
        raise w.conflict("ANNOTATION_INTEGRITY", "当前新规则标注的生成任务缺失")
    draft = db.scalar(
        select(p.ProcessingDraft).where(
            p.ProcessingDraft.task_id == task.id, p.ProcessingDraft.view == "final"
        )
    )
    states = db.execute(
        text(
            "SELECT question_id,generation_state,rule_version,rules_manifest_hash "
            "FROM question_annotation_states WHERE batch_id=:b"
        ),
        {"b": batch.id},
    ).all()
    if (
        not session
        or session.state != "approved"
        or not draft
        or batch.result_hash != revision.final_result_hash
        or len(states) != len(draft.payload["questions"])
        or any(
            row.rule_version != ERROR_RULE_VERSION
            or row.rules_manifest_hash != revision.rules_manifest["manifest_hash"]
            for row in states
        )
    ):
        raise w.conflict("ANNOTATION_INTEGRITY", "当前新规则标注的生成或审核身份不完整")
    if revision.rules_manifest != current_method:
        # Runtime compatibility alone is insufficient: recheck actual responses,
        # receipts and unchanged source with the same guard used for publication.
        from app.core.config import get_settings
        from app.services.processing.reviewing import validate_final

        validate_final(db, draft.payload, task.request, revision, get_settings())
    publication.verify_actual_batch(db, batch, draft.payload)
    selected = draft.payload["questions"][cursor : cursor + limit]
    items = [reading.question_view(draft.payload, question) for question in selected]
    for item in items:
        item["review_state"] = "approved"
    return {
        "batch_id": batch.id,
        "result_hash": revision.final_result_hash,
        "annotation_state": "approved",
        "rule_version": ERROR_RULE_VERSION,
        "items": items,
        "next_cursor": cursor + limit
        if cursor + limit < len(draft.payload["questions"])
        else None,
    }
