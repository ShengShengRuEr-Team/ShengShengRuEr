"""Notebook authorization and projections for students."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, not_found
from app.repositories import listening
from app.repositories import wrong_answers as repo
from app.schemas_wrong_answers import (
    ExplanationStatus,
    LearningStatus,
    NotebookVisibility,
    ReviewAudio,
    WrongAnswerDetail,
    WrongAnswerItem,
    WrongAnswerPage,
    WrongAnswerPatch,
    WrongAnswerType,
)
from app.services.wrong_answer_approvals import is_explanation_approved


def _item(entry: repo.NotebookEntry) -> WrongAnswerItem:
    answer, attempt, paper, _, state = entry
    return WrongAnswerItem(
        attempt_code=attempt.attempt_code,
        exam_paper_id=paper.id,
        question_no=answer.question_no,
        paper_title=(
            f"{paper.exam_level} {paper.exam_year}年{paper.exam_month}月"
            f"第{paper.paper_set}套"
        ),
        submitted_at=attempt.submitted_at,
        answer_type="unanswered" if answer.selected_option is None else "incorrect",
        learning_status=state.learning_status if state else "pending",
        is_hidden=state.is_hidden if state else False,
        updated_at=state.updated_at if state else attempt.submitted_at,
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

    answer, attempt = entry.answer, entry.attempt
    compatible = repo.compatible_review_source(db, entry)
    skills, candidates, annotation_reviewed_at = repo.review_annotations(
        db, answer, attempt, source=compatible
    )
    explanation, explanation_status = _explanation(entry, settings)
    return WrongAnswerDetail(
        **_item(entry).model_dump(),
        question_text=answer.question_text,
        options={
            "A": answer.option_a,
            "B": answer.option_b,
            "C": answer.option_c,
            "D": answer.option_d,
        },
        selected_option=answer.selected_option,
        correct_option=answer.correct_option,
        explanation_text=explanation,
        explanation_status=explanation_status,
        has_explanation=explanation is not None,
        audio=_audio(db, entry, settings, compatible=compatible),
        review_materials_source="matched_current_batch"
        if compatible
        else "submission_batch",
        audio_source_note=(
            "与交卷时相同的原音（文件哈希已核对，使用当前已开放批次）"
            if compatible
            else "当前卷音频（同交卷来源批次）"
        ),
        annotation_source_note=(
            "题干、选项、正确答案与原音已核对一致；补显当前正式批次已审核的标注，交卷快照和成绩保持原样。"
            if compatible
            else "关联标注来自交卷来源批次的当前有效审核结果，可能与交卷时不同。"
        ),
        skills=skills,
        candidate_causes=candidates,
        annotation_reviewed_at=annotation_reviewed_at,
        evidence_access="restricted" if skills or candidates else "none",
    )


def _explanation(
    entry: repo.NotebookEntry, settings: Settings
) -> tuple[str | None, ExplanationStatus]:
    answer, attempt, _, _, _ = entry
    explanation = answer.explanation_text
    if not explanation or not explanation.strip():
        return None, "missing"
    if is_explanation_approved(
        settings.wrong_answers_explanation_approvals_file,
        batch_id=attempt.import_batch_id,
        answer_id=answer.id,
        explanation=explanation,
    ):
        return explanation, "available"
    return None, "restricted"


def _audio(
    db: Session, entry: repo.NotebookEntry, settings: Settings, *, compatible=None
) -> ReviewAudio:
    _, attempt, paper, batch, _ = entry
    if (batch.id != attempt.import_batch_id and compatible is None) or (
        batch.audio_id is None and paper.playback_audio_id is not None
    ):
        return ReviewAudio(status="batch_mismatch")
    audio = listening.get_audio(db, batch.audio_id)
    if audio is None or not (settings.audio_storage_path / audio.storage_key).is_file():
        return ReviewAudio(status="missing")
    return ReviewAudio(
        status="available",
        url=f"/api/v1/listening-papers/{paper.id}/audio?expected_batch_id={batch.id}",
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

    state = repo.update_state(
        db,
        entry.answer.id,
        entry.attempt.submitted_at,
        patch.model_dump(exclude_unset=True),
    )
    db.commit()
    return _item(entry._replace(state=state))
