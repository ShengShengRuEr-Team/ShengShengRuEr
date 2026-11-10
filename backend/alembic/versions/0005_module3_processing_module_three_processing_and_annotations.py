"""module three processing and annotations

Revision ID: 0005_module3_processing
Revises: 0004_expected_count_source
Create Date: 2026-11-04 22:22:50.189442

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_module3_processing"
down_revision: str | Sequence[str] | None = "0004_expected_count_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing versioned keys must exist before composite ownership FKs.
    op.create_unique_constraint(
        op.f("uq_content_groups_id"), "content_groups", ["id", "batch_id"]
    )
    op.create_unique_constraint(op.f("uq_passages_id"), "passages", ["id", "batch_id"])
    op.create_unique_constraint(
        op.f("uq_questions_id"), "questions", ["id", "batch_id"]
    )
    op.create_unique_constraint(
        op.f("uq_transcript_segments_id"), "transcript_segments", ["id", "batch_id"]
    )
    op.create_table(
        "dictionary_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("schema_sha256", sa.String(length=64), nullable=False),
        sa.Column("data_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "id_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dictionary_snapshots")),
        sa.UniqueConstraint(
            "schema_sha256", name=op.f("uq_dictionary_snapshots_schema_sha256")
        ),
    )
    op.create_table(
        "classification_dicts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("dict_kind", sa.String(length=32), nullable=False),
        sa.Column("classification_code", sa.String(length=64), nullable=False),
        sa.Column("classification_name", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("decision_rule", sa.Text(), nullable=True),
        sa.Column("exclude_rule", sa.Text(), nullable=True),
        sa.Column("typical_example", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dictionary_snapshots.id"],
            name=op.f("fk_classification_dicts_snapshot_id_dictionary_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_classification_dicts")),
        sa.UniqueConstraint(
            "snapshot_id",
            "classification_code",
            name=op.f("uq_classification_dicts_snapshot_id"),
        ),
    )
    op.create_table(
        "error_causes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("error_cause_code", sa.String(length=64), nullable=False),
        sa.Column("display_code", sa.String(length=64), nullable=False),
        sa.Column("legacy_codes", sa.String(length=64), nullable=True),
        sa.Column("cause_level", sa.Integer(), nullable=False),
        sa.Column("parent_error_cause_id", sa.BigInteger(), nullable=True),
        sa.Column("cause_name", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("confirmation_rule", sa.Text(), nullable=True),
        sa.Column("display_mapping", sa.String(length=32), nullable=True),
        sa.Column("boundary_rule", sa.Text(), nullable=True),
        sa.Column("remedy_hint", sa.Text(), nullable=True),
        sa.Column("maturity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["parent_error_cause_id"],
            ["error_causes.id"],
            name=op.f("fk_error_causes_parent_error_cause_id_error_causes"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dictionary_snapshots.id"],
            name=op.f("fk_error_causes_snapshot_id_dictionary_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_error_causes")),
        sa.UniqueConstraint(
            "snapshot_id", "error_cause_code", name=op.f("uq_error_causes_snapshot_id")
        ),
    )
    op.create_table(
        "material_sources",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_code", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("derived_from_material_id", sa.BigInteger(), nullable=True),
        sa.Column("generation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("registered_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["derived_from_material_id"],
            ["material_sources.id"],
            name=op.f("fk_material_sources_derived_from_material_id_material_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["registered_by"],
            ["users.id"],
            name=op.f("fk_material_sources_registered_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_sources")),
        sa.UniqueConstraint(
            "source_kind",
            "storage_key",
            "sha256",
            name=op.f("uq_material_sources_source_kind"),
        ),
    )
    op.create_index(
        op.f("ix_material_sources_exam_paper_code"),
        "material_sources",
        ["exam_paper_code"],
        unique=False,
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_code", sa.String(length=64), nullable=False),
        sa.Column("display_code", sa.String(length=64), nullable=False),
        sa.Column("legacy_codes", sa.String(length=64), nullable=True),
        sa.Column("skill_level", sa.Integer(), nullable=False),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("observable_behavior", sa.Text(), nullable=True),
        sa.Column("counter_example", sa.Text(), nullable=True),
        sa.Column("usage_scope", sa.String(length=32), nullable=False),
        sa.Column("exam_level_scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dictionary_snapshots.id"],
            name=op.f("fk_skills_snapshot_id_dictionary_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint(
            "snapshot_id", "skill_code", name=op.f("uq_skills_snapshot_id")
        ),
    )
    op.create_table(
        "language_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("item_text", sa.Text(), nullable=False),
        sa.Column("lemma", sa.Text(), nullable=True),
        sa.Column("sense", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_language_items_batch_id_import_batches"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_language_items")),
        sa.UniqueConstraint(
            "batch_id", "item_code", name=op.f("uq_language_items_batch_id")
        ),
        sa.UniqueConstraint(
            "batch_id",
            "item_type",
            "normalized_text",
            "sense",
            name="uq_language_items_sense",
        ),
        sa.UniqueConstraint("id", "batch_id", name=op.f("uq_language_items_id")),
    )
    op.create_table(
        "processing_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_paper_code", sa.String(length=64), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=True),
        sa.Column("parent_task_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.UUID(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("method_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("reused_task_id", sa.UUID(), nullable=True),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("method", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pending','running','failed','awaiting_confirmation','completed')",
            name=op.f("ck_processing_tasks_state"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_processing_tasks_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_processing_tasks_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_paper_id"],
            ["exam_papers.id"],
            name=op.f("fk_processing_tasks_exam_paper_id_exam_papers"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_tasks_parent_task_id_processing_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["reused_task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_tasks_reused_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_tasks")),
    )
    op.create_index(
        op.f("ix_processing_tasks_exam_paper_code"),
        "processing_tasks",
        ["exam_paper_code"],
        unique=False,
    )
    op.create_index(
        "ix_processing_tasks_poll",
        "processing_tasks",
        ["state", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "skill_error_relations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_code", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("error_cause_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_nature", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("candidate_scope", sa.Text(), nullable=False),
        sa.Column("selection_rule", sa.Text(), nullable=False),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["error_cause_id"],
            ["error_causes.id"],
            name=op.f("fk_skill_error_relations_error_cause_id_error_causes"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_skill_error_relations_skill_id_skills"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dictionary_snapshots.id"],
            name=op.f("fk_skill_error_relations_snapshot_id_dictionary_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_error_relations")),
        sa.UniqueConstraint(
            "snapshot_id",
            "relation_code",
            "revision_no",
            name=op.f("uq_skill_error_relations_snapshot_id"),
        ),
    )
    op.create_index(
        "uq_skill_error_relations_current",
        "skill_error_relations",
        ["snapshot_id", "relation_code"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "batch_activation_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("old_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("new_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("check_id", sa.BigInteger(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("operator_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["content_checks.id"],
            name=op.f("fk_batch_activation_logs_check_id_content_checks"),
        ),
        sa.ForeignKeyConstraint(
            ["exam_paper_id"],
            ["exam_papers.id"],
            name=op.f("fk_batch_activation_logs_exam_paper_id_exam_papers"),
        ),
        sa.ForeignKeyConstraint(
            ["new_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_batch_activation_logs_new_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["old_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_batch_activation_logs_old_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            name=op.f("fk_batch_activation_logs_operator_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_batch_activation_logs_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_activation_logs")),
    )
    op.create_table(
        "batch_audio_groups",
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("audio_id", sa.BigInteger(), nullable=False),
        sa.Column("content_group_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audio_id"],
            ["audio_files.id"],
            name=op.f("fk_batch_audio_groups_audio_id_audio_files"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_batch_audio_groups_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["content_group_id"],
            ["content_groups.id"],
            name=op.f("fk_batch_audio_groups_content_group_id_content_groups"),
        ),
        sa.PrimaryKeyConstraint(
            "batch_id",
            "audio_id",
            "content_group_id",
            name=op.f("pk_batch_audio_groups"),
        ),
    )
    op.create_table(
        "batch_paper_metadata",
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("content_group_id", sa.BigInteger(), nullable=False),
        sa.Column("binding_state", sa.String(length=32), nullable=True),
        sa.Column("question_order_state", sa.String(length=32), nullable=True),
        sa.Column("option_order_state", sa.String(length=32), nullable=True),
        sa.Column("equivalence_basis", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_batch_paper_metadata_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["content_group_id"],
            ["content_groups.id"],
            name=op.f("fk_batch_paper_metadata_content_group_id_content_groups"),
        ),
        sa.PrimaryKeyConstraint("batch_id", name=op.f("pk_batch_paper_metadata")),
    )
    op.create_table(
        "batch_source_refs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("src_id", sa.String(length=128), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("conversion_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_batch_source_refs_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["material_sources.id"],
            name=op.f("fk_batch_source_refs_material_id_material_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_batch_source_refs_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_source_refs")),
    )
    op.create_table(
        "processing_artifacts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("method_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("source_artifact_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"],
            ["processing_artifacts.id"],
            name=op.f(
                "fk_processing_artifacts_source_artifact_id_processing_artifacts"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_artifacts_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_artifacts")),
        sa.UniqueConstraint(
            "task_id",
            "stage",
            "artifact_hash",
            name=op.f("uq_processing_artifacts_task_id"),
        ),
    )
    op.create_table(
        "processing_corrections",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("parent_task_id", sa.UUID(), nullable=False),
        sa.Column("before_hash", sa.String(length=64), nullable=False),
        sa.Column("after_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "before_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "after_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("operator_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            name=op.f("fk_processing_corrections_operator_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_corrections_parent_task_id_processing_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_corrections_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_corrections")),
    )
    op.create_table(
        "processing_drafts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("view", sa.String(length=16), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_drafts_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_drafts")),
        sa.UniqueConstraint(
            "task_id", "view", name=op.f("uq_processing_drafts_task_id")
        ),
    )
    op.create_table(
        "processing_llm_attempts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("response_model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reserved_usd", sa.Numeric(precision=14, scale=8), nullable=False),
        sa.Column("charged_usd", sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column("billing_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_llm_attempts_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_llm_attempts")),
    )
    op.create_table(
        "processing_reviews",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("operator_user_id", sa.BigInteger(), nullable=False),
        sa.Column("operator_label", sa.String(length=128), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            name=op.f("fk_processing_reviews_operator_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_processing_reviews_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_reviews")),
    )
    op.create_table(
        "task_materials",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["material_sources.id"],
            name=op.f("fk_task_materials_material_id_material_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["processing_tasks.id"],
            name=op.f("fk_task_materials_task_id_processing_tasks"),
        ),
        sa.PrimaryKeyConstraint(
            "task_id", "material_id", name=op.f("pk_task_materials")
        ),
    )
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("passage_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("collector", sa.String(length=64), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_evidence_items_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["passage_id", "batch_id"],
            ["passages.id", "passages.batch_id"],
            name="fk_evidence_items_passage_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["passages.id"],
            name=op.f("fk_evidence_items_passage_id_passages"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_evidence_items_segment_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["transcript_segments.id"],
            name=op.f("fk_evidence_items_segment_id_transcript_segments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_items")),
        sa.UniqueConstraint("id", "batch_id", name=op.f("uq_evidence_items_id")),
    )
    op.create_table(
        "error_question_relations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_kind", sa.String(length=32), nullable=False),
        sa.Column("relation_code", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=True),
        sa.Column("error_cause_id", sa.BigInteger(), nullable=True),
        sa.Column("option_letter", sa.String(length=1), nullable=True),
        sa.Column("owner_relation_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_error_question_relations_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["error_cause_id"],
            ["error_causes.id"],
            name=op.f("fk_error_question_relations_error_cause_id_error_causes"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_error_question_relations_evidence_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_items.id"],
            name=op.f("fk_error_question_relations_evidence_id_evidence_items"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_relation_id", "batch_id"],
            ["error_question_relations.id", "error_question_relations.batch_id"],
            name="fk_error_question_relations_owner_relation_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["owner_relation_id"],
            ["error_question_relations.id"],
            name=op.f(
                "fk_error_question_relations_owner_relation_id_error_question_relations"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_error_question_relations_question_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_error_question_relations_question_id_questions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_error_question_relations")),
        sa.UniqueConstraint(
            "batch_id",
            "relation_code",
            "revision_no",
            name=op.f("uq_error_question_relations_batch_id"),
        ),
        sa.UniqueConstraint(
            "id", "batch_id", name=op.f("uq_error_question_relations_id")
        ),
    )
    op.create_index(
        "uq_error_question_relations_current",
        "error_question_relations",
        ["batch_id", "relation_code"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "evidence_segments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("passage_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(start_char IS NULL AND end_char IS NULL) OR (start_char >= 0 AND end_char > start_char)",
            name=op.f("ck_evidence_segments_char_range"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_evidence_segments_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_evidence_segments_evidence_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id", "batch_id"],
            ["passages.id", "passages.batch_id"],
            name="fk_evidence_segments_passage_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_evidence_segments_segment_id_batch",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_segments")),
        sa.UniqueConstraint(
            "evidence_id", "segment_id", name="uq_evidence_segments_segment"
        ),
        sa.UniqueConstraint(
            "evidence_id", "sort_order", name=op.f("uq_evidence_segments_evidence_id")
        ),
    )
    op.create_table(
        "other_relations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("relation_kind", sa.String(length=32), nullable=False),
        sa.Column("relation_code", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("from_skill_id", sa.BigInteger(), nullable=True),
        sa.Column("to_skill_id", sa.BigInteger(), nullable=True),
        sa.Column("question_id", sa.BigInteger(), nullable=True),
        sa.Column("language_item_id", sa.BigInteger(), nullable=True),
        sa.Column("option_letter", sa.String(length=1), nullable=True),
        sa.Column("segment_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_other_relations_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_other_relations_evidence_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_items.id"],
            name=op.f("fk_other_relations_evidence_id_evidence_items"),
        ),
        sa.ForeignKeyConstraint(
            ["from_skill_id"],
            ["skills.id"],
            name=op.f("fk_other_relations_from_skill_id_skills"),
        ),
        sa.ForeignKeyConstraint(
            ["language_item_id", "batch_id"],
            ["language_items.id", "language_items.batch_id"],
            name="fk_other_relations_language_item_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["language_item_id"],
            ["language_items.id"],
            name=op.f("fk_other_relations_language_item_id_language_items"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_other_relations_question_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_other_relations_question_id_questions"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_id", "batch_id"],
            ["transcript_segments.id", "transcript_segments.batch_id"],
            name="fk_other_relations_segment_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["transcript_segments.id"],
            name=op.f("fk_other_relations_segment_id_transcript_segments"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["dictionary_snapshots.id"],
            name=op.f("fk_other_relations_snapshot_id_dictionary_snapshots"),
        ),
        sa.ForeignKeyConstraint(
            ["to_skill_id"],
            ["skills.id"],
            name=op.f("fk_other_relations_to_skill_id_skills"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_other_relations")),
        sa.UniqueConstraint("id", "batch_id", name=op.f("uq_other_relations_id")),
        sa.UniqueConstraint(
            "scope_key",
            "relation_code",
            "revision_no",
            name=op.f("uq_other_relations_scope_key"),
        ),
    )
    op.create_index(
        "uq_other_relations_current",
        "other_relations",
        ["scope_key", "relation_code"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "skill_question_relations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("relation_kind", sa.String(length=32), nullable=False),
        sa.Column("relation_code", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=True),
        sa.Column("skill_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_relation_id", sa.BigInteger(), nullable=True),
        sa.Column("evidence_id", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("collector", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name=op.f("fk_skill_question_relations_batch_id_import_batches"),
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "batch_id"],
            ["evidence_items.id", "evidence_items.batch_id"],
            name="fk_skill_question_relations_evidence_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_items.id"],
            name=op.f("fk_skill_question_relations_evidence_id_evidence_items"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_relation_id", "batch_id"],
            ["skill_question_relations.id", "skill_question_relations.batch_id"],
            name="fk_skill_question_relations_owner_relation_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["owner_relation_id"],
            ["skill_question_relations.id"],
            name=op.f(
                "fk_skill_question_relations_owner_relation_id_skill_question_relations"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "batch_id"],
            ["questions.id", "questions.batch_id"],
            name="fk_skill_question_relations_question_id_batch",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_skill_question_relations_question_id_questions"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_skill_question_relations_skill_id_skills"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_question_relations")),
        sa.UniqueConstraint(
            "batch_id",
            "relation_code",
            "revision_no",
            name=op.f("uq_skill_question_relations_batch_id"),
        ),
        sa.UniqueConstraint(
            "id", "batch_id", name=op.f("uq_skill_question_relations_id")
        ),
    )
    op.create_index(
        "uq_skill_question_relations_current",
        "skill_question_relations",
        ["batch_id", "relation_code"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.add_column(
        "audio_files", sa.Column("source_paper_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "audio_files",
        sa.Column("derived_from_audio_id", sa.BigInteger(), nullable=True),
    )
    op.add_column("audio_files", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "audio_files",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_foreign_key(
        op.f("fk_audio_files_source_paper_id_exam_papers"),
        "audio_files",
        "exam_papers",
        ["source_paper_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_audio_files_derived_from_audio_id_audio_files"),
        "audio_files",
        "audio_files",
        ["derived_from_audio_id"],
        ["id"],
    )
    op.add_column(
        "content_checks", sa.Column("result_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "content_checks", sa.Column("rule_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "content_checks",
        sa.Column(
            "check_profile",
            sa.String(length=16),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "content_groups", sa.Column("basis_paper_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "content_groups", sa.Column("equivalence_basis", sa.Text(), nullable=True)
    )
    op.add_column(
        "content_groups", sa.Column("status", sa.String(length=32), nullable=True)
    )
    op.add_column("content_groups", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "content_groups",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_unique_constraint(
        op.f("uq_content_groups_batch_id"),
        "content_groups",
        ["batch_id", "content_group_code"],
    )
    op.create_foreign_key(
        op.f("fk_content_groups_basis_paper_id_exam_papers"),
        "content_groups",
        "exam_papers",
        ["basis_paper_id"],
        ["id"],
    )
    op.add_column("exam_papers", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "exam_papers",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "import_batches",
        sa.Column("result_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "import_batches",
        sa.Column("profile_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "import_batches",
        sa.Column(
            "check_profile",
            sa.String(length=16),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "import_batches", sa.Column("result_hash", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_import_batches_exam_paper_id"),
        "import_batches",
        ["exam_paper_id", "result_fingerprint"],
    )
    op.add_column("passages", sa.Column("genre_id", sa.BigInteger(), nullable=True))
    op.add_column("passages", sa.Column("genre_note", sa.Text(), nullable=True))
    op.add_column(
        "passages", sa.Column("genre_confidence", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "passages",
        sa.Column("genre_review_status", sa.String(length=32), nullable=True),
    )
    op.add_column("passages", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "passages",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_unique_constraint(
        "uq_passages_batch_code", "passages", ["batch_id", "passage_code"]
    )
    op.create_foreign_key(
        op.f("fk_passages_genre_id_classification_dicts"),
        "passages",
        "classification_dicts",
        ["genre_id"],
        ["id"],
    )
    op.add_column("presentations", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "presentations",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "questions", sa.Column("source_paper_id", sa.BigInteger(), nullable=True)
    )
    op.add_column("questions", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "questions",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_unique_constraint(
        op.f("uq_questions_batch_id"), "questions", ["batch_id", "question_code"]
    )
    op.create_foreign_key(
        op.f("fk_questions_source_paper_id_exam_papers"),
        "questions",
        "exam_papers",
        ["source_paper_id"],
        ["id"],
    )
    op.add_column("transcript_segments", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "transcript_segments",
        sa.Column(
            "attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # Module-two passages survive this rollback and still reference the new
    # dictionary table. Detach that foreign key before dropping its target.
    op.drop_constraint(
        op.f("fk_passages_genre_id_classification_dicts"),
        "passages",
        type_="foreignkey",
    )
    op.drop_index(
        "uq_skill_question_relations_current",
        table_name="skill_question_relations",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("skill_question_relations")
    op.drop_index(
        "uq_other_relations_current",
        table_name="other_relations",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("other_relations")
    op.drop_table("evidence_segments")
    op.drop_index(
        "uq_error_question_relations_current",
        table_name="error_question_relations",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("error_question_relations")
    op.drop_table("evidence_items")
    op.drop_table("task_materials")
    op.drop_table("processing_reviews")
    op.drop_table("processing_llm_attempts")
    op.drop_table("processing_drafts")
    op.drop_table("processing_corrections")
    op.drop_table("processing_artifacts")
    op.drop_table("batch_source_refs")
    op.drop_table("batch_paper_metadata")
    op.drop_table("batch_audio_groups")
    op.drop_table("batch_activation_logs")
    op.drop_index(
        "uq_skill_error_relations_current",
        table_name="skill_error_relations",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("skill_error_relations")
    op.drop_index("ix_processing_tasks_poll", table_name="processing_tasks")
    op.drop_index(
        op.f("ix_processing_tasks_exam_paper_code"), table_name="processing_tasks"
    )
    op.drop_table("processing_tasks")
    op.drop_table("language_items")
    op.drop_table("skills")
    op.drop_index(
        op.f("ix_material_sources_exam_paper_code"), table_name="material_sources"
    )
    op.drop_table("material_sources")
    op.drop_table("error_causes")
    op.drop_table("classification_dicts")
    op.drop_table("dictionary_snapshots")
    # ### end Alembic commands ###

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("uq_transcript_segments_id"), "transcript_segments", type_="unique"
    )
    op.drop_column("transcript_segments", "attributes_json")
    op.drop_column("transcript_segments", "notes")
    op.drop_constraint(
        op.f("fk_questions_source_paper_id_exam_papers"),
        "questions",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_questions_id"), "questions", type_="unique")
    op.drop_constraint(op.f("uq_questions_batch_id"), "questions", type_="unique")
    op.drop_column("questions", "attributes_json")
    op.drop_column("questions", "notes")
    op.drop_column("questions", "source_paper_id")
    op.drop_column("presentations", "attributes_json")
    op.drop_column("presentations", "notes")
    op.drop_constraint(op.f("uq_passages_id"), "passages", type_="unique")
    op.drop_constraint("uq_passages_batch_code", "passages", type_="unique")
    op.drop_column("passages", "attributes_json")
    op.drop_column("passages", "notes")
    op.drop_column("passages", "genre_review_status")
    op.drop_column("passages", "genre_confidence")
    op.drop_column("passages", "genre_note")
    op.drop_column("passages", "genre_id")
    op.drop_constraint(
        op.f("uq_import_batches_exam_paper_id"), "import_batches", type_="unique"
    )
    op.drop_column("import_batches", "result_hash")
    op.drop_column("import_batches", "check_profile")
    op.drop_column("import_batches", "profile_version")
    op.drop_column("import_batches", "result_fingerprint")
    op.drop_column("exam_papers", "attributes_json")
    op.drop_column("exam_papers", "notes")
    op.drop_constraint(
        op.f("fk_content_groups_basis_paper_id_exam_papers"),
        "content_groups",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_content_groups_id"), "content_groups", type_="unique")
    op.drop_constraint(
        op.f("uq_content_groups_batch_id"), "content_groups", type_="unique"
    )
    op.drop_column("content_groups", "attributes_json")
    op.drop_column("content_groups", "notes")
    op.drop_column("content_groups", "status")
    op.drop_column("content_groups", "equivalence_basis")
    op.drop_column("content_groups", "basis_paper_id")
    op.drop_column("content_checks", "check_profile")
    op.drop_column("content_checks", "rule_version")
    op.drop_column("content_checks", "result_hash")
    op.drop_constraint(
        op.f("fk_audio_files_derived_from_audio_id_audio_files"),
        "audio_files",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_audio_files_source_paper_id_exam_papers"),
        "audio_files",
        type_="foreignkey",
    )
    op.drop_column("audio_files", "attributes_json")
    op.drop_column("audio_files", "notes")
    op.drop_column("audio_files", "derived_from_audio_id")
    op.drop_column("audio_files", "source_paper_id")
