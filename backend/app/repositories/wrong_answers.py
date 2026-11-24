"""Notebook projection over immutable grades and their original content batch."""

import logging
from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import and_, case, false, func, or_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.db.models_annotations import (
    ErrorCause,
    ErrorQuestionRelation,
    EvidenceItem,
    QuestionAnnotationState,
    QuestionDistractorAssessment,
    Skill,
    SkillQuestionRelation,
)
from app.db.models_attempt import Attempt, AttemptAnswer
from app.db.models_listening import ExamPaper, ImportBatch, Presentation, Question
from app.db.models_processing import DictionarySnapshot
from app.db.models_processing_workflows import (
    ProcessingReviewSession,
    ProcessingWorkflowRevision,
)
from app.db.models_wrong_answers import WrongAnswerState
from app.module3.annotation_identity import ERROR_RULE_VERSION, RESULT_VERSION
from app.repositories import listening
from app.schemas_wrong_answers import (
    LearningStatus,
    NotebookVisibility,
    ReviewCandidate,
    ReviewSkill,
    WrongAnswerType,
)

logger = logging.getLogger(__name__)


class NotebookEntry(NamedTuple):
    answer: AttemptAnswer
    attempt: Attempt
    paper: ExamPaper
    current_batch: ImportBatch
    state: WrongAnswerState | None


def _owned_wrong_answers(student_id: int):
    accessible = (
        listening.student_accessible_papers()
        .with_only_columns(
            ExamPaper.id.label("exam_paper_id"), ImportBatch.id.label("batch_id")
        )
        .subquery()
    )
    return (
        select(AttemptAnswer, Attempt, ExamPaper, ImportBatch, WrongAnswerState)
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .join(accessible, accessible.c.exam_paper_id == Attempt.exam_paper_id)
        .join(ExamPaper, ExamPaper.id == accessible.c.exam_paper_id)
        .join(ImportBatch, ImportBatch.id == accessible.c.batch_id)
        .outerjoin(WrongAnswerState, WrongAnswerState.answer_id == AttemptAnswer.id)
        .where(Attempt.student_id == student_id, AttemptAnswer.is_correct.is_(False))
    )


def _is_hidden():
    return func.coalesce(WrongAnswerState.is_hidden, false())


def list_entries(
    db: Session,
    student_id: int,
    *,
    page: int,
    limit: int,
    exam_paper_id: int | None,
    answer_type: WrongAnswerType | None,
    learning_status: LearningStatus | None,
    visibility: NotebookVisibility,
) -> tuple[list[NotebookEntry], int]:
    query = _owned_wrong_answers(student_id)
    if visibility != "all":
        query = query.where(_is_hidden().is_(visibility == "hidden"))
    if exam_paper_id is not None:
        query = query.where(Attempt.exam_paper_id == exam_paper_id)
    if answer_type == "incorrect":
        query = query.where(AttemptAnswer.selected_option.is_not(None))
    if answer_type == "unanswered":
        query = query.where(AttemptAnswer.selected_option.is_(None))
    if learning_status is not None:
        query = query.where(
            func.coalesce(WrongAnswerState.learning_status, "pending")
            == learning_status
        )
    totals = (
        select(func.count().label("total"))
        .select_from(query.with_only_columns(AttemptAnswer.id).subquery())
        .subquery()
    )
    page_rows = (
        query.order_by(
            Attempt.submitted_at.desc(), Attempt.id.desc(), AttemptAnswer.question_no
        )
        .offset((page - 1) * limit)
        .limit(limit)
        .subquery()
    )
    answer = aliased(AttemptAnswer, page_rows)
    attempt = aliased(Attempt, page_rows)
    paper = aliased(ExamPaper, page_rows)
    batch = aliased(ImportBatch, page_rows)
    state = aliased(WrongAnswerState, page_rows)
    # One statement gives the count and page the same MVCC snapshot. The left
    # join still returns the count when the requested page has no rows.
    rows = db.execute(
        select(answer, attempt, paper, batch, state, totals.c.total)
        .select_from(totals.outerjoin(page_rows, true()))
        .order_by(attempt.submitted_at.desc(), attempt.id.desc(), answer.question_no)
    ).all()
    return [NotebookEntry(*row[:5]) for row in rows if row[0] is not None], rows[
        0
    ].total


def find_entry(
    db: Session,
    student_id: int,
    attempt_code: UUID,
    question_no: int,
    *,
    include_hidden: bool = False,
) -> NotebookEntry | None:
    query = _owned_wrong_answers(student_id).where(
        Attempt.attempt_code == str(attempt_code),
        AttemptAnswer.question_no == question_no,
    )
    if not include_hidden:
        query = query.where(_is_hidden().is_(False))
    row = db.execute(query).one_or_none()
    return NotebookEntry(*row) if row is not None else None


def update_state(
    db: Session, answer_id: int, submitted_at: datetime, changes: dict
) -> WrongAnswerState:
    # ON CONFLICT merges only requested fields into the latest locked row.
    now = func.clock_timestamp()
    patch = dict(changes)
    initial = dict(changes)
    mastery_changed = initial.get("learning_status") == "mastered"
    initial["updated_at"] = (
        now if mastery_changed or initial.get("is_hidden") else submitted_at
    )
    changed = or_(
        *(
            getattr(WrongAnswerState, field).is_distinct_from(value)
            for field, value in changes.items()
        )
    )
    patch["updated_at"] = case((changed, now), else_=WrongAnswerState.updated_at)
    if "learning_status" in patch:
        status = patch["learning_status"]
        patch["reviewed_at"] = case(
            (
                WrongAnswerState.learning_status != status,
                now if mastery_changed else None,
            ),
            else_=WrongAnswerState.reviewed_at,
        )
        if mastery_changed:
            initial["reviewed_at"] = now
    return db.scalars(
        insert(WrongAnswerState)
        .values(answer_id=answer_id, **initial)
        .on_conflict_do_update(index_elements=[WrongAnswerState.answer_id], set_=patch)
        .returning(WrongAnswerState),
        execution_options={"populate_existing": True},
    ).one()


def _source(db, answer, attempt):
    return db.execute(
        select(Question, ImportBatch, Presentation)
        .join(ImportBatch, ImportBatch.id == Question.batch_id)
        .outerjoin(
            Presentation,
            and_(
                Presentation.batch_id == Question.batch_id,
                Presentation.question_id == Question.id,
                Presentation.exam_paper_id == attempt.exam_paper_id,
                Presentation.question_no == answer.question_no,
            ),
        )
        .where(
            Question.id == answer.question_id,
            Question.batch_id == attempt.import_batch_id,
            ImportBatch.exam_paper_id == attempt.exam_paper_id,
            ImportBatch.status == "active",
        )
    ).one_or_none()


def _approved_annotation(db, question, batch):
    state = QuestionAnnotationState
    revision = ProcessingWorkflowRevision
    review = ProcessingReviewSession
    return db.execute(
        select(DictionarySnapshot.id, state.generation_state, review.submitted_at)
        .select_from(state)
        .join(revision, revision.id == state.revision_id)
        .join(review, review.id == state.review_session_id)
        .join(
            DictionarySnapshot,
            DictionarySnapshot.schema_sha256
            == revision.rules_manifest["dictionary_sha256"].astext,
        )
        .where(
            state.batch_id == batch.id,
            state.question_id == question.id,
            state.rule_version == ERROR_RULE_VERSION,
            state.generation_state.in_(("generated_empty", "generated_nonempty")),
            state.result_hash == batch.result_hash,
            revision.batch_id == batch.id,
            revision.final_result_hash == state.result_hash,
            revision.rules_manifest["result_version"].astext == RESULT_VERSION,
            revision.rules_manifest["error_rule_version"].astext == state.rule_version,
            revision.rules_manifest["manifest_hash"].astext
            == state.rules_manifest_hash,
            review.revision_id == revision.id,
            review.result_hash == state.result_hash,
            review.state == "approved",
        )
    ).one_or_none()


def _has_valid_evidence(relation, kind: str, *, candidate: bool = False):
    evidence_relation = aliased(relation)
    query = (
        select(evidence_relation.id)
        .join(
            EvidenceItem,
            and_(
                EvidenceItem.id == evidence_relation.evidence_id,
                EvidenceItem.batch_id == evidence_relation.batch_id,
            ),
        )
        .where(
            evidence_relation.batch_id == relation.batch_id,
            evidence_relation.owner_relation_id == relation.id,
            evidence_relation.relation_kind == kind,
            evidence_relation.is_current.is_(True),
            evidence_relation.review_status == "已通过",
            EvidenceItem.review_status == "已通过",
        )
    )
    if candidate:
        query = query.where(
            evidence_relation.business_eligible.is_(True),
            evidence_relation.rule_version == ERROR_RULE_VERSION,
        )
    return query.exists()


def _skills(db, question, batch, dictionary_id):
    relation = SkillQuestionRelation
    rows = db.execute(
        select(
            Skill.display_code,
            Skill.skill_name,
            relation.role,
            Skill.definition,
        )
        .select_from(relation)
        .join(Skill, Skill.id == relation.skill_id)
        .where(
            relation.batch_id == batch.id,
            relation.question_id == question.id,
            relation.relation_kind == "QUESTION_SKILL",
            relation.is_current.is_(True),
            relation.review_status == "已通过",
            relation.role.in_(("PRIMARY", "AUXILIARY")),
            Skill.snapshot_id == dictionary_id,
            Skill.skill_level == 3,
            Skill.status == "启用",
            _has_valid_evidence(relation, "SKILL_EVIDENCE"),
        )
        .order_by(relation.id)
    )
    return [
        ReviewSkill(
            code=code, name=name, role=role, definition=definition.strip() or None
        )
        for code, name, role, definition in rows
    ]


def _candidate_causes(db, answer, question, batch, presentation, dictionary_id):
    if not answer.selected_option:
        return []
    base_option = _mapped_option(answer, question, batch, presentation)
    if base_option is None:
        return []

    relation = ErrorQuestionRelation
    assessment = QuestionDistractorAssessment
    rows = db.execute(
        select(
            ErrorCause.display_code,
            ErrorCause.cause_name,
            ErrorCause.definition,
        )
        .select_from(relation)
        .join(ErrorCause, ErrorCause.id == relation.error_cause_id)
        .join(
            assessment,
            and_(
                assessment.batch_id == relation.batch_id,
                assessment.question_id == relation.question_id,
                assessment.option_letter == relation.option_letter,
            ),
        )
        .where(
            relation.batch_id == batch.id,
            relation.question_id == question.id,
            relation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            relation.is_current.is_(True),
            relation.review_status == "已通过",
            relation.option_letter == base_option,
            relation.business_eligible.is_(True),
            relation.rule_version == ERROR_RULE_VERSION,
            assessment.rule_version == ERROR_RULE_VERSION,
            assessment.status == "SUPPORTED",
            ErrorCause.snapshot_id == dictionary_id,
            ErrorCause.cause_level == 3,
            ErrorCause.status == "启用",
            _has_valid_evidence(relation, "CANDIDATE_EVIDENCE", candidate=True),
        )
        .order_by(relation.id)
    )
    return [
        ReviewCandidate(
            code=code,
            name=name,
            option_letter=answer.selected_option,
            basis_summary=definition.strip() or None,
        )
        for code, name, definition in rows
    ]


def _mapped_option(answer, question, batch, presentation):
    if presentation is not None:
        try:
            options = listening.paper_options_for(question, presentation)
            correct = listening.paper_letter_for(question, presentation)
        except listening.PaperUnavailable:
            pass
        else:
            snapshot = (
                answer.option_a,
                answer.option_b,
                answer.option_c,
                answer.option_d,
            )
            if options == snapshot and correct == answer.correct_option:
                return presentation.option_letter_mapping[answer.selected_option]
    logger.warning(
        "错题本跳过不匹配的选项标注 answer_id=%s question_id=%s batch_id=%s",
        answer.id,
        question.id,
        batch.id,
    )
    return None


def review_annotations(
    db: Session, answer: AttemptAnswer, attempt: Attempt
) -> tuple[list[ReviewSkill], list[ReviewCandidate], datetime | None]:
    source = _source(db, answer, attempt)
    if source is None:
        return [], [], None
    question, batch, presentation = source
    annotation = _approved_annotation(db, question, batch)
    if annotation is None:
        return [], [], None
    dictionary_id, generation, reviewed_at = annotation
    skills = _skills(db, question, batch, dictionary_id)
    candidates = (
        _candidate_causes(db, answer, question, batch, presentation, dictionary_id)
        if generation == "generated_nonempty"
        else []
    )
    return skills, candidates, reviewed_at if skills or candidates else None
