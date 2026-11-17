"""管理端数据模型。

- 持久会话：`auth_sessions`（T01）。对外会话标识为 UUID；只存 jti 的
  SHA-256 指纹，不存原始 JWT 或 jti。
- 两类审计事件：`admin_login_events`、`admin_audit_events`（T02）。

users.auth_version 属于既有 users 表的增量列，定义在 `app.db.models`。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthSession(Base):
    """一次登录对应一行；撤销或过期即不可再用。"""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("auth_version >= 0", name="auth_version"),
        CheckConstraint(
            "(revoked_at IS NULL AND revoke_reason IS NULL)"
            " OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)",
            name="revocation_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    jti_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    auth_version: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", server_default=""
    )


Index(
    "ix_auth_sessions_user_revoked_expires",
    AuthSession.user_id,
    AuthSession.revoked_at,
    AuthSession.expires_at,
)
Index(
    "ix_auth_sessions_last_activity_id",
    AuthSession.last_activity_at.desc(),
    AuthSession.id.desc(),
)
Index("ix_auth_sessions_expires_at", AuthSession.expires_at)
