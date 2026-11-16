"""Versioned annotation tables; generated declarations reviewed against schema V1.2."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("snapshot_id", "skill_code"),)
    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(
        BigInteger, ForeignKey("dictionary_snapshots.id"), nullable=False
    )
    skill_code = Column(String(64), nullable=False)
    display_code = Column(String(64), nullable=False)
    legacy_codes = Column(String(64), nullable=True)
    skill_level = Column(Integer, nullable=False)
    skill_name = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    observable_behavior = Column(Text, nullable=True)
    counter_example = Column(Text, nullable=True)
    usage_scope = Column(String(32), nullable=False)
    exam_level_scope = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSONB, nullable=True)


class SkillErrorRelation(Base):
    __tablename__ = "skill_error_relations"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "relation_code", "revision_no"),
        Index(
            "uq_skill_error_relations_current",
            "snapshot_id",
            "relation_code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )
    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(
        BigInteger, ForeignKey("dictionary_snapshots.id"), nullable=False
    )
    relation_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    skill_id = Column(BigInteger, ForeignKey("skills.id"), nullable=False)
    error_cause_id = Column(BigInteger, ForeignKey("error_causes.id"), nullable=False)
    relation_nature = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    candidate_scope = Column(Text, nullable=False)
    selection_rule = Column(Text, nullable=False)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)


class ErrorQuestionRelation(Base):
    __tablename__ = "error_question_relations"
    __table_args__ = (
        CheckConstraint(
            "(relation_kind = 'QUESTION_ERROR_CANDIDATE' AND question_id IS "
            "NOT NULL AND error_cause_id IS NOT NULL AND owner_relation_id IS"
            " NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " "
            "ARRAY['trigger_mechanism','annotation_source','candidate_priority']::text[])"
            " = '{}'::jsonb))) OR (relation_kind = 'CANDIDATE_EVIDENCE' AND "
            "owner_relation_id IS NOT NULL AND evidence_id IS NOT NULL AND "
            "sort_order IS NOT NULL AND question_id IS NULL AND "
            "error_cause_id IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " ARRAY['support_note']::text[]) = '{}'::jsonb)))",
            name="relation_shape",
        ),
        UniqueConstraint("batch_id", "relation_code", "revision_no"),
        Index(
            "uq_error_question_relations_current",
            "batch_id",
            "relation_code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        UniqueConstraint("id", "batch_id"),
        ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_error_question_relations_question_id_batch",
        ),
        ForeignKeyConstraint(
            ["owner_relation_id", "batch_id"],
            ["error_question_relations.id", "error_question_relations.batch_id"],
            name="fk_error_question_relations_owner_relation_id_batch",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_error_question_relations_evidence_id_batch",
        ),
    )
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    relation_kind = Column(String(32), nullable=False)
    relation_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    question_id = Column(BigInteger, ForeignKey("questions.id"), nullable=True)
    error_cause_id = Column(BigInteger, ForeignKey("error_causes.id"), nullable=True)
    option_letter = Column(String(1), nullable=True)
    owner_relation_id = Column(
        BigInteger, ForeignKey("error_question_relations.id"), nullable=True
    )
    evidence_id = Column(BigInteger, ForeignKey("evidence_items.id"), nullable=True)
    sort_order = Column(Integer, nullable=True)
    attributes_json = Column(JSONB, nullable=True)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)


class SkillQuestionRelation(Base):
    __tablename__ = "skill_question_relations"
    __table_args__ = (
        CheckConstraint(
            "(relation_kind = 'QUESTION_SKILL' AND question_id IS NOT NULL "
            "AND skill_id IS NOT NULL AND role IS NOT NULL AND "
            "owner_relation_id IS NULL AND evidence_id IS NULL AND "
            "(attributes_json IS NULL OR (jsonb_typeof(attributes_json) = "
            "'object' AND (attributes_json - "
            "ARRAY['annotation_reason','annotation_source','confidence','legacy_tag_code']::text[])"
            " = '{}'::jsonb))) OR (relation_kind = 'SKILL_EVIDENCE' AND "
            "owner_relation_id IS NOT NULL AND evidence_id IS NOT NULL AND "
            "sort_order IS NOT NULL AND skill_id IS NULL AND question_id IS "
            "NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " ARRAY['relation_type','support_note']::text[]) = '{}'::jsonb)))",
            name="relation_shape",
        ),
        UniqueConstraint("batch_id", "relation_code", "revision_no"),
        Index(
            "uq_skill_question_relations_current",
            "batch_id",
            "relation_code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        UniqueConstraint("id", "batch_id"),
        ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_skill_question_relations_question_id_batch",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_skill_question_relations_evidence_id_batch",
        ),
        ForeignKeyConstraint(
            ["owner_relation_id", "batch_id"],
            ["skill_question_relations.id", "skill_question_relations.batch_id"],
            name="fk_skill_question_relations_owner_relation_id_batch",
        ),
    )
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    relation_kind = Column(String(32), nullable=False)
    relation_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    question_id = Column(BigInteger, ForeignKey("questions.id"), nullable=True)
    skill_id = Column(BigInteger, ForeignKey("skills.id"), nullable=True)
    owner_relation_id = Column(
        BigInteger, ForeignKey("skill_question_relations.id"), nullable=True
    )
    evidence_id = Column(BigInteger, ForeignKey("evidence_items.id"), nullable=True)
    role = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=True)
    attributes_json = Column(JSONB, nullable=True)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)


class OtherRelation(Base):
    __tablename__ = "other_relations"
    __table_args__ = (
        CheckConstraint(
            "(relation_kind = 'SKILL_TAXONOMY' AND from_skill_id IS NOT NULL "
            "AND to_skill_id IS NOT NULL AND role IS NOT NULL AND sort_order "
            "IS NOT NULL AND segment_id IS NULL AND question_id IS NULL AND "
            "language_item_id IS NULL AND evidence_id IS NULL AND "
            "(attributes_json IS NULL OR (jsonb_typeof(attributes_json) = "
            "'object' AND (attributes_json - "
            "ARRAY['display_path','rationale']::text[]) = '{}'::jsonb))) OR "
            "(relation_kind = 'SKILL_PREREQUISITE' AND from_skill_id IS NOT "
            "NULL AND to_skill_id IS NOT NULL AND segment_id IS NULL AND "
            "question_id IS NULL AND language_item_id IS NULL AND evidence_id"
            " IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " "
            "ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[])"
            " = '{}'::jsonb))) OR (relation_kind = 'SKILL_CO_USE' AND "
            "from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND "
            "segment_id IS NULL AND question_id IS NULL AND language_item_id "
            "IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " "
            "ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[])"
            " = '{}'::jsonb))) OR (relation_kind = 'SKILL_SUPPORT' AND "
            "from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND "
            "segment_id IS NULL AND question_id IS NULL AND language_item_id "
            "IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " "
            "ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[])"
            " = '{}'::jsonb))) OR (relation_kind = 'QUESTION_LANGUAGE_ITEM' "
            "AND question_id IS NOT NULL AND language_item_id IS NOT NULL AND"
            " from_skill_id IS NULL AND to_skill_id IS NULL AND evidence_id "
            "IS NULL AND (attributes_json IS NULL OR "
            "(jsonb_typeof(attributes_json) = 'object' AND (attributes_json -"
            " ARRAY['location_type','context_text','note']::text[]) = "
            "'{}'::jsonb))) OR (relation_kind = 'ANSWER_EVIDENCE' AND "
            "question_id IS NOT NULL AND evidence_id IS NOT NULL AND "
            "sort_order IS NOT NULL AND from_skill_id IS NULL AND to_skill_id"
            " IS NULL AND segment_id IS NULL AND language_item_id IS NULL AND"
            " (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = "
            "'object' AND (attributes_json - ARRAY['support_note']::text[]) ="
            " '{}'::jsonb)))",
            name="relation_shape",
        ),
        CheckConstraint(
            "(scope = 'batch' AND batch_id IS NOT NULL AND snapshot_id IS "
            "NULL AND scope_key = 'batch:' || batch_id::text) OR (scope = "
            "'snapshot' AND batch_id IS NULL AND snapshot_id IS NOT NULL AND "
            "scope_key = 'snapshot:' || snapshot_id::text)",
            name="scope_identity",
        ),
        CheckConstraint(
            "(scope = 'snapshot' AND relation_kind IN "
            "('SKILL_TAXONOMY','SKILL_PREREQUISITE','SKILL_CO_USE','SKILL_SUPPORT'))"
            " OR (scope = 'batch' AND relation_kind IN "
            "('QUESTION_LANGUAGE_ITEM','ANSWER_EVIDENCE'))",
            name="scope_kind",
        ),
        UniqueConstraint("scope_key", "relation_code", "revision_no"),
        Index(
            "uq_other_relations_current",
            "scope_key",
            "relation_code",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        UniqueConstraint("id", "batch_id"),
        ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_other_relations_question_id_batch",
        ),
        ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_other_relations_segment_id_batch",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_other_relations_evidence_id_batch",
        ),
        ForeignKeyConstraint(
            ["language_item_id", "batch_id"],
            ["language_items.id", "language_items.batch_id"],
            name="fk_other_relations_language_item_id_batch",
        ),
    )
    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(
        BigInteger, ForeignKey("dictionary_snapshots.id"), nullable=True
    )
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=True)
    scope_key = Column(String(80), nullable=False)
    scope = Column(String(16), nullable=False)
    relation_kind = Column(String(32), nullable=False)
    relation_code = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    from_skill_id = Column(BigInteger, ForeignKey("skills.id"), nullable=True)
    to_skill_id = Column(BigInteger, ForeignKey("skills.id"), nullable=True)
    question_id = Column(BigInteger, ForeignKey("questions.id"), nullable=True)
    language_item_id = Column(
        BigInteger, ForeignKey("language_items.id"), nullable=True
    )
    option_letter = Column(String(1), nullable=True)
    segment_id = Column(BigInteger, ForeignKey("transcript_segments.id"), nullable=True)
    evidence_id = Column(BigInteger, ForeignKey("evidence_items.id"), nullable=True)
    role = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=True)
    attributes_json = Column(JSONB, nullable=True)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("id", "batch_id"),
        ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_evidence_items_segment_id_batch",
        ),
        ForeignKeyConstraint(
            ["passage_id", "batch_id"],
            ["passages.id", "passages.batch_id"],
            name="fk_evidence_items_passage_id_batch",
        ),
    )
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    passage_id = Column(BigInteger, ForeignKey("passages.id"), nullable=False)
    segment_id = Column(BigInteger, ForeignKey("transcript_segments.id"), nullable=True)
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    evidence_text = Column(Text, nullable=False)
    evidence_type = Column(String(32), nullable=False)
    source = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    collector = Column(String(64), nullable=True)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSONB, nullable=True)


class ClassificationDict(Base):
    __tablename__ = "classification_dicts"
    __table_args__ = (UniqueConstraint("snapshot_id", "classification_code"),)
    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(
        BigInteger, ForeignKey("dictionary_snapshots.id"), nullable=False
    )
    dict_kind = Column(String(32), nullable=False)
    classification_code = Column(String(64), nullable=False)
    classification_name = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    decision_rule = Column(Text, nullable=True)
    exclude_rule = Column(Text, nullable=True)
    typical_example = Column(Text, nullable=True)
    status = Column(String(32), nullable=False)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSONB, nullable=True)


class ErrorCause(Base):
    __tablename__ = "error_causes"
    __table_args__ = (UniqueConstraint("snapshot_id", "error_cause_code"),)
    id = Column(BigInteger, primary_key=True)
    snapshot_id = Column(
        BigInteger, ForeignKey("dictionary_snapshots.id"), nullable=False
    )
    error_cause_code = Column(String(64), nullable=False)
    display_code = Column(String(64), nullable=False)
    legacy_codes = Column(String(64), nullable=True)
    cause_level = Column(Integer, nullable=False)
    parent_error_cause_id = Column(
        BigInteger, ForeignKey("error_causes.id"), nullable=True
    )
    cause_name = Column(Text, nullable=False)
    definition = Column(Text, nullable=False)
    confirmation_rule = Column(Text, nullable=True)
    display_mapping = Column(String(32), nullable=True)
    boundary_rule = Column(Text, nullable=True)
    remedy_hint = Column(Text, nullable=True)
    maturity = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSONB, nullable=True)


class LanguageItem(Base):
    __tablename__ = "language_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "item_code"),
        UniqueConstraint(
            "batch_id",
            "item_type",
            "normalized_text",
            "sense",
            name="uq_language_items_sense",
        ),
        UniqueConstraint("id", "batch_id"),
    )
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    normalized_text = Column(Text, nullable=False)
    item_code = Column(String(64), nullable=False)
    item_type = Column(String(32), nullable=False)
    item_text = Column(Text, nullable=False)
    lemma = Column(Text, nullable=True)
    sense = Column(Text, nullable=False)
    status = Column(String(32), nullable=False)
    collector = Column(String(64), nullable=False)
    review_status = Column(String(32), nullable=False, default="待审核")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSONB, nullable=True)


class EvidenceSegment(Base):
    __tablename__ = "evidence_segments"
    __table_args__ = (
        UniqueConstraint("evidence_id", "sort_order"),
        UniqueConstraint(
            "evidence_id", "segment_id", name="uq_evidence_segments_segment"
        ),
        ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_evidence_segments_evidence_id_batch",
        ),
        ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_evidence_segments_segment_id_batch",
        ),
        ForeignKeyConstraint(
            ["passage_id", "batch_id"],
            ["passages.id", "passages.batch_id"],
            name="fk_evidence_segments_passage_id_batch",
        ),
        CheckConstraint(
            "(start_char IS NULL AND end_char IS NULL) OR "
            "(start_char >= 0 AND end_char > start_char)",
            name="char_range",
        ),
    )
    id = Column(BigInteger, primary_key=True)
    evidence_id = Column(BigInteger, nullable=False)
    batch_id = Column(BigInteger, ForeignKey("import_batches.id"), nullable=False)
    passage_id = Column(BigInteger, nullable=False)
    segment_id = Column(BigInteger, nullable=False)
    sort_order = Column(Integer, nullable=False)
    start_char = Column(Integer)
    end_char = Column(Integer)
