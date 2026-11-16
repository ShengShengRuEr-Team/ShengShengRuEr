"""Add durable workflow identities, uploads, commands and review records.

SQL is frozen here; migration execution does not import application models.
Downgrade refuses to erase continuation records. Restore a verified backup instead.
"""

from alembic import op
from sqlalchemy import text

revision = "0008_m3_continuation"
down_revision = "0007_m3_attempt_merge"
branch_labels = None
depends_on = None

UPGRADE_SQL = [
    """ALTER TABLE processing_tasks ADD COLUMN workflow_id UUID, ADD COLUMN revision_id UUID""",
    """ALTER TABLE processing_tasks DROP CONSTRAINT ck_processing_tasks_state""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT ck_processing_tasks_state CHECK (state IN ('pending','running','failed','awaiting_confirmation','completed','stopping','stopped'))""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT uq_processing_tasks_id_revision_workflow UNIQUE (id, revision_id, workflow_id)""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT ck_processing_tasks_workflow_binding CHECK ((workflow_id IS NULL) = (revision_id IS NULL))""",
    """CREATE TABLE processing_workflows (
	id UUID NOT NULL,
	exam_level VARCHAR(32) NOT NULL,
	exam_year INTEGER NOT NULL,
	exam_month INTEGER NOT NULL,
	paper_set INTEGER NOT NULL,
	content_scope VARCHAR(16) NOT NULL,
	exam_paper_id BIGINT,
	current_revision_id UUID,
	current_task_id UUID,
	row_version INTEGER NOT NULL,
	processing_state VARCHAR(32) NOT NULL,
	content_review_state VARCHAR(32) NOT NULL,
	error_review_state VARCHAR(32) NOT NULL,
	publication_state VARCHAR(32) NOT NULL,
	created_by BIGINT NOT NULL,
	updated_by BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_workflows PRIMARY KEY (id),
	CONSTRAINT uq_processing_workflows_exam_level UNIQUE (exam_level, exam_year, exam_month, paper_set, content_scope),
	CONSTRAINT ck_processing_workflows_row_version CHECK (row_version > 0),
	CONSTRAINT ck_processing_workflows_identity CHECK (exam_level IN ('CET4','CET6') AND exam_year BETWEEN 1980 AND 2200 AND exam_month BETWEEN 1 AND 12 AND paper_set > 0 AND content_scope = 'listening'),
	CONSTRAINT fk_processing_workflows_exam_paper_id_exam_papers FOREIGN KEY(exam_paper_id) REFERENCES exam_papers (id),
	CONSTRAINT fk_processing_workflows_created_by_users FOREIGN KEY(created_by) REFERENCES users (id),
	CONSTRAINT fk_processing_workflows_updated_by_users FOREIGN KEY(updated_by) REFERENCES users (id)
)""",
    """CREATE TABLE processing_workflow_revisions (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	revision_no INTEGER NOT NULL,
	parent_revision_id UUID,
	reason TEXT NOT NULL,
	document_mode VARCHAR(16) NOT NULL,
	listening_pages JSONB NOT NULL,
	materials_manifest JSONB NOT NULL,
	rules_manifest JSONB NOT NULL,
	stage_fingerprints JSONB NOT NULL,
	materials_hash VARCHAR(64),
	materials_frozen_at TIMESTAMP WITH TIME ZONE,
	final_task_id UUID,
	final_result_hash VARCHAR(64),
	final_frozen_at TIMESTAMP WITH TIME ZONE,
	batch_id BIGINT,
	created_by BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_workflow_revisions PRIMARY KEY (id),
	CONSTRAINT uq_processing_workflow_revisions_id UNIQUE (id, workflow_id),
	CONSTRAINT uq_processing_workflow_revisions_workflow_id UNIQUE (workflow_id, revision_no),
	CONSTRAINT fk_revision_parent FOREIGN KEY(parent_revision_id, workflow_id) REFERENCES processing_workflow_revisions (id, workflow_id),
	CONSTRAINT ck_processing_workflow_revisions_revision_no CHECK (revision_no > 0),
	CONSTRAINT ck_processing_workflow_revisions_final_identity CHECK ((final_result_hash IS NULL) = (final_frozen_at IS NULL)),
	CONSTRAINT fk_processing_workflow_revisions_workflow_id_processing_e3a0 FOREIGN KEY(workflow_id) REFERENCES processing_workflows (id),
	CONSTRAINT fk_processing_workflow_revisions_batch_id_import_batches FOREIGN KEY(batch_id) REFERENCES import_batches (id),
	CONSTRAINT fk_processing_workflow_revisions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
)""",
    """CREATE TABLE processing_review_sessions (
	id UUID NOT NULL,
	revision_id UUID NOT NULL,
	result_hash VARCHAR(64) NOT NULL,
	state VARCHAR(16) NOT NULL,
	row_version INTEGER NOT NULL,
	submitted_by BIGINT,
	submitted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_review_sessions PRIMARY KEY (id),
	CONSTRAINT uq_processing_review_sessions_revision_id UNIQUE (revision_id, result_hash),
	CONSTRAINT uq_processing_review_sessions_id UNIQUE (id, revision_id, result_hash),
	CONSTRAINT ck_processing_review_sessions_state CHECK (state IN ('draft','returned','approved')),
	CONSTRAINT ck_processing_review_sessions_row_version CHECK (row_version > 0),
	CONSTRAINT fk_processing_review_sessions_revision_id_processing_wo_fd2d FOREIGN KEY(revision_id) REFERENCES processing_workflow_revisions (id),
	CONSTRAINT fk_processing_review_sessions_submitted_by_users FOREIGN KEY(submitted_by) REFERENCES users (id)
)""",
    """CREATE TABLE processing_stage_approvals (
	id UUID NOT NULL,
	revision_id UUID NOT NULL,
	stage VARCHAR(32) NOT NULL,
	artifact_hash VARCHAR(64) NOT NULL,
	dependency_hash VARCHAR(64) NOT NULL,
	decision VARCHAR(16) NOT NULL,
	items JSONB NOT NULL,
	reused_approval_id UUID,
	operator_user_id BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_stage_approvals PRIMARY KEY (id),
	CONSTRAINT fk_processing_stage_approvals_revision_id_processing_wo_8bd2 FOREIGN KEY(revision_id) REFERENCES processing_workflow_revisions (id),
	CONSTRAINT fk_processing_stage_approvals_reused_approval_id_proces_5bd8 FOREIGN KEY(reused_approval_id) REFERENCES processing_stage_approvals (id),
	CONSTRAINT fk_processing_stage_approvals_operator_user_id_users FOREIGN KEY(operator_user_id) REFERENCES users (id)
)""",
    """CREATE TABLE processing_workflow_commands (
	id UUID NOT NULL,
	workflow_id UUID NOT NULL,
	revision_id UUID NOT NULL,
	action VARCHAR(64) NOT NULL,
	idempotency_key UUID NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	request JSONB NOT NULL,
	expected_workflow_version INTEGER,
	state VARCHAR(16) NOT NULL,
	result JSONB NOT NULL,
	failure_code VARCHAR(64),
	execution_token UUID,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	retry_of_operation_id UUID,
	created_by BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_workflow_commands PRIMARY KEY (id),
	CONSTRAINT uq_processing_workflow_commands_created_by UNIQUE (created_by, action, idempotency_key),
	CONSTRAINT fk_command_revision FOREIGN KEY(revision_id, workflow_id) REFERENCES processing_workflow_revisions (id, workflow_id),
	CONSTRAINT ck_processing_workflow_commands_state CHECK (state IN ('accepted','running','waiting','succeeded','failed','conflict','stopped')),
	CONSTRAINT fk_processing_workflow_commands_workflow_id_processing__0c9c FOREIGN KEY(workflow_id) REFERENCES processing_workflows (id),
	CONSTRAINT fk_processing_workflow_commands_retry_of_operation_id_p_7684 FOREIGN KEY(retry_of_operation_id) REFERENCES processing_workflow_commands (id),
	CONSTRAINT fk_processing_workflow_commands_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
)""",
    """CREATE TABLE processing_workflow_materials (
	id UUID NOT NULL,
	revision_id UUID NOT NULL,
	kind VARCHAR(16) NOT NULL,
	upload_version INTEGER NOT NULL,
	state VARCHAR(16) NOT NULL,
	material_id BIGINT,
	original_filename VARCHAR(255) NOT NULL,
	declared_size BIGINT NOT NULL,
	declared_sha256 VARCHAR(64),
	actual_size BIGINT,
	actual_sha256 VARCHAR(64),
	failure_code VARCHAR(64),
	execution_token UUID,
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_workflow_materials PRIMARY KEY (id),
	CONSTRAINT uq_processing_workflow_materials_revision_id UNIQUE (revision_id, kind, upload_version),
	CONSTRAINT uq_processing_workflow_materials_id UNIQUE (id, revision_id, kind),
	CONSTRAINT ck_processing_workflow_materials_kind CHECK (kind IN ('paper','answer','audio')),
	CONSTRAINT ck_processing_workflow_materials_state CHECK (state IN ('reserved','uploading','validating','ready','failed','cancelled','superseded')),
	CONSTRAINT ck_processing_workflow_materials_size_version CHECK (upload_version > 0 AND declared_size > 0),
	CONSTRAINT ck_processing_workflow_materials_ready CHECK (state <> 'ready' OR (material_id IS NOT NULL AND actual_sha256 IS NOT NULL AND actual_size > 0)),
	CONSTRAINT fk_processing_workflow_materials_revision_id_processing_d162 FOREIGN KEY(revision_id) REFERENCES processing_workflow_revisions (id),
	CONSTRAINT fk_processing_workflow_materials_material_id_material_sources FOREIGN KEY(material_id) REFERENCES material_sources (id)
)""",
    """CREATE TABLE processing_material_selections (
	revision_id UUID NOT NULL,
	kind VARCHAR(16) NOT NULL,
	upload_id UUID NOT NULL,
	CONSTRAINT pk_processing_material_selections PRIMARY KEY (revision_id, kind),
	CONSTRAINT fk_material_selection_upload FOREIGN KEY(upload_id, revision_id, kind) REFERENCES processing_workflow_materials (id, revision_id, kind),
	CONSTRAINT fk_processing_material_selections_revision_id_processin_bf20 FOREIGN KEY(revision_id) REFERENCES processing_workflow_revisions (id)
)""",
    """CREATE TABLE processing_review_items (
	session_id UUID NOT NULL,
	question_src_id VARCHAR(128) NOT NULL,
	decisions JSONB NOT NULL,
	note TEXT NOT NULL,
	issues JSONB NOT NULL,
	operator_user_id BIGINT NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_review_items PRIMARY KEY (session_id, question_src_id),
	CONSTRAINT fk_processing_review_items_session_id_processing_review_1c45 FOREIGN KEY(session_id) REFERENCES processing_review_sessions (id),
	CONSTRAINT fk_processing_review_items_operator_user_id_users FOREIGN KEY(operator_user_id) REFERENCES users (id)
)""",
    """CREATE TABLE processing_workflow_events (
	id BIGSERIAL NOT NULL,
	workflow_id UUID NOT NULL,
	revision_id UUID,
	task_id UUID,
	command_id UUID,
	event_type VARCHAR(64) NOT NULL,
	detail JSONB NOT NULL,
	operator_user_id BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_processing_workflow_events PRIMARY KEY (id),
	CONSTRAINT fk_processing_workflow_events_workflow_id_processing_workflows FOREIGN KEY(workflow_id) REFERENCES processing_workflows (id),
	CONSTRAINT fk_processing_workflow_events_revision_id_processing_wo_1d1a FOREIGN KEY(revision_id) REFERENCES processing_workflow_revisions (id),
	CONSTRAINT fk_processing_workflow_events_task_id_processing_tasks FOREIGN KEY(task_id) REFERENCES processing_tasks (id),
	CONSTRAINT fk_processing_workflow_events_command_id_processing_wor_d1b6 FOREIGN KEY(command_id) REFERENCES processing_workflow_commands (id),
	CONSTRAINT fk_processing_workflow_events_operator_user_id_users FOREIGN KEY(operator_user_id) REFERENCES users (id)
)""",
    """CREATE INDEX ix_workflow_cursor ON processing_workflows (created_at, id)""",
    """CREATE INDEX ix_workflow_states ON processing_workflows (processing_state, content_review_state, publication_state)""",
    """CREATE INDEX ix_processing_stage_approvals_revision_id ON processing_stage_approvals (revision_id)""",
    """CREATE INDEX ix_workflow_command_poll ON processing_workflow_commands (state, created_at, id)""",
    """CREATE INDEX ix_workflow_upload_recovery ON processing_workflow_materials (state, lease_expires_at)""",
    """CREATE INDEX ix_workflow_event_cursor ON processing_workflow_events (workflow_id, created_at, id)""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT fk_processing_tasks_workflow_id_processing_workflows FOREIGN KEY (workflow_id) REFERENCES processing_workflows(id)""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT fk_processing_tasks_revision_id_processing_workflow_revisions FOREIGN KEY (revision_id) REFERENCES processing_workflow_revisions(id)""",
    """ALTER TABLE processing_tasks ADD CONSTRAINT fk_processing_task_revision_workflow FOREIGN KEY (revision_id, workflow_id) REFERENCES processing_workflow_revisions(id, workflow_id)""",
    """ALTER TABLE processing_workflows ADD CONSTRAINT fk_workflow_current_revision FOREIGN KEY(current_revision_id, id) REFERENCES processing_workflow_revisions (id, workflow_id)""",
    """ALTER TABLE processing_workflows ADD CONSTRAINT fk_workflow_current_task FOREIGN KEY(current_task_id, current_revision_id, id) REFERENCES processing_tasks (id, revision_id, workflow_id)""",
    """ALTER TABLE processing_workflow_revisions ADD CONSTRAINT fk_processing_workflow_revisions_final_task_id_processing_tasks FOREIGN KEY(final_task_id) REFERENCES processing_tasks (id)""",
]


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    op.execute(
        "ALTER TABLE processing_workflow_revisions ADD CONSTRAINT uq_revision_final_hash UNIQUE (id, final_result_hash)"
    )
    op.execute(
        "ALTER TABLE processing_workflow_revisions ADD CONSTRAINT fk_revision_final_task_binding FOREIGN KEY (final_task_id, id, workflow_id) REFERENCES processing_tasks(id, revision_id, workflow_id)"
    )
    op.execute(
        "ALTER TABLE processing_review_sessions ADD CONSTRAINT fk_review_session_final_result FOREIGN KEY (revision_id, result_hash) REFERENCES processing_workflow_revisions(id, final_result_hash)"
    )
    op.execute("""
CREATE FUNCTION m3_continuation_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'continuation audit history is append-only';
END;
$$;
CREATE TRIGGER m3_workflow_events_immutable BEFORE UPDATE OR DELETE
ON processing_workflow_events FOR EACH ROW EXECUTE FUNCTION m3_continuation_append_only();
CREATE TRIGGER m3_stage_approvals_immutable BEFORE UPDATE OR DELETE
ON processing_stage_approvals FOR EACH ROW EXECUTE FUNCTION m3_continuation_append_only();

CREATE FUNCTION m3_command_identity_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'accepted command identity cannot be deleted';
  END IF;
  IF ROW(NEW.id, NEW.workflow_id, NEW.revision_id, NEW.action, NEW.idempotency_key,
         NEW.request_hash, NEW.request, NEW.expected_workflow_version, NEW.created_by,
         NEW.created_at, NEW.retry_of_operation_id)
     IS DISTINCT FROM
     ROW(OLD.id, OLD.workflow_id, OLD.revision_id, OLD.action, OLD.idempotency_key,
         OLD.request_hash, OLD.request, OLD.expected_workflow_version, OLD.created_by,
         OLD.created_at, OLD.retry_of_operation_id) THEN
    RAISE EXCEPTION 'accepted command identity is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER m3_command_identity_immutable BEFORE UPDATE OR DELETE
ON processing_workflow_commands FOR EACH ROW EXECUTE FUNCTION m3_command_identity_immutable();

CREATE FUNCTION m3_revision_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'revision history cannot be deleted';
  END IF;
  IF ROW(NEW.id, NEW.workflow_id, NEW.revision_no, NEW.parent_revision_id,
         NEW.rules_manifest, NEW.document_mode, NEW.listening_pages, NEW.created_by)
     IS DISTINCT FROM ROW(OLD.id, OLD.workflow_id, OLD.revision_no, OLD.parent_revision_id,
         OLD.rules_manifest, OLD.document_mode, OLD.listening_pages, OLD.created_by) THEN
    RAISE EXCEPTION 'revision identity is immutable';
  END IF;
  IF OLD.materials_frozen_at IS NOT NULL AND
     ROW(NEW.materials_manifest, NEW.materials_hash, NEW.materials_frozen_at)
     IS DISTINCT FROM ROW(OLD.materials_manifest, OLD.materials_hash, OLD.materials_frozen_at) THEN
    RAISE EXCEPTION 'frozen materials cannot be replaced';
  END IF;
  IF OLD.final_frozen_at IS NOT NULL AND
     ROW(NEW.final_task_id, NEW.final_result_hash, NEW.final_frozen_at, NEW.stage_fingerprints)
     IS DISTINCT FROM ROW(OLD.final_task_id, OLD.final_result_hash, OLD.final_frozen_at, OLD.stage_fingerprints) THEN
    RAISE EXCEPTION 'frozen result cannot be replaced';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER m3_revision_immutable BEFORE UPDATE OR DELETE
ON processing_workflow_revisions FOR EACH ROW EXECUTE FUNCTION m3_revision_immutable();

CREATE FUNCTION m3_selection_unfrozen() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  target_revision uuid;
  frozen_at timestamptz;
BEGIN
  target_revision := CASE WHEN TG_OP = 'DELETE' THEN OLD.revision_id ELSE NEW.revision_id END;
  SELECT materials_frozen_at INTO frozen_at FROM processing_workflow_revisions
    WHERE id = target_revision FOR UPDATE;
  IF frozen_at IS NOT NULL THEN
    RAISE EXCEPTION 'material selection of frozen revision cannot change';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.revision_id IS DISTINCT FROM NEW.revision_id THEN
    RAISE EXCEPTION 'material selection cannot change revision';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER m3_selection_unfrozen BEFORE INSERT OR UPDATE OR DELETE
ON processing_material_selections FOR EACH ROW EXECUTE FUNCTION m3_selection_unfrozen();
    """)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM processing_workflows)")):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_workflow_revisions)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_review_sessions)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_stage_approvals)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_workflow_commands)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_workflow_materials)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_material_selections)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM processing_review_items)")):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    if connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM processing_workflow_events)")
    ):
        raise RuntimeError(
            "Refusing to delete continuation history; restore a verified backup"
        )
    op.execute("DROP FUNCTION m3_selection_unfrozen() CASCADE")
    op.execute("DROP FUNCTION m3_revision_immutable() CASCADE")
    op.execute("DROP FUNCTION m3_command_identity_immutable() CASCADE")
    op.execute("DROP FUNCTION m3_continuation_append_only() CASCADE")
    op.execute(
        "ALTER TABLE processing_workflow_revisions DROP CONSTRAINT fk_revision_final_task_binding"
    )
    op.execute(
        "ALTER TABLE processing_workflows DROP CONSTRAINT fk_workflow_current_task"
    )
    op.execute(
        "ALTER TABLE processing_workflows DROP CONSTRAINT fk_workflow_current_revision"
    )
    op.execute(
        "ALTER TABLE processing_workflow_revisions DROP CONSTRAINT fk_processing_workflow_revisions_final_task_id_processing_tasks"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT fk_processing_task_revision_workflow"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT fk_processing_tasks_workflow_id_processing_workflows"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT fk_processing_tasks_revision_id_processing_workflow_revisions"
    )
    op.drop_table("processing_workflow_events")
    op.drop_table("processing_review_items")
    op.drop_table("processing_material_selections")
    op.drop_table("processing_workflow_materials")
    op.drop_table("processing_workflow_commands")
    op.drop_table("processing_stage_approvals")
    op.drop_table("processing_review_sessions")
    op.drop_table("processing_workflow_revisions")
    op.drop_table("processing_workflows")
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT uq_processing_tasks_id_revision_workflow"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP CONSTRAINT ck_processing_tasks_workflow_binding"
    )
    op.execute(
        "ALTER TABLE processing_tasks DROP COLUMN workflow_id, DROP COLUMN revision_id"
    )
    op.execute("ALTER TABLE processing_tasks DROP CONSTRAINT ck_processing_tasks_state")
    op.execute(
        "ALTER TABLE processing_tasks ADD CONSTRAINT ck_processing_tasks_state CHECK (state IN ('pending','running','failed','awaiting_confirmation','completed'))"
    )
