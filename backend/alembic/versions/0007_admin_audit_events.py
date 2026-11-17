"""管理端阶段一 T02：两类审计事件表

Revision ID: 0007_admin_audit_events
Revises: 0006_admin_auth_session
Create Date: 2026-11-17

只新增两张表与索引/约束，不 ALTER 既有表，不写数据迁移、不 seed 数据。
``downgrade()`` 逆序删表，索引随表删除，可回到 0006 的结构。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_admin_audit_events"
down_revision: str | None = "0006_admin_auth_session"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHARED_COLUMNS = (
    sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("event_type", sa.String(length=64), nullable=False),
    sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
    sa.Column(
        "actor_name",
        sa.String(length=50),
        server_default=sa.text("''"),
        nullable=False,
    ),
    sa.Column("role_snapshot", sa.String(length=16), nullable=True),
    sa.Column("target_type", sa.String(length=32), nullable=True),
    sa.Column("target_id", sa.String(length=64), nullable=True),
    sa.Column("result", sa.String(length=16), nullable=False),
    sa.Column("reason_code", sa.String(length=64), nullable=True),
    sa.Column(
        "summary",
        postgresql.JSONB(),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    ),
    sa.Column("ip", postgresql.INET(), nullable=True),
    sa.Column(
        "user_agent",
        sa.String(length=256),
        server_default=sa.text("''"),
        nullable=False,
    ),
    sa.Column(
        "duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False
    ),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
)


def upgrade() -> None:
    op.create_table(
        "admin_login_events",
        *SHARED_COLUMNS,
        sa.Column(
            "username_attempted",
            sa.String(length=50),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "result IN ('SUCCESS', 'FAILURE')",
            name="ck_admin_login_events_result",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0", name="ck_admin_login_events_duration_ms"
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN"
            " ('UNKNOWN_ACCOUNT', 'BAD_PASSWORD', 'DISABLED')",
            name="ck_admin_login_events_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_admin_login_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_admin_login_events"),
    )
    op.create_index(
        "ix_admin_login_events_occurred_at_event_id",
        "admin_login_events",
        [sa.text("occurred_at DESC"), sa.text("event_id DESC")],
    )
    op.create_index(
        "ix_admin_login_events_actor_occurred_at",
        "admin_login_events",
        ["actor_user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_admin_login_events_result_occurred_at",
        "admin_login_events",
        ["result", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_admin_login_events_username",
        "admin_login_events",
        ["username_attempted"],
    )
    op.create_index(
        "ix_admin_login_events_reason_code",
        "admin_login_events",
        ["reason_code"],
    )

    op.create_table(
        "admin_audit_events",
        *SHARED_COLUMNS,
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "result IN ('SUCCESS', 'FAILURE')",
            name="ck_admin_audit_events_result",
        ),
        sa.CheckConstraint(
            "duration_ms >= 0", name="ck_admin_audit_events_duration_ms"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_admin_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_admin_audit_events"),
    )
    op.create_index(
        "ix_admin_audit_events_occurred_at_event_id",
        "admin_audit_events",
        [sa.text("occurred_at DESC"), sa.text("event_id DESC")],
    )
    op.create_index(
        "ix_admin_audit_events_actor_occurred_at",
        "admin_audit_events",
        ["actor_user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_admin_audit_events_result_occurred_at",
        "admin_audit_events",
        ["result", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_admin_audit_events_event_type_occurred_at",
        "admin_audit_events",
        ["event_type", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_admin_audit_events_target",
        "admin_audit_events",
        ["target_type", "target_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_events_target", table_name="admin_audit_events"
    )
    op.drop_index(
        "ix_admin_audit_events_event_type_occurred_at",
        table_name="admin_audit_events",
    )
    op.drop_index(
        "ix_admin_audit_events_result_occurred_at",
        table_name="admin_audit_events",
    )
    op.drop_index(
        "ix_admin_audit_events_actor_occurred_at",
        table_name="admin_audit_events",
    )
    op.drop_index(
        "ix_admin_audit_events_occurred_at_event_id",
        table_name="admin_audit_events",
    )
    op.drop_table("admin_audit_events")

    op.drop_index(
        "ix_admin_login_events_reason_code", table_name="admin_login_events"
    )
    op.drop_index(
        "ix_admin_login_events_username", table_name="admin_login_events"
    )
    op.drop_index(
        "ix_admin_login_events_result_occurred_at",
        table_name="admin_login_events",
    )
    op.drop_index(
        "ix_admin_login_events_actor_occurred_at",
        table_name="admin_login_events",
    )
    op.drop_index(
        "ix_admin_login_events_occurred_at_event_id",
        table_name="admin_login_events",
    )
    op.drop_table("admin_login_events")
