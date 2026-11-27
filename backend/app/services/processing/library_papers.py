"""Bounded administrator list and archive/restore admission control."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db import models_library as l
from app.db import models_processing_workflows as m
from app.db.models_attempt import Attempt
from app.db.models_listening import (
    ContentCheck,
    ExamPaper,
    ImportBatch,
    PaperVisibility,
    Presentation,
)
from app.module3.contracts import fingerprint
from app.services.processing import library_editing as e
from app.services.processing import workflows as w


def scope_hash(db, paper):
    head = db.get(l.LibraryEditHead, paper.id)
    batch_id = db.scalar(
        select(ImportBatch.id).where(
            ImportBatch.exam_paper_id == paper.id, ImportBatch.is_current.is_(True)
        )
    )
    return fingerprint(
        {
            "exam_paper_id": paper.id,
            "row_version": paper.library_row_version,
            "current_batch_id": batch_id,
            "edit_row_version": head.row_version if head else None,
            "save_version_id": str(head.current_save_version_id) if head else None,
        }
    )


def list_papers(
    db,
    *,
    page=1,
    page_size=20,
    exam_level=None,
    exam_year=None,
    exam_month=None,
    paper_set=None,
    archived=False,
    keyword=None,
    processing_state=None,
    review_state=None,
    visible=None,
):
    latest_check = (
        select(ContentCheck.is_passed)
        .where(ContentCheck.batch_id == ImportBatch.id)
        .order_by(ContentCheck.checked_at.desc(), ContentCheck.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    visible_expr = (
        select(PaperVisibility.is_visible)
        .where(PaperVisibility.batch_id == ImportBatch.id)
        .order_by(PaperVisibility.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    question_count = (
        select(func.count(Presentation.id))
        .where(Presentation.batch_id == ImportBatch.id)
        .scalar_subquery()
    )
    query = (
        select(
            ExamPaper,
            ImportBatch,
            m.ProcessingWorkflow,
            l.LibraryEditHead,
            l.LibrarySaveVersion.version_no,
            latest_check.label("check_passed"),
            visible_expr.label("is_visible"),
            question_count.label("question_count"),
        )
        .outerjoin(
            ImportBatch,
            (ImportBatch.exam_paper_id == ExamPaper.id)
            & ImportBatch.is_current.is_(True)
            & (ImportBatch.status == "active"),
        )
        .outerjoin(
            m.ProcessingWorkflow, m.ProcessingWorkflow.exam_paper_id == ExamPaper.id
        )
        .outerjoin(l.LibraryEditHead, l.LibraryEditHead.exam_paper_id == ExamPaper.id)
        .outerjoin(
            l.LibrarySaveVersion,
            l.LibrarySaveVersion.id == l.LibraryEditHead.current_save_version_id,
        )
    )
    query = query.where(
        ExamPaper.archived_at.is_not(None)
        if archived
        else ExamPaper.archived_at.is_(None)
    )
    for name, value in (
        ("exam_level", exam_level),
        ("exam_year", exam_year),
        ("exam_month", exam_month),
        ("paper_set", paper_set),
    ):
        if value is not None:
            query = query.where(getattr(ExamPaper, name) == value)
    if keyword:
        query = query.where(
            ExamPaper.exam_paper_code.icontains(keyword, autoescape=True)
        )
    if processing_state:
        query = query.where(m.ProcessingWorkflow.processing_state == processing_state)
    if review_state:
        query = query.where(m.ProcessingWorkflow.content_review_state == review_state)
    if visible is not None:
        query = query.where(func.coalesce(visible_expr, False) == visible)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(ExamPaper.updated_at.desc(), ExamPaper.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for paper, batch, workflow, head, version, passed, is_visible, count in rows:
        items.append(
            {
                "exam_paper_id": paper.id,
                "code": paper.exam_paper_code,
                "exam_level": paper.exam_level,
                "exam_year": paper.exam_year,
                "exam_month": paper.exam_month,
                "paper_set": paper.paper_set,
                "expected_question_count": paper.expected_question_count,
                "question_count": count,
                "current_batch_id": batch.id if batch else None,
                "current_batch_code": batch.batch_code if batch else None,
                "workflow_id": str(workflow.id) if workflow else None,
                "processing_state": workflow.processing_state if workflow else "legacy",
                "review_state": workflow.content_review_state
                if workflow
                else paper.review_status,
                "publication_state": workflow.publication_state
                if workflow
                else ("active" if batch else "unpublished"),
                "check_passed": bool(passed),
                "is_visible": bool(is_visible) and paper.archived_at is None,
                "version_no": version or 0,
                "edit_row_version": head.row_version if head else None,
                "row_version": paper.library_row_version,
                "archived_at": paper.archived_at,
                "archive_reason": paper.archive_reason,
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def archive_preview(db, paper_id):
    paper = db.get(ExamPaper, paper_id)
    if not paper:
        from app.core.errors import not_found

        raise not_found()
    workflow = db.scalar(
        select(m.ProcessingWorkflow).where(
            m.ProcessingWorkflow.exam_paper_id == paper_id
        )
    )
    active = (
        db.scalars(
            select(m.ProcessingWorkflowCommand.id).where(
                m.ProcessingWorkflowCommand.workflow_id == workflow.id,
                m.ProcessingWorkflowCommand.state.in_(["accepted", "running"]),
            )
        ).all()
        if workflow
        else []
    )
    return {
        "exam_paper_id": paper_id,
        "content_hash": scope_hash(db, paper),
        "row_version": paper.library_row_version,
        "archived_at": paper.archived_at,
        "active_operation_ids": [str(r) for r in active],
        "batch_count": db.scalar(
            select(func.count())
            .select_from(ImportBatch)
            .where(ImportBatch.exam_paper_id == paper_id)
        ),
        "attempt_count": db.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.exam_paper_id == paper_id)
        ),
        "version_count": db.scalar(
            select(func.count())
            .select_from(l.LibrarySaveVersion)
            .where(l.LibrarySaveVersion.exam_paper_id == paper_id)
        ),
        "impact": (
            "归档后停止新访问和新提交；已接收的提交及本人历史结果保留。"
            "恢复后须重新独立开放。"
        ),
    }


def archive(db, paper_id, payload, user_id, key, *, restore=False):
    action = "library_unarchive" if restore else "library_archive"
    old, digest, body = w.begin_command(db, user_id, action, key, paper_id, payload)
    if old:
        return old
    paper = e.paper_lock(db, paper_id)
    if (
        paper.library_row_version != payload.expected_row_version
        or scope_hash(db, paper) != payload.expected_content_hash
    ):
        raise w.conflict(
            "VERSION_CONFLICT", "试卷状态已更新", row_version=paper.library_row_version
        )
    workflow = db.scalar(
        select(m.ProcessingWorkflow)
        .where(m.ProcessingWorkflow.exam_paper_id == paper_id)
        .with_for_update()
    )
    if not workflow:
        from app.services.processing.library_legacy import ensure_workflow

        workflow = ensure_workflow(db, paper, user_id)
    # Restoration is allowed on an archived paper; execution conflicts remain.
    if (
        workflow.processing_state in {"queued", "running", "stopping"}
        or archive_preview(db, paper_id)["active_operation_ids"]
        or workflow.publication_state
        in {"preparing", "pending_batch", "validating", "activating"}
    ):
        raise w.conflict("WORKFLOW_BUSY", "请先停止处理或完成发布，再操作回收站")
    changed = (paper.archived_at is not None) == restore
    if changed:
        paper.archived_at = None if restore else datetime.now(UTC)
        paper.archived_by = None if restore else user_id
        paper.archive_reason = None if restore else payload.reason
        paper.library_row_version += 1
        paper.updated_at = datetime.now(UTC)
        # Both transitions revoke visibility; restore can never silently reopen.
        for visibility in db.scalars(
            select(PaperVisibility).where(PaperVisibility.exam_paper_id == paper_id)
        ).all():
            visibility.is_visible = False
    revision = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
    return w.finish_command(
        db,
        workflow,
        revision,
        user_id,
        action,
        key,
        digest,
        body,
        {
            "exam_paper_id": paper_id,
            "row_version": paper.library_row_version,
            "archived": paper.archived_at is not None,
            "is_visible": False,
            "changed": changed,
        },
    )
