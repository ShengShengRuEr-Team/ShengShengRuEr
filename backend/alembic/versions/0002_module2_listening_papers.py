"""module2 listening papers (minimal business subset)

Revision ID: 0002_module2_listening_papers
Revises: 0001_initial_auth_only
Create Date: 2026-11-03

模块二题库管理与整套试卷展示，最小业务子集，共 11 张表：
audio_files / exam_papers / import_batches / content_groups / passages /
transcript_segments / questions / presentations（业务）+
content_checks / paper_visibility / visibility_audit_logs（系统记录）。

不修改、不清空模块一 users / roles / user_roles / token_revocations。
词典与标注表本期不建，待模块三按 16 表基线补齐。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_module2_listening_papers"
down_revision: str | None = "0001_initial_auth_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("audio_code", sa.String(length=64), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), server_default="local", nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("format", sa.String(length=16), server_default="", nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("variant_type", sa.String(length=32), server_default="原始", nullable=False),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_audio_files_review_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audio_files")),
        sa.UniqueConstraint("audio_code", name=op.f("uq_audio_files_audio_code")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_audio_files_storage_key")),
    )

    op.create_table(
        "exam_papers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exam_paper_code", sa.String(length=64), nullable=False),
        sa.Column("exam_level", sa.String(length=32), nullable=False),
        sa.Column("exam_year", sa.Integer(), nullable=False),
        sa.Column("exam_month", sa.Integer(), nullable=False),
        sa.Column("paper_set", sa.Integer(), nullable=False),
        sa.Column("content_scope", sa.String(length=16), server_default="listening", nullable=False),
        sa.Column("playback_audio_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.Text(), server_default="", nullable=False),
        sa.Column("mapping_source", sa.Text(), server_default="", nullable=False),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_exam_papers_review_status"),
        ),
        sa.ForeignKeyConstraint(
            ["playback_audio_id"], ["audio_files.id"],
            name=op.f("fk_exam_papers_playback_audio_id_audio_files"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_papers")),
        sa.UniqueConstraint("exam_paper_code", name=op.f("uq_exam_papers_exam_paper_code")),
    )

    op.create_table(
        "import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("audio_id", sa.BigInteger(), nullable=True),
        sa.Column("batch_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("source_manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("source_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'active', 'failed')", name=op.f("ck_import_batches_status")),
        sa.ForeignKeyConstraint(["audio_id"], ["audio_files.id"], name=op.f("fk_import_batches_audio_id_audio_files"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_import_batches_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
        sa.UniqueConstraint("batch_code", name=op.f("uq_import_batches_batch_code")),
    )
    # 每套试卷至多一个当前批次（部分唯一索引）。
    op.create_index(
        "uq_import_batches_one_current",
        "import_batches",
        ["exam_paper_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "content_groups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("content_group_code", sa.String(length=64), nullable=False),
        sa.Column("group_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("exam_level_scope", sa.String(length=16), server_default="", nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_content_groups_review_status"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_content_groups_batch_id_import_batches"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_groups")),
    )

    op.create_table(
        "passages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("audio_id", sa.BigInteger(), nullable=True),
        sa.Column("passage_code", sa.String(length=64), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("passage_type", sa.String(length=32), server_default="", nullable=False),
        sa.Column("topic", sa.Text(), server_default="", nullable=False),
        sa.Column("scene", sa.Text(), server_default="", nullable=False),
        sa.Column("accent", sa.String(length=32), server_default="未判定", nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("body_end_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_ms", sa.BigInteger(), nullable=True),
        sa.Column("speaker_count", sa.Integer(), nullable=True),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_passages_review_status"),
        ),
        sa.ForeignKeyConstraint(["audio_id"], ["audio_files.id"], name=op.f("fk_passages_audio_id_audio_files"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_passages_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_passages_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passages")),
        sa.UniqueConstraint("batch_id", "passage_index", name=op.f("uq_passages_batch_id")),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("passage_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("segment_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker_code", sa.String(length=64), server_default="", nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("segment_type IN ('body', 'question')", name=op.f("ck_transcript_segments_segment_type")),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_transcript_segments_review_status"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_transcript_segments_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["passage_id"], ["passages.id"], name=op.f("fk_transcript_segments_passage_id_passages"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcript_segments")),
        sa.UniqueConstraint("passage_id", "segment_index", name=op.f("uq_transcript_segments_passage_id")),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("passage_id", sa.BigInteger(), nullable=False),
        sa.Column("question_code", sa.String(length=64), nullable=False),
        sa.Column("question_segment_id", sa.BigInteger(), nullable=True),
        sa.Column("question_index", sa.Integer(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_a", sa.Text(), nullable=False),
        sa.Column("option_b", sa.Text(), nullable=False),
        sa.Column("option_c", sa.Text(), nullable=False),
        sa.Column("option_d", sa.Text(), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.Column("explanation_source", sa.String(length=255), server_default="", nullable=False),
        sa.Column("content_state", sa.String(length=32), server_default="待补齐", nullable=False),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("correct_option IN ('A', 'B', 'C', 'D')", name=op.f("ck_questions_correct_option")),
        sa.CheckConstraint(
            "content_state IN ('待补齐', '可用', '停用')", name=op.f("ck_questions_content_state")
        ),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_questions_review_status"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_questions_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["passage_id"], ["passages.id"], name=op.f("fk_questions_passage_id_passages"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_segment_id"], ["transcript_segments.id"], name=op.f("fk_questions_question_segment_id_transcript_segments"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )

    op.create_table(
        "presentations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("question_no", sa.Integer(), nullable=False),
        sa.Column("option_mapping_state", sa.String(length=16), server_default="未知", nullable=False),
        sa.Column("mapping_source", sa.Text(), server_default="", nullable=False),
        sa.Column("option_letter_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("collector", sa.String(length=64), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=32), server_default="待审核", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "review_status IN ('待审核', '需修改', '待确认', '已通过')",
            name=op.f("ck_presentations_review_status"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_presentations_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_presentations_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], name=op.f("fk_presentations_question_id_questions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentations")),
        sa.UniqueConstraint("batch_id", "question_no", name=op.f("uq_presentations_batch_id")),
    )

    op.create_table(
        "content_checks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_content_checks_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_content_checks_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_checks")),
    )

    op.create_table(
        "paper_visibility",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_paper_visibility_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"], name=op.f("fk_paper_visibility_cancelled_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], name=op.f("fk_paper_visibility_confirmed_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_paper_visibility_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_visibility")),
    )

    op.create_table(
        "visibility_audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("operator_user_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=255), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], name=op.f("fk_visibility_audit_logs_batch_id_import_batches"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_paper_id"], ["exam_papers.id"], name=op.f("fk_visibility_audit_logs_exam_paper_id_exam_papers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_user_id"], ["users.id"], name=op.f("fk_visibility_audit_logs_operator_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visibility_audit_logs")),
    )


def downgrade() -> None:
    op.drop_table("visibility_audit_logs")
    op.drop_table("paper_visibility")
    op.drop_table("content_checks")
    op.drop_table("presentations")
    op.drop_table("questions")
    op.drop_table("transcript_segments")
    op.drop_table("passages")
    op.drop_table("content_groups")
    op.drop_index("uq_import_batches_one_current", table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_table("exam_papers")
    op.drop_table("audio_files")
