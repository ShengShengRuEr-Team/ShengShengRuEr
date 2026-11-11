"""作答系统：attempts / attempt_answers / attempt_rejections

Revision ID: 0005_attempt_system
Revises: 0004_expected_count_source
Create Date: 2026-11-10

只新增三张表与索引/约束，不 ALTER 任何既有表，不写数据迁移。
``downgrade()`` 逆序删表：先 attempt_answers、attempt_rejections，再 attempts；
索引随表删除。模块一 4 张表与模块二 11 张表不受影响。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_attempt_system"
down_revision: str | None = "0004_expected_count_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_code", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_key", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("correct_rate", sa.SmallInteger(), nullable=False),
        sa.Column("practice_score", sa.SmallInteger(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "question_count > 0", name=op.f("ck_attempts_question_count_positive")
        ),
        sa.CheckConstraint(
            "correct_count BETWEEN 0 AND question_count",
            name=op.f("ck_attempts_correct_count_range"),
        ),
        sa.CheckConstraint(
            "correct_rate BETWEEN 0 AND 100",
            name=op.f("ck_attempts_correct_rate_range"),
        ),
        sa.CheckConstraint(
            "practice_score IS NULL OR practice_score BETWEEN 0 AND 249",
            name=op.f("ck_attempts_practice_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_attempts_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exam_paper_id"],
            ["exam_papers.id"],
            name=op.f("fk_attempts_exam_paper_id_exam_papers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["import_batches.id"],
            name=op.f("fk_attempts_import_batch_id_import_batches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
        sa.UniqueConstraint(
            "attempt_code", name=op.f("uq_attempts_attempt_code")
        ),
        sa.UniqueConstraint(
            "student_id",
            "attempt_key",
            name=op.f("uq_attempts_student_attempt_key"),
        ),
    )
    op.create_index(
        "ix_attempts_student_paper",
        "attempts",
        ["student_id", "exam_paper_id"],
    )
    op.create_index("ix_attempts_paper", "attempts", ["exam_paper_id"])
    op.create_index("ix_attempts_submitted_at", "attempts", ["submitted_at"])

    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("question_no", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "passage_type",
            sa.String(length=32),
            server_default="",
            nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_a", sa.Text(), nullable=False),
        sa.Column("option_b", sa.Text(), nullable=False),
        sa.Column("option_c", sa.Text(), nullable=False),
        sa.Column("option_d", sa.Text(), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("selected_option", sa.String(length=1), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("explanation_text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "is_correct = (selected_option IS NOT NULL"
            " AND selected_option = correct_option)",
            name=op.f("ck_attempt_answers_correctness"),
        ),
        sa.CheckConstraint(
            "question_id > 0",
            name=op.f("ck_attempt_answers_question_id_positive"),
        ),
        sa.CheckConstraint(
            "question_no > 0",
            name=op.f("ck_attempt_answers_question_no_positive"),
        ),
        sa.CheckConstraint(
            "correct_option IN ('A', 'B', 'C', 'D')",
            name=op.f("ck_attempt_answers_correct_option_domain"),
        ),
        sa.CheckConstraint(
            "selected_option IS NULL OR selected_option IN ('A', 'B', 'C', 'D')",
            name=op.f("ck_attempt_answers_selected_option_domain"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_attempt_answers_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempt_answers")),
        sa.UniqueConstraint(
            "attempt_id",
            "question_no",
            name=op.f("uq_attempt_answers_attempt_question_no"),
        ),
        sa.UniqueConstraint(
            "attempt_id",
            "question_id",
            name=op.f("uq_attempt_answers_attempt_question_id"),
        ),
    )
    op.create_index(
        "ix_attempt_answers_attempt", "attempt_answers", ["attempt_id"]
    )

    op.create_table(
        "attempt_rejections",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("exam_paper_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_key", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("rejection_kind", sa.String(length=32), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rejection_kind IN ('paper_not_accessible',"
            " 'content_version_mismatch')",
            name=op.f("ck_attempt_rejections_rejection_kind_domain"),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_attempt_rejections_student_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempt_rejections")),
        sa.UniqueConstraint(
            "student_id",
            "attempt_key",
            name=op.f("uq_attempt_rejections_student_attempt_key"),
        ),
    )


def downgrade() -> None:
    # 逆序删除：先逐题事实与拒绝标记，再作答主记录；索引随表删除。
    op.drop_table("attempt_answers")
    op.drop_table("attempt_rejections")
    op.drop_table("attempts")
