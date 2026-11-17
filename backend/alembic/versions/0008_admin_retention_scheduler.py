"""管理端阶段一 T07：留存调度三张表

Revision ID: 0008_admin_retention_scheduler
Revises: 0007_admin_audit_events
Create Date: 2026-11-17

只新增 `admin_job_definitions`、`admin_job_runs`、`admin_job_scheduler_state`
三张表与索引/约束，并 seed 唯一任务定义；不 ALTER 既有表、不写数据迁移。
`downgrade()` 逆序删表，可回到 0007。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_admin_retention_scheduler"
down_revision: str | None = "0007_admin_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_job_definitions",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Shanghai'"),
            nullable=False,
        ),
        sa.Column(
            "next_scheduled_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_scheduled_slot", sa.Date(), nullable=True),
        sa.Column(
            "last_run_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "active_run_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "missed_slots",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_id = 'admin.retention_cleanup'",
            name="job_id",
        ),
        sa.CheckConstraint(
            "missed_slots >= 0",
            name="missed_slots",
        ),
        sa.PrimaryKeyConstraint("job_id", name="pk_admin_job_definitions"),
    )

    op.create_table(
        "admin_job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("slot_key", sa.Date(), nullable=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "state",
            sa.String(length=16),
            server_default=sa.text("'QUEUED'"),
            nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retry_pending",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "counts",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "counts_complete",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "trigger IN ('scheduled', 'manual')",
            name="trigger",
        ),
        sa.CheckConstraint(
            "(trigger = 'scheduled' AND slot_key IS NOT NULL)"
            " OR (trigger = 'manual' AND slot_key IS NULL)",
            name="slot_rule",
        ),
        sa.CheckConstraint(
            "state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL',"
            " 'FAILED', 'INTERRUPTED')",
            name="state",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 2",
            name="attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_admin_job_runs_actor_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_admin_job_runs"),
    )
    op.create_index(
        "uq_admin_job_runs_slot",
        "admin_job_runs",
        ["job_id", "slot_key"],
        unique=True,
        postgresql_where=sa.text("trigger = 'scheduled'"),
    )
    op.create_index(
        "uq_admin_job_runs_active",
        "admin_job_runs",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('QUEUED', 'RUNNING')"),
    )
    op.create_index(
        "ix_admin_job_runs_job_created",
        "admin_job_runs",
        ["job_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "admin_job_scheduler_state",
        sa.Column("instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "instance_id", name="pk_admin_job_scheduler_state"
        ),
    )
    op.create_index(
        "ix_admin_job_scheduler_state_heartbeat",
        "admin_job_scheduler_state",
        ["heartbeat_at"],
    )

    # 唯一任务定义：只 seed 一行，next_scheduled_at 由调度进程启动时计算。
    op.execute(
        "INSERT INTO admin_job_definitions"
        " (job_id, enabled, timezone, missed_slots)"
        " VALUES ('admin.retention_cleanup', true, 'Asia/Shanghai', 0)"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_job_scheduler_state_heartbeat",
        table_name="admin_job_scheduler_state",
    )
    op.drop_table("admin_job_scheduler_state")

    op.drop_index(
        "ix_admin_job_runs_job_created", table_name="admin_job_runs"
    )
    op.drop_index(
        "uq_admin_job_runs_active", table_name="admin_job_runs"
    )
    op.drop_index("uq_admin_job_runs_slot", table_name="admin_job_runs")
    op.drop_table("admin_job_runs")

    op.drop_table("admin_job_definitions")
