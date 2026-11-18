"""V7 assessment coverage, comparison evidence references and version guards."""

from alembic import op
from sqlalchemy import text

revision = "0010_m3_distractor_coverage"
down_revision = "0009_m3_error_invariants"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
ALTER TABLE error_question_relations DROP CONSTRAINT ck_option_error_version;
ALTER TABLE error_question_relations ADD CONSTRAINT ck_option_error_version CHECK (
  rule_version IN ('legacy','m3.option-errors.v1','m3.option-errors.v2') AND
  business_eligible = (rule_version <> 'legacy'));
ALTER TABLE error_question_relations ADD COLUMN personal_verification_needed text;
ALTER TABLE error_question_relations ADD CONSTRAINT ck_v7_personal_verification CHECK (
  rule_version <> 'm3.option-errors.v2' OR relation_kind <> 'QUESTION_ERROR_CANDIDATE'
  OR (personal_verification_needed IS NOT NULL AND length(btrim(personal_verification_needed)) > 0));
DO $$ DECLARE c record; BEGIN
  FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='question_annotation_states'::regclass
    AND contype='c' AND (pg_get_constraintdef(oid) LIKE '%rule_version%'
                     OR pg_get_constraintdef(oid) LIKE '%generation_state%')
  LOOP EXECUTE format('ALTER TABLE question_annotation_states DROP CONSTRAINT %I', c.conname); END LOOP;
END $$;
ALTER TABLE question_annotation_states ADD CONSTRAINT ck_annotation_rule CHECK (
  rule_version IN ('m3.option-errors.v1','m3.option-errors.v2'));
ALTER TABLE question_annotation_states ADD CONSTRAINT ck_annotation_generation CHECK (
  (rule_version='m3.option-errors.v1' AND generation_state IN ('generated','generated_empty'))
  OR (rule_version='m3.option-errors.v2' AND generation_state IN
      ('generated_empty','generated_nonempty','generation_incomplete','generation_failed')));
CREATE TABLE question_distractor_assessments (
  batch_id bigint NOT NULL,
  question_id bigint NOT NULL,
  option_letter varchar(1) NOT NULL CHECK (option_letter IN ('A','B','C','D')),
  rule_version varchar(32) NOT NULL CHECK (rule_version='m3.option-errors.v2'),
  status varchar(32) NOT NULL CHECK(status IN ('SUPPORTED','NO_SUPPORTED_CANDIDATE','INSUFFICIENT_EVIDENCE')),
  reason text NOT NULL CHECK(length(btrim(reason))>0),
  unresolved_points jsonb NOT NULL CHECK(jsonb_typeof(unresolved_points)='array'),
  source_candidate_hash varchar(64) NOT NULL CHECK(source_candidate_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY(batch_id,question_id,option_letter),
  FOREIGN KEY(batch_id,question_id) REFERENCES question_annotation_states(batch_id,question_id),
  CHECK ((status='INSUFFICIENT_EVIDENCE' AND jsonb_array_length(unresolved_points)>0)
      OR (status<>'INSUFFICIENT_EVIDENCE' AND jsonb_array_length(unresolved_points)=0))
);
CREATE TABLE question_distractor_comparison_evidences (
  batch_id bigint NOT NULL,
  question_id bigint NOT NULL,
  option_letter varchar(1) NOT NULL,
  sort_order integer NOT NULL CHECK(sort_order>0),
  evidence_id bigint NOT NULL,
  support_note text,
  PRIMARY KEY(batch_id,question_id,option_letter,sort_order),
  FOREIGN KEY(batch_id,question_id,option_letter)
    REFERENCES question_distractor_assessments(batch_id,question_id,option_letter),
  FOREIGN KEY(evidence_id,batch_id) REFERENCES evidence_items(id,batch_id)
);
CREATE FUNCTION m3_freeze_distractor_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'persisted V7 assessment and comparison evidence are immutable; create a revision'; END $$;
CREATE TRIGGER m3_freeze_assessment BEFORE UPDATE OR DELETE ON question_distractor_assessments
  FOR EACH ROW EXECUTE FUNCTION m3_freeze_distractor_record();
CREATE TRIGGER m3_freeze_comparison BEFORE UPDATE OR DELETE ON question_distractor_comparison_evidences
  FOR EACH ROW EXECUTE FUNCTION m3_freeze_distractor_record();
""")
    # Retain the deployed V1 invariant function and extend its generation enum.
    connection = op.get_bind()
    definition = connection.scalar(text("SELECT pg_get_functiondef('m3_check_option_error_batch()'::regprocedure)"))
    op.execute(definition.replace("s.generation_state <> 'generated'", "s.generation_state NOT IN ('generated','generated_nonempty')"))
    op.execute("""
CREATE FUNCTION m3_check_distractor_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b bigint;
BEGIN
  FOR b IN SELECT DISTINCT x FROM unnest(ARRAY[
    CASE WHEN TG_OP<>'INSERT' THEN (to_jsonb(OLD)->>CASE WHEN TG_TABLE_NAME='import_batches' THEN 'id' ELSE 'batch_id' END)::bigint ELSE NULL END,
    CASE WHEN TG_OP<>'DELETE' THEN (to_jsonb(NEW)->>CASE WHEN TG_TABLE_NAME='import_batches' THEN 'id' ELSE 'batch_id' END)::bigint ELSE NULL END]) x
    WHERE x IS NOT NULL ORDER BY x
  LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('m3-option-errors:' || b::text,0));
    IF EXISTS (
      SELECT 1 FROM import_batches ib JOIN questions q ON q.batch_id=ib.id
      LEFT JOIN question_annotation_states s ON s.batch_id=q.batch_id AND s.question_id=q.id
      WHERE ib.id=b AND ib.source_manifest->'method'->'rules_manifest'->>'error_rule_version'='m3.option-errors.v2'
        AND (s.question_id IS NULL OR s.rule_version<>'m3.option-errors.v2')
    ) THEN RAISE EXCEPTION 'V7 batch requires generation state for every question'; END IF;
    IF EXISTS (
      SELECT 1 FROM question_annotation_states s JOIN questions q ON q.id=s.question_id
      JOIN processing_artifacts pa ON pa.id=s.candidate_artifact_id
      JOIN processing_workflow_revisions wr ON wr.id=s.revision_id
      WHERE s.batch_id=b AND s.rule_version='m3.option-errors.v2' AND (
        s.generation_state NOT IN ('generated_empty','generated_nonempty')
        OR s.rules_manifest_hash IS DISTINCT FROM wr.rules_manifest->>'manifest_hash'
        OR (SELECT count(*) FROM question_distractor_assessments a
            WHERE a.batch_id=b AND a.question_id=q.id)<>3
        OR EXISTS (SELECT 1 FROM question_distractor_assessments a
            WHERE a.batch_id=b AND a.question_id=q.id AND (
              a.option_letter=q.correct_option OR a.status='INSUFFICIENT_EVIDENCE'
              OR (a.status='SUPPORTED') IS DISTINCT FROM EXISTS (
                 SELECT 1 FROM error_question_relations p WHERE p.batch_id=b AND p.question_id=q.id
                 AND p.option_letter=a.option_letter AND p.relation_kind='QUESTION_ERROR_CANDIDATE'
                 AND p.rule_version='m3.option-errors.v2')
              OR a.source_candidate_hash IS DISTINCT FROM (
                SELECT r->>'candidate_hash' FROM processing_drafts d,
                  jsonb_array_elements(d.payload->'generation_receipts') r
                WHERE d.task_id=wr.final_task_id AND d.view='final'
                  AND r->>'question_src_id'=(SELECT i.src_id FROM processing_batch_identities i
                    WHERE i.batch_id=b AND i.entity_type='questions' AND i.entity_id=q.id) LIMIT 1)))
        OR (s.generation_state='generated_empty') IS DISTINCT FROM NOT EXISTS (
          SELECT 1 FROM question_distractor_assessments a WHERE a.batch_id=b
            AND a.question_id=q.id AND a.status='SUPPORTED'))
    ) THEN RAISE EXCEPTION 'V7 incomplete assessments, state, or candidate identity'; END IF;
    IF EXISTS (
      SELECT 1 FROM question_distractor_assessments a
      JOIN question_annotation_states s ON s.batch_id=a.batch_id AND s.question_id=a.question_id
      JOIN processing_workflow_revisions wr ON wr.id=s.revision_id
      JOIN processing_batch_identities qi ON qi.batch_id=a.batch_id
        AND qi.entity_type='questions' AND qi.entity_id=a.question_id
      WHERE a.batch_id=b AND NOT EXISTS (
        SELECT 1 FROM processing_drafts d,
          jsonb_array_elements(d.payload->'distractor_assessments') x
        WHERE d.task_id=wr.final_task_id AND d.view='final'
          AND x->>'question_src_id'=qi.src_id AND x->>'option_letter'=a.option_letter
          AND x->>'status'=a.status AND x->>'reason'=a.reason
          AND x->'unresolved_points'=a.unresolved_points
          AND x->>'source_candidate_hash'=a.source_candidate_hash
          AND jsonb_array_length(x->'comparison_evidence_refs')=(
            SELECT count(*) FROM question_distractor_comparison_evidences c
            WHERE c.batch_id=b AND c.question_id=a.question_id AND c.option_letter=a.option_letter)
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(x->'comparison_evidence_refs') WITH ORDINALITY ref(value,n)
            LEFT JOIN processing_batch_identities ei ON ei.batch_id=b AND ei.entity_type='evidences'
              AND ei.src_id=ref.value->>'evidence_src_id'
            LEFT JOIN question_distractor_comparison_evidences c ON c.batch_id=b
              AND c.question_id=a.question_id AND c.option_letter=a.option_letter AND c.sort_order=ref.n
            WHERE c.evidence_id IS DISTINCT FROM ei.entity_id
              OR c.support_note IS DISTINCT FROM ref.value->>'support_note'))
    ) THEN RAISE EXCEPTION 'V7 assessment or comparison differs from frozen result'; END IF;
    IF EXISTS (
      SELECT 1 FROM error_question_relations p JOIN questions q ON q.id=p.question_id
      LEFT JOIN question_annotation_states s ON s.batch_id=p.batch_id AND s.question_id=q.id
      JOIN error_causes ec ON ec.id=p.error_cause_id
      JOIN dictionary_snapshots ds ON ds.id=ec.snapshot_id
      WHERE p.batch_id=b AND p.rule_version='m3.option-errors.v2'
        AND p.relation_kind='QUESTION_ERROR_CANDIDATE' AND (
          s.rule_version IS DISTINCT FROM p.rule_version OR ds.schema_sha256<>'6348030d2b5acb49e0cf036487f4ddd508428f33b0033e5cfb4261d40a986580'
          OR ec.cause_level<>3 OR ec.status<>'启用'
          OR NOT EXISTS(SELECT 1 FROM question_distractor_assessments a
              WHERE a.batch_id=b AND a.question_id=q.id AND a.option_letter=p.option_letter AND a.status='SUPPORTED'))
    ) THEN RAISE EXCEPTION 'V7 candidate missing matching supported assessment or dictionary'; END IF;
    IF EXISTS (
      SELECT 1 FROM question_distractor_comparison_evidences c
      JOIN evidence_items e ON e.id=c.evidence_id JOIN questions q ON q.id=c.question_id
      WHERE c.batch_id=b AND (e.passage_id<>q.passage_id OR e.batch_id<>b
        OR NOT EXISTS(SELECT 1 FROM evidence_segments es WHERE es.evidence_id=e.id)
        OR EXISTS(SELECT 1 FROM evidence_segments es JOIN transcript_segments ts ON ts.id=es.segment_id
          WHERE es.evidence_id=e.id AND (ts.passage_id<>q.passage_id OR ts.segment_type<>'body'
           OR ts.start_ms<0 OR ts.end_ms<=ts.start_ms)))
    ) THEN RAISE EXCEPTION 'V7 comparison evidence ownership invalid'; END IF;
  END LOOP;
  RETURN NULL;
END $$;
""")
    for table in ("question_distractor_assessments", "question_distractor_comparison_evidences",
                  "question_annotation_states", "error_question_relations", "questions",
                  "evidence_items", "evidence_segments", "transcript_segments", "import_batches"):
        op.execute(f"""CREATE CONSTRAINT TRIGGER m3_distractors_{table}
          AFTER INSERT OR UPDATE OR DELETE ON {table} DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION m3_check_distractor_batch()""")


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM question_distractor_assessments)
        OR EXISTS(SELECT 1 FROM question_annotation_states WHERE rule_version='m3.option-errors.v2')
        OR EXISTS(SELECT 1 FROM error_question_relations WHERE rule_version='m3.option-errors.v2')
      THEN RAISE EXCEPTION 'restore verified backup; V7 audit history cannot be erased'; END IF;
    END $$;""")
    op.execute("DROP FUNCTION m3_check_distractor_batch() CASCADE")
    op.execute("DROP FUNCTION m3_freeze_distractor_record() CASCADE")
    op.drop_table("question_distractor_comparison_evidences")
    op.drop_table("question_distractor_assessments")
    op.execute("ALTER TABLE error_question_relations DROP CONSTRAINT ck_v7_personal_verification, DROP COLUMN personal_verification_needed")
    op.execute("ALTER TABLE error_question_relations DROP CONSTRAINT ck_option_error_version")
    op.execute("ALTER TABLE error_question_relations ADD CONSTRAINT ck_option_error_version CHECK(rule_version IN ('legacy','m3.option-errors.v1') AND business_eligible=(rule_version='m3.option-errors.v1'))")
    op.execute("ALTER TABLE question_annotation_states DROP CONSTRAINT ck_annotation_rule, DROP CONSTRAINT ck_annotation_generation")
    op.execute("ALTER TABLE question_annotation_states ADD CHECK(rule_version='m3.option-errors.v1'), ADD CHECK(generation_state IN ('generated','generated_empty'))")
    definition = op.get_bind().scalar(text("SELECT pg_get_functiondef('m3_check_option_error_batch()'::regprocedure)"))
    op.execute(definition.replace("s.generation_state NOT IN ('generated','generated_nonempty')", "s.generation_state <> 'generated'"))
