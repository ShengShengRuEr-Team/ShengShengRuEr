"""Version-gated option errors, generation receipts and deferred relation checks."""

from alembic import op

revision = "0009_m3_error_invariants"
down_revision = "0008_m3_continuation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
ALTER TABLE error_question_relations
  ADD COLUMN rule_version varchar(32) NOT NULL DEFAULT 'legacy',
  ADD COLUMN business_eligible boolean NOT NULL DEFAULT false,
  ADD CONSTRAINT ck_option_error_version CHECK (
    rule_version IN ('legacy','m3.option-errors.v1') AND
    business_eligible = (rule_version = 'm3.option-errors.v1'));
CREATE UNIQUE INDEX uq_option_error_identity ON error_question_relations
  (batch_id, question_id, option_letter, error_cause_id, rule_version)
  WHERE business_eligible AND is_current AND relation_kind='QUESTION_ERROR_CANDIDATE';
ALTER TABLE processing_artifacts ADD CONSTRAINT uq_artifact_task UNIQUE (id, task_id);
ALTER TABLE processing_tasks ADD CONSTRAINT uq_task_revision UNIQUE (id, revision_id);
CREATE TABLE processing_batch_identities (
  batch_id bigint NOT NULL REFERENCES import_batches(id),
  entity_type varchar(40) NOT NULL,
  src_id varchar(128) NOT NULL,
  entity_id bigint NOT NULL,
  PRIMARY KEY(batch_id,entity_type,src_id),
  UNIQUE(batch_id,entity_type,entity_id)
);
CREATE TABLE question_annotation_states (
  batch_id bigint NOT NULL REFERENCES import_batches(id),
  question_id bigint NOT NULL,
  revision_id uuid NOT NULL REFERENCES processing_workflow_revisions(id),
  result_hash varchar(64) NOT NULL,
  rule_version varchar(32) NOT NULL CHECK (rule_version='m3.option-errors.v1'),
  rules_manifest_hash varchar(64) NOT NULL,
  question_input_hash varchar(64) NOT NULL,
  generation_state varchar(32) NOT NULL CHECK (generation_state IN ('generated','generated_empty')),
  generation_task_id uuid NOT NULL REFERENCES processing_tasks(id),
  candidate_artifact_id bigint NOT NULL,
  review_session_id uuid NOT NULL,
  PRIMARY KEY (batch_id, question_id),
  FOREIGN KEY (question_id,batch_id) REFERENCES questions(id,batch_id),
  FOREIGN KEY (candidate_artifact_id,generation_task_id) REFERENCES processing_artifacts(id,task_id),
  FOREIGN KEY (review_session_id,revision_id,result_hash)
    REFERENCES processing_review_sessions(id,revision_id,result_hash)
);
CREATE FUNCTION m3_check_option_error_batch() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE b bigint;
BEGIN
  FOR b IN SELECT DISTINCT x FROM unnest(ARRAY[
    CASE WHEN TG_OP <> 'INSERT' THEN OLD.batch_id ELSE NULL END,
    CASE WHEN TG_OP <> 'DELETE' THEN NEW.batch_id ELSE NULL END]) AS x
    WHERE x IS NOT NULL ORDER BY x
  LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended('m3-option-errors:' || b::text,0));
    IF EXISTS (
      SELECT 1 FROM error_question_relations r
      LEFT JOIN questions q ON q.id=r.question_id AND q.batch_id=r.batch_id
      LEFT JOIN question_annotation_states s ON s.question_id=q.id AND s.batch_id=q.batch_id
      WHERE r.batch_id=b AND r.business_eligible AND r.relation_kind='QUESTION_ERROR_CANDIDATE'
        AND (q.id IS NULL OR r.option_letter IS NULL OR r.option_letter NOT IN ('A','B','C','D')
          OR r.option_letter=q.correct_option OR s.question_id IS NULL
          OR s.generation_state <> 'generated'
          OR NOT EXISTS (SELECT 1 FROM error_question_relations c
              WHERE c.owner_relation_id=r.id AND c.relation_kind='CANDIDATE_EVIDENCE'))
    ) THEN RAISE EXCEPTION 'invalid option error parent or missing generation/evidence'; END IF;
    IF EXISTS (
      SELECT 1 FROM error_question_relations c
      LEFT JOIN error_question_relations p ON p.id=c.owner_relation_id
      LEFT JOIN questions q ON q.id=p.question_id
      LEFT JOIN evidence_items e ON e.id=c.evidence_id
      WHERE (c.batch_id=b OR p.batch_id=b) AND c.relation_kind='CANDIDATE_EVIDENCE'
        AND (c.business_eligible OR p.business_eligible)
        AND (p.id IS NULL OR p.relation_kind <> 'QUESTION_ERROR_CANDIDATE'
          OR NOT p.business_eligible OR NOT c.business_eligible
          OR p.rule_version IS DISTINCT FROM c.rule_version OR p.batch_id<>c.batch_id
          OR c.option_letter IS NOT NULL OR e.id IS NULL OR e.batch_id<>p.batch_id
          OR e.passage_id<>q.passage_id
          OR NOT EXISTS (SELECT 1 FROM evidence_segments es WHERE es.evidence_id=e.id)
          OR EXISTS (SELECT 1 FROM evidence_segments es
              JOIN transcript_segments ts ON ts.id=es.segment_id
              WHERE es.evidence_id=e.id AND (es.batch_id<>p.batch_id
                OR es.passage_id<>q.passage_id OR ts.passage_id<>q.passage_id
                OR ts.segment_type<>'body')))
    ) THEN RAISE EXCEPTION 'invalid option error evidence owner, rule or passage'; END IF;
    IF EXISTS (
      SELECT 1 FROM question_annotation_states s
      JOIN processing_workflow_revisions r ON r.id=s.revision_id
      JOIN processing_workflows w ON w.id=r.workflow_id
      JOIN import_batches ib ON ib.id=s.batch_id
      JOIN processing_tasks t ON t.id=s.generation_task_id
      JOIN processing_review_sessions rs ON rs.id=s.review_session_id
      WHERE s.batch_id=b AND (r.final_result_hash<>s.result_hash
        OR t.workflow_id IS DISTINCT FROM w.id
        OR NOT EXISTS (WITH RECURSIVE lineage AS (
          SELECT id,parent_revision_id FROM processing_workflow_revisions WHERE id=s.revision_id
          UNION ALL SELECT p.id,p.parent_revision_id FROM processing_workflow_revisions p
            JOIN lineage l ON p.id=l.parent_revision_id)
          SELECT 1 FROM lineage WHERE id=t.revision_id)
        OR w.exam_paper_id IS DISTINCT FROM ib.exam_paper_id OR rs.state<>'approved'
        OR (s.generation_state='generated_empty' AND EXISTS (
          SELECT 1 FROM error_question_relations p WHERE p.batch_id=b AND p.question_id=s.question_id
            AND p.business_eligible AND p.relation_kind='QUESTION_ERROR_CANDIDATE')))
    ) THEN RAISE EXCEPTION 'annotation generation/review identity mismatch'; END IF;
  END LOOP;
  RETURN NULL;
END;
$$;
CREATE FUNCTION m3_freeze_approved_reviews() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='processing_review_sessions' THEN
    IF OLD.state='approved' THEN RAISE EXCEPTION 'approved review session is immutable'; END IF;
  ELSE
    IF EXISTS(SELECT 1 FROM processing_review_sessions WHERE id=OLD.session_id AND state='approved')
      THEN RAISE EXCEPTION 'approved review items are immutable'; END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER m3_freeze_session BEFORE UPDATE OR DELETE ON processing_review_sessions
  FOR EACH ROW EXECUTE FUNCTION m3_freeze_approved_reviews();
CREATE TRIGGER m3_freeze_review_item BEFORE UPDATE OR DELETE ON processing_review_items
  FOR EACH ROW EXECUTE FUNCTION m3_freeze_approved_reviews();
    """)
    for table in (
        "error_question_relations",
        "evidence_items",
        "evidence_segments",
        "questions",
        "transcript_segments",
        "question_annotation_states",
    ):
        op.execute(f"""CREATE CONSTRAINT TRIGGER m3_option_errors_{table}
            AFTER INSERT OR UPDATE OR DELETE ON {table}
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION m3_check_option_error_batch()""")


def downgrade():
    # Version gating must never be removed from a database with continuation data.
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM question_annotation_states) OR EXISTS(
        SELECT 1 FROM error_question_relations WHERE business_eligible) THEN
        RAISE EXCEPTION 'restore a verified backup; new annotation history cannot be erased';
      END IF;
    END $$;""")
    op.execute("DROP FUNCTION m3_check_option_error_batch() CASCADE")
    op.execute("DROP FUNCTION m3_freeze_approved_reviews() CASCADE")
    op.drop_table("question_annotation_states")
    op.drop_table("processing_batch_identities")
    op.execute("ALTER TABLE processing_tasks DROP CONSTRAINT uq_task_revision")
    op.execute("ALTER TABLE processing_artifacts DROP CONSTRAINT uq_artifact_task")
    op.execute("DROP INDEX uq_option_error_identity")
    op.execute(
        "ALTER TABLE error_question_relations DROP CONSTRAINT ck_option_error_version"
    )
    op.execute(
        "ALTER TABLE error_question_relations DROP COLUMN rule_version, DROP COLUMN business_eligible"
    )
