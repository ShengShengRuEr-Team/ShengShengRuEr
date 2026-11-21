"""Notebook projection over immutable grades and their original content batch."""

from collections import defaultdict

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.db.models_annotations import (
    ErrorCause,
    ErrorQuestionRelation,
    EvidenceItem,
    QuestionAnnotationState,
    Skill,
    SkillQuestionRelation,
)
from app.db.models_attempt import Attempt, AttemptAnswer
from app.db.models_listening import (
    ExamPaper,
    ImportBatch,
    Passage,
    Presentation,
    Question,
    TranscriptSegment,
)
from app.db.models_processing_workflows import (
    ProcessingReviewSession,
    ProcessingWorkflowRevision,
)
from app.db.models_wrong_answers import WrongAnswerDismissal
from app.module3.annotation_identity import ERROR_RULE_VERSION
from app.repositories import listening
from app.schemas_wrong_answers import ReviewCandidate, ReviewEvidence, ReviewSkill


def _owned_wrong_answers(student_id: int):
    return (
        select(AttemptAnswer, Attempt, ExamPaper)
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .join(ExamPaper, ExamPaper.id == Attempt.exam_paper_id)
        .where(Attempt.student_id == student_id, AttemptAnswer.is_correct.is_(False))
    )


def _visible(query):
    return query.where(
        ~select(WrongAnswerDismissal.answer_id)
        .where(WrongAnswerDismissal.answer_id == AttemptAnswer.id)
        .exists()
    )


def _item(answer, attempt, paper):
    return {
        "attempt_code": attempt.attempt_code,
        "question_no": answer.question_no,
        "question_text": answer.question_text,
        "paper_title": (
            f"{paper.exam_level} {paper.exam_year}年{paper.exam_month}月"
            f"第{paper.paper_set}套"
        ),
        "submitted_at": attempt.submitted_at,
        "selected_option": answer.selected_option,
    }


def list_entries(db: Session, student_id: int, keyword: str, page: int, limit: int):
    query = _visible(_owned_wrong_answers(student_id))
    if keyword:
        query = query.where(
            or_(
                AttemptAnswer.question_text.icontains(keyword, autoescape=True),
                ExamPaper.exam_level.icontains(keyword, autoescape=True),
                ExamPaper.exam_paper_code.icontains(keyword, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(
            Attempt.submitted_at.desc(), Attempt.id.desc(), AttemptAnswer.question_no
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return {"items": [_item(*row) for row in rows], "total": total}


def _get_entry(db, student_id, attempt_code, question_no, *, include_dismissed=False):
    query = _owned_wrong_answers(student_id).where(
        Attempt.attempt_code == str(attempt_code),
        AttemptAnswer.question_no == question_no,
    )
    row = db.execute(query if include_dismissed else _visible(query)).one_or_none()
    if row is None:
        raise not_found("错题记录不存在")
    return row


def dismiss_entry(db: Session, student_id: int, attempt_code, question_no: int):
    answer, _, _ = _get_entry(
        db, student_id, attempt_code, question_no, include_dismissed=True
    )
    db.execute(
        insert(WrongAnswerDismissal)
        .values(answer_id=answer.id)
        .on_conflict_do_nothing(index_elements=[WrongAnswerDismissal.answer_id])
    )
    db.commit()


def _source(db, answer, attempt):
    return db.execute(
        select(Question, Passage, ImportBatch, Presentation)
        .join(
            Passage,
            and_(
                Passage.id == Question.passage_id, Passage.batch_id == Question.batch_id
            ),
        )
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
        )
    ).one_or_none()


def _evidence(db, relation, batch_id, owners, kind, *, candidate=False):
    if not owners:
        return {}
    query = (
        select(
            relation.owner_relation_id,
            EvidenceItem.evidence_text,
            relation.attributes_json,
        )
        .join(
            EvidenceItem,
            and_(
                EvidenceItem.id == relation.evidence_id,
                EvidenceItem.batch_id == relation.batch_id,
            ),
        )
        .where(
            relation.batch_id == batch_id,
            relation.owner_relation_id.in_(owners),
            relation.relation_kind == kind,
            relation.is_current.is_(True),
        )
        .order_by(relation.sort_order, relation.id)
    )
    if candidate:
        query = query.where(
            relation.business_eligible.is_(True),
            relation.rule_version == ERROR_RULE_VERSION,
        )
    result = defaultdict(list)
    for owner, text, attributes in db.execute(query):
        result[owner].append(
            ReviewEvidence(text=text, note=(attributes or {}).get("support_note"))
        )
    return result


def _skills(db, question, batch):
    relation = SkillQuestionRelation
    rows = db.execute(
        select(relation, Skill)
        .join(Skill, Skill.id == relation.skill_id)
        .where(
            relation.batch_id == batch.id,
            relation.question_id == question.id,
            relation.relation_kind == "QUESTION_SKILL",
            relation.is_current.is_(True),
        )
        .order_by(relation.id)
    ).all()
    evidence = _evidence(
        db, relation, batch.id, [row.id for row, _ in rows], "SKILL_EVIDENCE"
    )
    return [
        ReviewSkill(
            code=skill.display_code,
            name=skill.skill_name,
            role=row.role,
            reason=(row.attributes_json or {}).get("annotation_reason"),
            evidence=evidence.get(row.id, []),
        )
        for row, skill in rows
    ]


def _candidate_causes(db, answer, question, batch, presentation):
    if not answer.selected_option or presentation is None:
        return []
    try:
        options = listening.paper_options_for(question, presentation)
        correct = listening.paper_letter_for(question, presentation)
    except listening.PaperUnavailable:
        return []
    if (
        options != (answer.option_a, answer.option_b, answer.option_c, answer.option_d)
        or correct != answer.correct_option
    ):
        return []
    base_option = presentation.option_letter_mapping[answer.selected_option]

    state = QuestionAnnotationState
    revision = ProcessingWorkflowRevision
    review = ProcessingReviewSession
    relation = ErrorQuestionRelation
    rows = db.execute(
        select(relation, ErrorCause)
        .join(ErrorCause, ErrorCause.id == relation.error_cause_id)
        .join(
            state,
            and_(
                state.batch_id == relation.batch_id,
                state.question_id == relation.question_id,
            ),
        )
        .join(revision, revision.id == state.revision_id)
        .join(review, review.id == state.review_session_id)
        .where(
            relation.batch_id == batch.id,
            relation.question_id == question.id,
            relation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            relation.is_current.is_(True),
            relation.option_letter == base_option,
            relation.business_eligible.is_(True),
            relation.rule_version == ERROR_RULE_VERSION,
            state.rule_version == ERROR_RULE_VERSION,
            state.generation_state == "generated_nonempty",
            state.result_hash == batch.result_hash,
            revision.batch_id == batch.id,
            revision.final_result_hash == state.result_hash,
            revision.rules_manifest["manifest_hash"].astext
            == state.rules_manifest_hash,
            review.revision_id == revision.id,
            review.result_hash == state.result_hash,
            review.state == "approved",
        )
        .order_by(relation.id)
    ).all()
    evidence = _evidence(
        db,
        relation,
        batch.id,
        [row.id for row, _ in rows],
        "CANDIDATE_EVIDENCE",
        candidate=True,
    )
    return [
        ReviewCandidate(
            code=cause.display_code,
            name=cause.cause_name,
            option_letter=answer.selected_option,
            reason=(row.attributes_json or {}).get("trigger_mechanism"),
            evidence=evidence.get(row.id, []),
        )
        for row, cause in rows
    ]


def _entry_material(db, answer, attempt):
    source = _source(db, answer, attempt)
    if source is None:
        return None, []
    question, passage, batch, _ = source
    transcript = db.scalars(
        select(TranscriptSegment.text)
        .where(
            TranscriptSegment.batch_id == batch.id,
            TranscriptSegment.passage_id == passage.id,
            or_(
                TranscriptSegment.segment_type == "body",
                TranscriptSegment.id == question.question_segment_id,
            ),
        )
        .order_by(TranscriptSegment.segment_index)
    ).all()
    return source, transcript


def get_entry(db: Session, student_id: int, attempt_code, question_no: int):
    answer, attempt, paper = _get_entry(db, student_id, attempt_code, question_no)
    source, transcript = _entry_material(db, answer, attempt)
    skills, candidates, audio_url = [], [], None
    if source is not None:
        question, passage, batch, presentation = source
        skills = _skills(db, question, batch)
        candidates = _candidate_causes(db, answer, question, batch, presentation)
        if passage.audio_id or batch.audio_id:
            audio_url = f"/api/v1/wrong-answers/{attempt_code}/{question_no}/audio"
    return {
        **_item(answer, attempt, paper),
        "options": {
            "A": answer.option_a,
            "B": answer.option_b,
            "C": answer.option_c,
            "D": answer.option_d,
        },
        "correct_option": answer.correct_option,
        "explanation_text": answer.explanation_text,
        "transcript": transcript,
        "audio_url": audio_url,
        "skills": skills,
        "candidate_causes": candidates,
    }


def get_entry_audio(db: Session, student_id: int, attempt_code, question_no: int):
    answer, attempt, _ = _get_entry(db, student_id, attempt_code, question_no)
    source = _source(db, answer, attempt)
    if source is None:
        raise not_found("音频文件不可用")
    _, passage, batch, _ = source
    audio = listening.get_audio(db, passage.audio_id or batch.audio_id)
    if audio is None:
        raise not_found("音频文件不可用")
    return audio
