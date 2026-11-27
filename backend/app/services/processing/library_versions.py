"""Version summaries, explicit restore and two-pass retention under the paper lock."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.errors import AppError, not_found
from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.module3.contracts import fingerprint
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import workflows as w


def get_version(db, head, version_id, *, recover=False):
    version = db.get(l.LibrarySaveVersion, version_id)
    if (
        not version
        or version.exam_paper_id != head.exam_paper_id
        or version.workflow_id != head.workflow_id
    ):
        raise not_found("保存版本不存在")
    if recover and (version.snapshot is None or version.snapshot_pruned_at):
        raise AppError(
            410,
            "完整恢复快照已清理，版本摘要与审计记录仍保留",
            error_code="SNAPSHOT_GONE",
        )
    return version


def protection_reasons(db, head, version):
    reasons = []
    current = (
        db.get(l.LibrarySaveVersion, head.current_save_version_id)
        if head.current_save_version_id
        else None
    )
    if current and version.id in {current.id, current.parent_version_id}:
        reasons.append("latest" if version.id == current.id else "previous")
    refs = db.scalars(
        select(l.LibraryVersionReference).where(
            l.LibraryVersionReference.save_version_id == version.id,
            l.LibraryVersionReference.released_at.is_(None),
        )
    ).all()
    reasons.extend(f"{r.kind}:{r.reference}" for r in refs)
    revision = db.get(m.ProcessingWorkflowRevision, version.revision_id)
    final_version_id = None
    if revision.final_task_id:
        from app.db.models_processing import ProcessingDraft

        final_draft = db.scalar(
            select(ProcessingDraft).where(
                ProcessingDraft.task_id == revision.final_task_id,
                ProcessingDraft.view == "final",
            )
        )
        if final_draft:
            final_version_id = final_draft.payload.get("library_provenance", {}).get(
                "save_version_id"
            )
    bound_to_final = final_version_id is None or final_version_id == str(version.id)
    if revision.batch_id and bound_to_final:
        reasons.append(f"formal_batch:{revision.batch_id}")
    review = db.scalar(
        select(m.ProcessingReviewSession.id)
        .where(
            m.ProcessingReviewSession.revision_id == version.revision_id,
            m.ProcessingReviewSession.state.in_(["draft", "approved"]),
        )
        .limit(1)
    )
    if review and bound_to_final:
        reasons.append(f"review:{review}")
    active = db.scalar(
        select(m.ProcessingWorkflowCommand.id)
        .where(
            m.ProcessingWorkflowCommand.revision_id == version.revision_id,
            m.ProcessingWorkflowCommand.state.in_(["accepted", "running"]),
        )
        .limit(1)
    )
    if active:
        reasons.append(f"active_operation:{active}")
    return reasons


def summary(db, head, version):
    reasons = protection_reasons(db, head, version)
    due = version.unprotected_at + timedelta(days=7) if version.unprotected_at else None
    return {
        "id": str(version.id),
        "version_no": version.version_no,
        "parent_version_id": str(version.parent_version_id)
        if version.parent_version_id
        else None,
        "reason": version.reason,
        "actor_id": version.actor_id,
        "saved_at": version.saved_at,
        "origin_type": version.origin_type,
        "content_hash": version.content_hash,
        "diff_summary": version.diff_summary,
        "protection_reasons": reasons,
        "unprotected_at": version.unprotected_at,
        "eligible_after": due,
        "snapshot_pruned_at": version.snapshot_pruned_at,
        "can_restore": version.snapshot is not None
        and version.snapshot_pruned_at is None,
        "restored_from_version_id": str(version.restored_from_version_id)
        if version.restored_from_version_id
        else None,
    }


def versions(db, workflow_id, page, page_size):
    _, _, head, _, _ = e.context(db, workflow_id)
    rows = db.scalars(
        select(l.LibrarySaveVersion)
        .where(l.LibrarySaveVersion.exam_paper_id == head.exam_paper_id)
        .order_by(l.LibrarySaveVersion.version_no.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [summary(db, head, r) for r in rows],
        "page": page,
        "page_size": page_size,
    }


def detail(db, workflow_id, version_id):
    _, _, head, _, _ = e.context(db, workflow_id)
    version = get_version(db, head, version_id)
    return {
        **summary(db, head, version),
        "snapshot": version.snapshot,
        "cleanup_events": [
            {"state": r.state, "detail": r.detail, "created_at": r.created_at}
            for r in db.scalars(
                select(l.LibraryRetentionEvent).where(
                    l.LibraryRetentionEvent.save_version_id == version.id
                )
            ).all()
        ],
    }


def diff(db, workflow_id, version_id, against_id):
    _, _, head, _current, snapshot = e.context(db, workflow_id)
    target = get_version(db, head, version_id, recover=True)
    before = (
        get_version(db, head, against_id, recover=True).snapshot
        if against_id
        else snapshot
    )
    return {
        "changes": c.differences(before, target.snapshot),
        "impact": c.impact(
            c.differences(before, target.snapshot), before, target.snapshot
        ),
    }


def restore_snapshot(before, target, payload):
    if not payload.sections and not payload.question_src_ids:
        return deepcopy(target.snapshot)
    sections = set(payload.sections or c.SECTIONS)
    if sections - set(c.SECTIONS):
        raise c.invalid("不支持的局部回退范围")
    qids = set(payload.question_src_ids)
    if len(qids) != len(payload.question_src_ids):
        raise c.invalid("回退题目范围重复")
    if qids and not qids <= {r["_src_id"] for r in target.snapshot["questions"]}:
        raise c.invalid("回退题目不属于来源版本")
    after = deepcopy(before)
    owners = {
        r["_src_id"]
        for name in ("skill_question_relations", "error_question_relations")
        for source in (before, target.snapshot)
        for r in source[name]
        if r.get("question_src_id") in qids
    }

    def selected(row):
        return (
            row.get("question_src_id", row.get("_src_id")) in qids
            or row.get("owner_relation_src_id") in owners
        )

    for section in sections:
        if qids:
            if section in {
                "passages",
                "transcript_segments",
                "content_groups",
                "evidences",
            }:
                raise c.invalid("篇章和共享证据须显式选择完整关联范围后回退")
            after[section] = [r for r in before[section] if not selected(r)] + [
                r for r in target.snapshot[section] if selected(r)
            ]
        else:
            after[section] = deepcopy(target.snapshot[section])
    if sections & {"questions", "presentations", "transcript_segments", "passages"}:
        required = {
            "questions",
            "presentations",
            "skill_question_relations",
            "error_question_relations",
            "other_relations",
            "distractor_assessments",
            "evidences",
        }
        if not required <= sections:
            raise w.conflict(
                "RESTORE_DEPENDENCY_CONFLICT",
                "内容或映射回退须包含关联标注和证据",
                required_sections=sorted(required),
            )
    return c.canonical_snapshot(after)


def restore(db, workflow_id, payload, user_id, key=None):
    if key is not None:
        old, digest, body = w.begin_command(
            db, user_id, "library_restore", key, workflow_id, payload
        )
        if old:
            return old
    paper, workflow, head, current, before = e.context(
        db, workflow_id, lock=key is not None
    )
    e.preconditions(head, before, payload)
    target = get_version(db, head, payload.source_version_id, recover=True)
    # Same original materials/method are required. Content is revalidated below.
    manifest = c.dependency_manifest(before, head.baseline)
    if any(
        target.dependency_manifest.get(k) != manifest[k]
        for k in ("materials", "audio", "method")
    ):
        raise w.conflict(
            "RESTORE_DEPENDENCY_CONFLICT", "来源材料或方法已变化，不能直接回退"
        )
    after = restore_snapshot(before, target, payload)
    issues = c.validate_snapshot(
        after, head.baseline, e.request_for(paper, head.baseline)
    )
    changes = c.differences(before, after)
    effect = c.impact(changes, before, after)
    if key is None:
        return {
            "changes": changes,
            "impact": effect,
            "issues": issues,
            "source_version_id": str(target.id),
        }
    e.available(db, workflow, paper)
    version, changes, effect = e.append_save(
        db,
        paper,
        workflow,
        head,
        current,
        before,
        after,
        user_id,
        payload.reason,
        provenance={
            "type": "RESTORE",
            "source_version_id": str(target.id),
            "sections": payload.sections,
            "question_src_ids": payload.question_src_ids,
        },
        restored_from=target.id,
    )
    return w.finish_command(
        db,
        workflow,
        db.get(m.ProcessingWorkflowRevision, head.revision_id),
        user_id,
        "library_restore",
        key,
        digest,
        body,
        {
            "save_version_id": str(version.id) if version else None,
            "row_version": head.row_version,
            "content_hash": fingerprint(after),
            "impact": effect,
            "issues": issues,
        },
    )


def retention_candidates(db, now=None):
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(l.LibrarySaveVersion.id)
            .where(
                l.LibrarySaveVersion.snapshot_pruned_at.is_(None),
                l.LibrarySaveVersion.unprotected_at <= now - timedelta(days=7),
            )
            .order_by(l.LibrarySaveVersion.unprotected_at)
            .limit(1000)
        ).all()
    )


def prune(db, version_id, now=None):
    now = now or datetime.now(UTC)
    initial = db.get(l.LibrarySaveVersion, version_id)
    if not initial:
        raise not_found()
    e.paper_lock(db, initial.exam_paper_id)
    w.get_workflow(db, initial.workflow_id, lock=True)
    head = db.scalar(
        select(l.LibraryEditHead)
        .where(l.LibraryEditHead.exam_paper_id == initial.exam_paper_id)
        .with_for_update()
    )
    version = db.scalar(
        select(l.LibrarySaveVersion)
        .where(l.LibrarySaveVersion.id == version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    reasons = protection_reasons(db, head, version)
    due = version.unprotected_at and version.unprotected_at + timedelta(days=7) <= now
    if version.snapshot_pruned_at:
        return "already_pruned"
    state = "skipped" if reasons or not due else "pruned"
    db.add(
        l.LibraryRetentionEvent(
            id=uuid4(),
            save_version_id=version.id,
            state=state,
            detail={
                "protection_reasons": reasons,
                "retention_elapsed": bool(due),
                "checked_at": now.isoformat(),
            },
        )
    )
    if state == "pruned":
        version.snapshot_pruned_at = now
        version.snapshot = None
    db.commit()
    return state
