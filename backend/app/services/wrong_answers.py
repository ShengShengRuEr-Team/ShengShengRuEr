"""Notebook authorization and projections for students."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, not_found
from app.repositories import wrong_answers as repo
from app.schemas_wrong_answers import (
    LearningStatus,
    NotebookVisibility,
    WrongAnswerDetail,
    WrongAnswerItem,
    WrongAnswerPage,
    WrongAnswerPatch,
    WrongAnswerType,
)


def _item(entry: repo.NotebookEntry) -> WrongAnswerItem:
    answer, attempt, paper, _, state = entry
    return WrongAnswerItem(
        attempt_code=attempt.attempt_code,
        exam_paper_id=paper.id,
        question_no=answer.question_no,
        question_text=answer.question_text,
        paper_title=(
            f"{paper.exam_level} {paper.exam_year}年{paper.exam_month}月"
            f"第{paper.paper_set}套"
        ),
        submitted_at=attempt.submitted_at,
        selected_option=answer.selected_option,
        learning_status=state.learning_status if state else "pending",
        is_hidden=state.is_hidden if state else False,
        reviewed_at=state.reviewed_at if state else None,
    )


def list_entries(
    db: Session,
    student_id: int,
    settings: Settings,
    *,
    page: int,
    limit: int,
    exam_paper_id: int | None,
    answer_type: WrongAnswerType | None,
    learning_status: LearningStatus | None,
    visibility: NotebookVisibility,
) -> WrongAnswerPage:
    entries, total = repo.list_entries(
        db,
        student_id,
        page=page,
        limit=limit,
        exam_paper_id=exam_paper_id,
        answer_type=answer_type,
        learning_status=learning_status,
        visibility=visibility,
    )
    return WrongAnswerPage(
        items=[_item(entry) for entry in entries],
        total=total,
        state_writes_enabled=settings.wrong_answers_state_writes_enabled,
    )


def get_entry(
    db: Session,
    student_id: int,
    attempt_code: UUID,
    question_no: int,
    settings: Settings,
) -> WrongAnswerDetail:
    entry = repo.find_entry(db, student_id, attempt_code, question_no)
    if entry is None:
        raise not_found("错题记录不存在")
    if not settings.wrong_answers_protected_details_enabled:
        raise AppError(503, "错题详情暂未开放")

    answer, attempt, paper, batch, _ = entry
    skills, candidates = repo.review_annotations(db, answer, attempt)
    audio_url = None
    if batch.audio_id or paper.playback_audio_id:
        audio_url = (
            f"/api/v1/listening-papers/{paper.id}/audio?expected_batch_id={batch.id}"
        )
    return WrongAnswerDetail(
        **_item(entry).model_dump(),
        options={
            "A": answer.option_a,
            "B": answer.option_b,
            "C": answer.option_c,
            "D": answer.option_d,
        },
        correct_option=answer.correct_option,
        explanation_text=answer.explanation_text,
        audio_url=audio_url,
        skills=skills,
        candidate_causes=candidates,
    )


def update_entry(
    db: Session,
    student_id: int,
    attempt_code: UUID,
    question_no: int,
    settings: Settings,
    patch: WrongAnswerPatch,
) -> WrongAnswerItem:
    entry = repo.find_entry(
        db, student_id, attempt_code, question_no, include_hidden=True
    )
    if entry is None:
        raise not_found("错题记录不存在")
    if not settings.wrong_answers_state_writes_enabled:
        raise AppError(503, "错题管理暂未开放")

    state = repo.update_state(db, entry.answer.id, patch.model_dump(exclude_unset=True))
    db.commit()
    return _item(entry._replace(state=state))
