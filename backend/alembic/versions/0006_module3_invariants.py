"""Enforce conditional relation shape, scope and immutable automatic drafts."""

from alembic import op

revision = "0006_module3_invariants"
down_revision = "0005_module3_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_skill_question_relations_relation_shape",
        "skill_question_relations",
        "(relation_kind = 'QUESTION_SKILL' AND question_id IS NOT NULL AND skill_id IS NOT NULL AND role IS NOT NULL AND owner_relation_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['annotation_reason','annotation_source','confidence','legacy_tag_code']::text[]) = '{}'::jsonb))) OR (relation_kind = 'SKILL_EVIDENCE' AND owner_relation_id IS NOT NULL AND evidence_id IS NOT NULL AND sort_order IS NOT NULL AND skill_id IS NULL AND question_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['relation_type','support_note']::text[]) = '{}'::jsonb)))",
    )
    op.create_check_constraint(
        "ck_error_question_relations_relation_shape",
        "error_question_relations",
        "(relation_kind = 'QUESTION_ERROR_CANDIDATE' AND question_id IS NOT NULL AND error_cause_id IS NOT NULL AND owner_relation_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['trigger_mechanism','annotation_source','candidate_priority']::text[]) = '{}'::jsonb))) OR (relation_kind = 'CANDIDATE_EVIDENCE' AND owner_relation_id IS NOT NULL AND evidence_id IS NOT NULL AND sort_order IS NOT NULL AND question_id IS NULL AND error_cause_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['support_note']::text[]) = '{}'::jsonb)))",
    )
    op.create_check_constraint(
        "ck_other_relations_relation_shape",
        "other_relations",
        "(relation_kind = 'SKILL_TAXONOMY' AND from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND role IS NOT NULL AND sort_order IS NOT NULL AND segment_id IS NULL AND question_id IS NULL AND language_item_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['display_path','rationale']::text[]) = '{}'::jsonb))) OR (relation_kind = 'SKILL_PREREQUISITE' AND from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND segment_id IS NULL AND question_id IS NULL AND language_item_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[]) = '{}'::jsonb))) OR (relation_kind = 'SKILL_CO_USE' AND from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND segment_id IS NULL AND question_id IS NULL AND language_item_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[]) = '{}'::jsonb))) OR (relation_kind = 'SKILL_SUPPORT' AND from_skill_id IS NOT NULL AND to_skill_id IS NOT NULL AND segment_id IS NULL AND question_id IS NULL AND language_item_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['condition_key','task_condition','rationale','strength','source','valid_from','valid_to']::text[]) = '{}'::jsonb))) OR (relation_kind = 'QUESTION_LANGUAGE_ITEM' AND question_id IS NOT NULL AND language_item_id IS NOT NULL AND from_skill_id IS NULL AND to_skill_id IS NULL AND evidence_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['location_type','context_text','note']::text[]) = '{}'::jsonb))) OR (relation_kind = 'ANSWER_EVIDENCE' AND question_id IS NOT NULL AND evidence_id IS NOT NULL AND sort_order IS NOT NULL AND from_skill_id IS NULL AND to_skill_id IS NULL AND segment_id IS NULL AND language_item_id IS NULL AND (attributes_json IS NULL OR (jsonb_typeof(attributes_json) = 'object' AND (attributes_json - ARRAY['support_note']::text[]) = '{}'::jsonb)))",
    )
    op.create_check_constraint(
        "ck_other_relations_scope_identity",
        "other_relations",
        "(scope = 'batch' AND batch_id IS NOT NULL AND snapshot_id IS NULL AND scope_key = 'batch:' || batch_id::text) OR (scope = 'snapshot' AND batch_id IS NULL AND snapshot_id IS NOT NULL AND scope_key = 'snapshot:' || snapshot_id::text)",
    )
    op.create_check_constraint(
        "ck_other_relations_scope_kind",
        "other_relations",
        "(scope = 'snapshot' AND relation_kind IN ('SKILL_TAXONOMY','SKILL_PREREQUISITE','SKILL_CO_USE','SKILL_SUPPORT')) OR (scope = 'batch' AND relation_kind IN ('QUESTION_LANGUAGE_ITEM','ANSWER_EVIDENCE'))",
    )
    op.execute("""
CREATE FUNCTION m3_immutable_auto_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.view = 'auto_draft' THEN
    RAISE EXCEPTION 'automatic draft is immutable';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER m3_immutable_auto_draft BEFORE UPDATE OR DELETE ON processing_drafts
FOR EACH ROW EXECUTE FUNCTION m3_immutable_auto_draft();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER m3_immutable_auto_draft ON processing_drafts")
    op.execute("DROP FUNCTION m3_immutable_auto_draft()")
    op.drop_constraint(
        "ck_other_relations_scope_kind", "other_relations", type_="check"
    )
    op.drop_constraint(
        "ck_other_relations_scope_identity", "other_relations", type_="check"
    )
    op.drop_constraint(
        "ck_other_relations_relation_shape", "other_relations", type_="check"
    )
    op.drop_constraint(
        "ck_error_question_relations_relation_shape",
        "error_question_relations",
        type_="check",
    )
    op.drop_constraint(
        "ck_skill_question_relations_relation_shape",
        "skill_question_relations",
        type_="check",
    )
