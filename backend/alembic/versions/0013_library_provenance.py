"""Manual/mixed local execution bindings alongside strict legacy AI receipts."""

from alembic import op
from sqlalchemy import text

revision = "0013_library_provenance"
down_revision = "0012_library_edit_history"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE question_annotation_states
      ADD COLUMN source_type varchar(16) NOT NULL DEFAULT 'AI',
      ADD COLUMN library_save_version_id uuid REFERENCES library_save_versions(id),
      ADD COLUMN origin_task_id uuid REFERENCES processing_tasks(id),
      ALTER COLUMN generation_task_id DROP NOT NULL,
      ALTER COLUMN candidate_artifact_id DROP NOT NULL,
      DROP CONSTRAINT ck_annotation_generation""")
    op.execute("""ALTER TABLE question_annotation_states ADD CONSTRAINT ck_annotation_generation CHECK (
      (source_type='AI' AND generation_task_id IS NOT NULL AND candidate_artifact_id IS NOT NULL AND
       ((rule_version='m3.option-errors.v1' AND generation_state IN ('generated','generated_empty'))
        OR (rule_version='m3.option-errors.v2' AND generation_state IN ('generated_nonempty','generated_empty','generation_incomplete'))))
      OR (source_type IN ('MANUAL','MIXED') AND rule_version='m3.option-errors.v2'
          AND generation_state IN ('manual_nonempty','manual_empty','mixed_nonempty','mixed_empty')
          AND library_save_version_id IS NOT NULL AND origin_task_id IS NOT NULL
          AND generation_task_id IS NULL AND candidate_artifact_id IS NULL))""")
    # Preserve the entire deployed legacy checks, expanding only explicit source
    # states. Their own receipt joins continue checking every AI row unchanged.
    connection = op.get_bind()
    definition = connection.execute(
        text("SELECT pg_get_functiondef('m3_check_option_error_batch()'::regprocedure)")
    ).scalar_one()
    definition = definition.replace(
        "s.generation_state NOT IN ('generated','generated_nonempty')",
        "s.generation_state NOT IN ('generated','generated_nonempty','manual_nonempty','mixed_nonempty')",
    )
    op.execute(definition)
    op.execute("""CREATE FUNCTION library_check_published_sources() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE b bigint;
    BEGIN
      FOR b IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP<>'INSERT' THEN (to_jsonb(OLD)->>'batch_id')::bigint ELSE NULL END,
        CASE WHEN TG_OP<>'DELETE' THEN (to_jsonb(NEW)->>'batch_id')::bigint ELSE NULL END]) x
        WHERE x IS NOT NULL ORDER BY x
      LOOP
        IF EXISTS (
          SELECT 1 FROM question_annotation_states s
          LEFT JOIN library_save_versions v ON v.id=s.library_save_version_id
          LEFT JOIN processing_workflow_revisions r ON r.id=s.revision_id
          LEFT JOIN processing_tasks t ON t.id=s.origin_task_id
          LEFT JOIN processing_drafts d ON d.task_id=t.id AND d.view='final'
          LEFT JOIN import_batches ib ON ib.id=s.batch_id
          LEFT JOIN processing_review_sessions rs ON rs.id=s.review_session_id
          WHERE s.batch_id=b AND s.source_type IN ('MANUAL','MIXED') AND (
            v.id IS NULL OR v.snapshot_pruned_at IS NOT NULL OR v.exam_paper_id<>ib.exam_paper_id
            OR v.revision_id<>r.id OR r.workflow_contract<>'library.v1'
            OR t.id IS DISTINCT FROM r.final_task_id OR t.revision_id<>r.id
            OR d.result_hash IS DISTINCT FROM s.result_hash OR rs.state<>'approved'
            OR d.payload->'library_provenance'->>'save_version_id' IS DISTINCT FROM v.id::text
            OR d.payload->'library_provenance'->>'content_hash' IS DISTINCT FROM v.content_hash
            OR (SELECT count(*) FROM question_distractor_assessments a WHERE a.batch_id=b AND a.question_id=s.question_id)<>3
            OR EXISTS (SELECT 1 FROM question_distractor_assessments a
              JOIN questions q ON q.id=a.question_id
              WHERE a.batch_id=b AND a.question_id=s.question_id AND (
                a.option_letter=q.correct_option OR a.status='INSUFFICIENT_EVIDENCE'
                OR (a.status='SUPPORTED') IS DISTINCT FROM EXISTS (
                  SELECT 1 FROM error_question_relations e WHERE e.batch_id=b AND e.question_id=s.question_id
                  AND e.option_letter=a.option_letter AND e.relation_kind='QUESTION_ERROR_CANDIDATE')
                OR a.source_candidate_hash IS DISTINCT FROM (d.payload->'library_provenance'->'annotation_hashes'->>(
                  SELECT i.src_id FROM processing_batch_identities i WHERE i.batch_id=b AND i.entity_type='questions' AND i.entity_id=s.question_id))))
            OR (s.generation_state IN ('manual_empty','mixed_empty')) IS DISTINCT FROM NOT EXISTS(
              SELECT 1 FROM question_distractor_assessments a WHERE a.batch_id=b AND a.question_id=s.question_id AND a.status='SUPPORTED')
          )
        ) THEN RAISE EXCEPTION 'library published source/review binding invalid'; END IF;
      END LOOP;
      RETURN NULL;
    END $$""")
    for table in (
        "question_annotation_states",
        "question_distractor_assessments",
        "error_question_relations",
    ):
        op.execute(
            f"CREATE CONSTRAINT TRIGGER library_sources_{table} AFTER INSERT OR UPDATE OR DELETE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION library_check_published_sources()"
        )


def downgrade():
    raise RuntimeError(
        "Preserve manual provenance; disable library routes for app rollback"
    )
