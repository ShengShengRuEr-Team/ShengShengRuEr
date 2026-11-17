"""管理端阶段一 T01：users.auth_version 与持久会话 auth_sessions

Revision ID: 0006_admin_auth_session
Revises: 0005_attempt_system
Create Date: 2026-11-17

只做两件事：
1. 给既有 users 表增加 `auth_version`（NOT NULL DEFAULT 0，CHECK >= 0），
   存量用户自动为 0，不改旧字段、不改角色关系。
2. 新建 `auth_sessions`：一次登录一行，只存 jti 的 SHA-256 指纹，
   不存原始 JWT/jti；含用户、版本、签发/到期/最近活动、撤销事实与来源信息。

不 seed 账号、不写数据迁移。``downgrade()`` 逆序删索引、删表、删约束与列，
可回到 0005 的既有结构。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_admin_auth_session"
down_revision: str | None = "0005_attempt_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_check_constraint(
        "ck_users_auth_version", "users", "auth_version >= 0"
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("jti_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=32), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "user_agent",
            sa.String(length=256),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "auth_version >= 0", name="ck_auth_sessions_auth_version"
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoke_reason IS NULL)"
            " OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)",
            name="ck_auth_sessions_revocation_pair",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("jti_hash", name="uq_auth_sessions_jti_hash"),
    )
    op.create_index(
        "ix_auth_sessions_user_revoked_expires",
        "auth_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "ix_auth_sessions_last_activity_id",
        "auth_sessions",
        [sa.text("last_activity_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index(
        "ix_auth_sessions_last_activity_id", table_name="auth_sessions"
    )
    op.drop_index(
        "ix_auth_sessions_user_revoked_expires", table_name="auth_sessions"
    )
    op.drop_table("auth_sessions")
    op.drop_constraint("ck_users_auth_version", "users", type_="check")
    op.drop_column("users", "auth_version")
