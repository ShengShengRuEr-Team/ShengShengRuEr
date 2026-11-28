"""SQL access for the read-only skill/error query."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import distinct, func, select, tuple_
from sqlalchemy.orm import Session

from app.db.models_annotations import (
    ErrorCause,
    ErrorQuestionRelation,
    EvidenceItem,
    OtherRelation,
    Skill,
    SkillQuestionRelation,
)
from app.db.models_listening import (
    AudioFile,
    ExamPaper,
    Passage,
    Presentation,
    Question,
    TranscriptSegment,
)
from app.db.models_processing import DictionarySnapshot


def latest_snapshot(db: Session) -> DictionarySnapshot | None:
    return db.scalar(
        select(DictionarySnapshot)
        .order_by(DictionarySnapshot.created_at.desc(), DictionarySnapshot.id.desc())
        .limit(1)
    )


def load_dictionary_nodes(db: Session, snapshot_id: int):
    skills = db.scalars(
        select(Skill).where(Skill.snapshot_id == snapshot_id, Skill.status == "启用")
    ).all()
    errors = db.scalars(
        select(ErrorCause).where(
            ErrorCause.snapshot_id == snapshot_id, ErrorCause.status == "启用"
        )
    ).all()
    taxonomy = db.scalars(
        select(OtherRelation).where(
            OtherRelation.snapshot_id == snapshot_id,
            OtherRelation.scope == "snapshot",
            OtherRelation.relation_kind == "SKILL_TAXONOMY",
            OtherRelation.is_current.is_(True),
        )
    ).all()
    return skills, errors, taxonomy


def count_skill_usage(
    db: Session, batch_ids: Iterable[int]
) -> dict[int, dict[str, int]]:
    ids = tuple(batch_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            SkillQuestionRelation.skill_id,
            SkillQuestionRelation.role,
            func.count(distinct(SkillQuestionRelation.question_id)),
        )
        .where(
            SkillQuestionRelation.batch_id.in_(ids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
            SkillQuestionRelation.question_id.is_not(None),
        )
        .group_by(SkillQuestionRelation.skill_id, SkillQuestionRelation.role)
    ).all()
    result: dict[int, dict[str, int]] = defaultdict(
        lambda: {"question": 0, "primary": 0, "auxiliary": 0}
    )
    for skill_id, role, count in rows:
        result[skill_id]["question"] += int(count)
        if role == "PRIMARY":
            result[skill_id]["primary"] = int(count)
        elif role == "AUXILIARY":
            result[skill_id]["auxiliary"] = int(count)
    # A question can carry both roles for the same skill; total is a distinct
    # question count, not the sum of the two role buckets.
    totals = db.execute(
        select(
            SkillQuestionRelation.skill_id,
            func.count(distinct(SkillQuestionRelation.question_id)),
        )
        .where(
            SkillQuestionRelation.batch_id.in_(ids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
            SkillQuestionRelation.question_id.is_not(None),
        )
        .group_by(SkillQuestionRelation.skill_id)
    ).all()
    for skill_id, count in totals:
        result[skill_id]["question"] = int(count)
    return dict(result)


def count_error_usage(
    db: Session, batch_ids: Iterable[int]
) -> dict[int, dict[str, int]]:
    ids = tuple(batch_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            ErrorQuestionRelation.error_cause_id,
            func.count(distinct(ErrorQuestionRelation.question_id)),
            func.count(
                distinct(
                    tuple_(
                        ErrorQuestionRelation.question_id,
                        ErrorQuestionRelation.option_letter,
                        ErrorQuestionRelation.error_cause_id,
                    )
                )
            ),
        )
        .where(
            ErrorQuestionRelation.batch_id.in_(ids),
            ErrorQuestionRelation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            ErrorQuestionRelation.is_current.is_(True),
            ErrorQuestionRelation.business_eligible.is_(True),
            ErrorQuestionRelation.question_id.is_not(None),
            ErrorQuestionRelation.option_letter.is_not(None),
        )
        .group_by(ErrorQuestionRelation.error_cause_id)
    ).all()
    return {
        int(error_id): {
            "question": int(question_count),
            "option_relation": int(relation_count),
        }
        for error_id, question_count, relation_count in rows
    }


def load_questions(db: Session, question_ids: Iterable[int]) -> dict[int, Question]:
    ids = tuple(question_ids)
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(select(Question).where(Question.id.in_(ids))).all()
    }


def load_presentations(
    db: Session, question_ids: Iterable[int], batch_ids: Iterable[int] | None = None
) -> dict[int, list[tuple[Presentation, ExamPaper]]]:
    ids = tuple(question_ids)
    if not ids:
        return {}
    query = (
        select(Presentation, ExamPaper)
        .join(ExamPaper, ExamPaper.id == Presentation.exam_paper_id)
        .where(Presentation.question_id.in_(ids))
    )
    if batch_ids is not None:
        bids = tuple(batch_ids)
        if not bids:
            return {}
        query = query.where(Presentation.batch_id.in_(bids))
    rows = db.execute(
        query.order_by(
            Presentation.question_id,
            Presentation.question_no,
            Presentation.id,
        )
    ).all()
    result: dict[int, list[tuple[Presentation, ExamPaper]]] = defaultdict(list)
    for presentation, paper in rows:
        result[presentation.question_id].append((presentation, paper))
    return dict(result)


def load_audio_rows(
    db: Session, audio_ids: Iterable[int | None]
) -> dict[int, AudioFile]:
    ids = tuple({int(a) for a in audio_ids if a is not None})
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(select(AudioFile).where(AudioFile.id.in_(ids))).all()
    }


def load_question_skills(
    db: Session, question_ids: Iterable[int], batch_ids: Iterable[int]
) -> dict[int, list[SkillQuestionRelation]]:
    qids = tuple(question_ids)
    bids = tuple(batch_ids)
    if not qids or not bids:
        return {}
    rows = db.scalars(
        select(SkillQuestionRelation)
        .where(
            SkillQuestionRelation.question_id.in_(qids),
            SkillQuestionRelation.batch_id.in_(bids),
            SkillQuestionRelation.relation_kind == "QUESTION_SKILL",
            SkillQuestionRelation.is_current.is_(True),
        )
        .order_by(SkillQuestionRelation.question_id, SkillQuestionRelation.id)
    ).all()
    result: dict[int, list[SkillQuestionRelation]] = defaultdict(list)
    for row in rows:
        result[row.question_id].append(row)
    return dict(result)


def load_question_errors(
    db: Session, question_ids: Iterable[int], batch_ids: Iterable[int]
) -> dict[int, list[ErrorQuestionRelation]]:
    qids = tuple(question_ids)
    bids = tuple(batch_ids)
    if not qids or not bids:
        return {}
    rows = db.scalars(
        select(ErrorQuestionRelation)
        .where(
            ErrorQuestionRelation.question_id.in_(qids),
            ErrorQuestionRelation.batch_id.in_(bids),
            ErrorQuestionRelation.relation_kind == "QUESTION_ERROR_CANDIDATE",
            ErrorQuestionRelation.is_current.is_(True),
            ErrorQuestionRelation.business_eligible.is_(True),
            ErrorQuestionRelation.option_letter.is_not(None),
        )
        .order_by(
            ErrorQuestionRelation.question_id,
            ErrorQuestionRelation.option_letter,
            ErrorQuestionRelation.id,
        )
    ).all()
    result: dict[int, list[ErrorQuestionRelation]] = defaultdict(list)
    for row in rows:
        result[row.question_id].append(row)
    return dict(result)


def load_evidence(db: Session, evidence_ids: Iterable[int]) -> dict[int, EvidenceItem]:
    ids = tuple({int(x) for x in evidence_ids})
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(
            select(EvidenceItem).where(EvidenceItem.id.in_(ids))
        ).all()
    }


def load_skill_evidence(
    db: Session, owner_ids: Iterable[int], batch_ids: Iterable[int]
) -> dict[int, list[tuple[SkillQuestionRelation, EvidenceItem]]]:
    owners = tuple(owner_ids)
    bids = tuple(batch_ids)
    if not owners or not bids:
        return {}
    rows = db.execute(
        select(SkillQuestionRelation, EvidenceItem)
        .join(EvidenceItem, EvidenceItem.id == SkillQuestionRelation.evidence_id)
        .where(
            SkillQuestionRelation.owner_relation_id.in_(owners),
            SkillQuestionRelation.batch_id.in_(bids),
            SkillQuestionRelation.relation_kind == "SKILL_EVIDENCE",
            SkillQuestionRelation.is_current.is_(True),
        )
        .order_by(
            SkillQuestionRelation.owner_relation_id, SkillQuestionRelation.sort_order
        )
    ).all()
    result: dict[int, list[tuple[SkillQuestionRelation, EvidenceItem]]] = defaultdict(
        list
    )
    for relation, evidence in rows:
        result[relation.owner_relation_id].append((relation, evidence))
    return dict(result)


def load_error_evidence(
    db: Session, owner_ids: Iterable[int], batch_ids: Iterable[int]
) -> dict[int, list[tuple[ErrorQuestionRelation, EvidenceItem]]]:
    owners = tuple(owner_ids)
    bids = tuple(batch_ids)
    if not owners or not bids:
        return {}
    rows = db.execute(
        select(ErrorQuestionRelation, EvidenceItem)
        .join(EvidenceItem, EvidenceItem.id == ErrorQuestionRelation.evidence_id)
        .where(
            ErrorQuestionRelation.owner_relation_id.in_(owners),
            ErrorQuestionRelation.batch_id.in_(bids),
            ErrorQuestionRelation.relation_kind == "CANDIDATE_EVIDENCE",
            ErrorQuestionRelation.is_current.is_(True),
        )
        .order_by(
            ErrorQuestionRelation.owner_relation_id, ErrorQuestionRelation.sort_order
        )
    ).all()
    result: dict[int, list[tuple[ErrorQuestionRelation, EvidenceItem]]] = defaultdict(
        list
    )
    for relation, evidence in rows:
        result[relation.owner_relation_id].append((relation, evidence))
    return dict(result)


def count_error_evidence(
    db: Session, owner_ids: Iterable[int], batch_ids: Iterable[int]
) -> dict[int, int]:
    owners = tuple(owner_ids)
    bids = tuple(batch_ids)
    if not owners or not bids:
        return {}
    rows = db.execute(
        select(ErrorQuestionRelation.owner_relation_id, func.count())
        .where(
            ErrorQuestionRelation.owner_relation_id.in_(owners),
            ErrorQuestionRelation.batch_id.in_(bids),
            ErrorQuestionRelation.relation_kind == "CANDIDATE_EVIDENCE",
            ErrorQuestionRelation.is_current.is_(True),
        )
        .group_by(ErrorQuestionRelation.owner_relation_id)
    ).all()
    return {int(owner): int(count) for owner, count in rows}


def load_answer_evidence(
    db: Session, question_id: int, batch_id: int
) -> list[tuple[OtherRelation, EvidenceItem]]:
    return db.execute(
        select(OtherRelation, EvidenceItem)
        .join(EvidenceItem, EvidenceItem.id == OtherRelation.evidence_id)
        .where(
            OtherRelation.question_id == question_id,
            OtherRelation.batch_id == batch_id,
            OtherRelation.scope == "batch",
            OtherRelation.relation_kind == "ANSWER_EVIDENCE",
            OtherRelation.is_current.is_(True),
        )
        .order_by(OtherRelation.sort_order, OtherRelation.id)
    ).all()


def load_passage(db: Session, passage_id: int, batch_id: int):
    passage = db.scalar(
        select(Passage).where(Passage.id == passage_id, Passage.batch_id == batch_id)
    )
    if passage is None:
        return None, []
    segments = db.scalars(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.passage_id == passage_id,
            TranscriptSegment.batch_id == batch_id,
        )
        .order_by(TranscriptSegment.segment_index)
    ).all()
    return passage, list(segments)
