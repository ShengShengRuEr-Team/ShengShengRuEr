"""Library edit history and archive metadata; legacy results remain untouched."""

from alembic import op

revision = "0012_library_edit_history"
down_revision = "0011_skill_error_query_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE exam_papers ADD COLUMN archived_at timestamptz, ADD COLUMN archived_by bigint REFERENCES users(id), ADD COLUMN archive_reason text, ADD COLUMN library_row_version integer NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE processing_workflows ADD CONSTRAINT uq_workflow_id_paper UNIQUE (id, exam_paper_id)"
    )
    op.execute(
        "ALTER TABLE processing_workflow_revisions ADD COLUMN workflow_contract varchar(32) NOT NULL DEFAULT 'legacy', ADD COLUMN origin_manifest jsonb NOT NULL DEFAULT '{}', ADD COLUMN method_manifest_hash varchar(64)"
    )
    op.execute(
        "\nCREATE TABLE library_save_versions (\n\tid UUID NOT NULL, \n\texam_paper_id BIGINT NOT NULL, \n\tworkflow_id UUID NOT NULL, \n\trevision_id UUID NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tparent_version_id UUID, \n\trestored_from_version_id UUID, \n\treason TEXT NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\tsaved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\torigin_type VARCHAR(16) NOT NULL, \n\tbefore_hash VARCHAR(64) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tsnapshot JSONB, \n\tdiff_summary JSONB NOT NULL, \n\tdependency_manifest JSONB NOT NULL, \n\tunprotected_at TIMESTAMP WITH TIME ZONE, \n\tsnapshot_pruned_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT pk_library_save_versions PRIMARY KEY (id), \n\tCONSTRAINT uq_library_save_versions_id UNIQUE (id, exam_paper_id, workflow_id), \n\tCONSTRAINT uq_library_save_versions_exam_paper_id UNIQUE (exam_paper_id, version_no), \n\tCONSTRAINT fk_library_save_paper_workflow FOREIGN KEY(workflow_id, exam_paper_id) REFERENCES processing_workflows (id, exam_paper_id), \n\tCONSTRAINT fk_library_save_revision FOREIGN KEY(revision_id, workflow_id) REFERENCES processing_workflow_revisions (id, workflow_id), \n\tCONSTRAINT fk_library_save_parent FOREIGN KEY(parent_version_id, exam_paper_id, workflow_id) REFERENCES library_save_versions (id, exam_paper_id, workflow_id), \n\tCONSTRAINT ck_library_save_versions_version_positive CHECK (version_no > 0), \n\tCONSTRAINT ck_library_save_versions_origin CHECK (origin_type IN ('AI','MANUAL','MIXED')), \n\tCONSTRAINT fk_library_save_versions_exam_paper_id_exam_papers FOREIGN KEY(exam_paper_id) REFERENCES exam_papers (id), \n\tCONSTRAINT fk_library_save_versions_restored_from_version_id_libra_189c FOREIGN KEY(restored_from_version_id) REFERENCES library_save_versions (id), \n\tCONSTRAINT fk_library_save_versions_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_library_save_retention ON library_save_versions (unprotected_at)"
    )
    op.execute(
        "\nCREATE TABLE library_edit_heads (\n\texam_paper_id BIGINT NOT NULL, \n\tworkflow_id UUID NOT NULL, \n\trevision_id UUID NOT NULL, \n\tcurrent_save_version_id UUID, \n\trow_version INTEGER NOT NULL, \n\tbaseline JSONB NOT NULL, \n\tbaseline_manifest JSONB NOT NULL, \n\tCONSTRAINT pk_library_edit_heads PRIMARY KEY (exam_paper_id), \n\tCONSTRAINT uq_library_edit_heads_workflow_id UNIQUE (workflow_id), \n\tCONSTRAINT fk_library_head_paper_workflow FOREIGN KEY(workflow_id, exam_paper_id) REFERENCES processing_workflows (id, exam_paper_id), \n\tCONSTRAINT fk_library_head_revision FOREIGN KEY(revision_id, workflow_id) REFERENCES processing_workflow_revisions (id, workflow_id), \n\tCONSTRAINT fk_library_head_save FOREIGN KEY(current_save_version_id, exam_paper_id, workflow_id) REFERENCES library_save_versions (id, exam_paper_id, workflow_id), \n\tCONSTRAINT ck_library_edit_heads_row_version CHECK (row_version > 0), \n\tCONSTRAINT fk_library_edit_heads_exam_paper_id_exam_papers FOREIGN KEY(exam_paper_id) REFERENCES exam_papers (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE library_edit_changes (\n\tid BIGSERIAL NOT NULL, \n\tsave_version_id UUID NOT NULL, \n\tsequence_no INTEGER NOT NULL, \n\tchanges JSONB NOT NULL, \n\tprovenance JSONB NOT NULL, \n\tparent_hash VARCHAR(64) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\treason TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_library_edit_changes PRIMARY KEY (id), \n\tCONSTRAINT uq_library_edit_changes_save_version_id UNIQUE (save_version_id, sequence_no), \n\tCONSTRAINT fk_library_edit_changes_save_version_id_library_save_versions FOREIGN KEY(save_version_id) REFERENCES library_save_versions (id), \n\tCONSTRAINT fk_library_edit_changes_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE library_version_references (\n\tid BIGSERIAL NOT NULL, \n\tsave_version_id UUID NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\treference VARCHAR(255) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\treleased_at TIMESTAMP WITH TIME ZONE, \n\tCONSTRAINT pk_library_version_references PRIMARY KEY (id), \n\tCONSTRAINT uq_library_version_references_save_version_id UNIQUE (save_version_id, kind, reference), \n\tCONSTRAINT fk_library_version_references_save_version_id_library_s_cf4e FOREIGN KEY(save_version_id) REFERENCES library_save_versions (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE library_retention_events (\n\tid UUID NOT NULL, \n\tsave_version_id UUID NOT NULL, \n\tstate VARCHAR(32) NOT NULL, \n\tdetail JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_library_retention_events PRIMARY KEY (id), \n\tCONSTRAINT fk_library_retention_events_save_version_id_library_sav_07e7 FOREIGN KEY(save_version_id) REFERENCES library_save_versions (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE processing_annotation_candidates (\n\tid UUID NOT NULL, \n\tworkflow_id UUID NOT NULL, \n\trevision_id UUID NOT NULL, \n\tquestion_src_id VARCHAR(255) NOT NULL, \n\tmethod_hash VARCHAR(64) NOT NULL, \n\tdependency_hash VARCHAR(64) NOT NULL, \n\tcandidate_hash VARCHAR(64) NOT NULL, \n\tpayload JSONB NOT NULL, \n\treceipt JSONB NOT NULL, \n\tvalidation JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_processing_annotation_candidates PRIMARY KEY (id), \n\tCONSTRAINT fk_library_candidate_revision FOREIGN KEY(revision_id, workflow_id) REFERENCES processing_workflow_revisions (id, workflow_id), \n\tCONSTRAINT uq_processing_annotation_candidates_revision_id UNIQUE (revision_id, question_src_id, candidate_hash)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_exam_papers_library_cursor ON exam_papers(updated_at DESC,id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_exam_papers_library_archived ON exam_papers(archived_at)"
    )
    op.execute(
        "ALTER TABLE library_save_versions ADD COLUMN source_context jsonb NOT NULL DEFAULT '{}'"
    )
    op.execute("""CREATE FUNCTION library_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'library audit and candidate rows are immutable'; END $$""")
    for table in ("library_edit_changes", "processing_annotation_candidates"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION library_immutable_row()"
        )
    op.execute("""CREATE FUNCTION library_save_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'save summaries cannot be deleted'; END IF;
      IF (to_jsonb(NEW) - ARRAY['unprotected_at','snapshot_pruned_at','snapshot']) IS DISTINCT FROM
         (to_jsonb(OLD) - ARRAY['unprotected_at','snapshot_pruned_at','snapshot'])
         OR (NEW.snapshot IS DISTINCT FROM OLD.snapshot AND NOT (NEW.snapshot IS NULL AND NEW.snapshot_pruned_at IS NOT NULL))
         OR (OLD.snapshot_pruned_at IS NOT NULL AND NEW.snapshot_pruned_at IS DISTINCT FROM OLD.snapshot_pruned_at)
      THEN RAISE EXCEPTION 'save content is immutable'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER library_save_immutable BEFORE UPDATE OR DELETE ON library_save_versions FOR EACH ROW EXECUTE FUNCTION library_save_immutable()"
    )


def downgrade():
    raise RuntimeError(
        "Disable library entry points to roll back the app; retain saved history"
    )
