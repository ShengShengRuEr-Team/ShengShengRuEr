"""管理端数据模型。

- 持久会话：`auth_sessions`（T01）。对外会话标识为 UUID；只存 jti 的
  SHA-256 指纹，不存原始 JWT 或 jti。
- 两类审计事件：`admin_login_events`、`admin_audit_events`（T02）。两表独立，
  共享列相同；登录表另存声明用户名与失败类型，操作表另存 `run_id`（纯追溯）。

users.auth_version 属于既有 users 表的增量列，定义在 `app.db.models`。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
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


class AdminLoginEvent(Base):
    """登录事件：成功与失败都记，未知账号也留声明用户名。"""

    __tablename__ = "admin_login_events"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS', 'FAILURE')", name="result"
        ),
        CheckConstraint("duration_ms >= 0", name="duration_ms"),
        CheckConstraint(
            "reason_code IS NULL OR reason_code IN"
            " ('UNKNOWN_ACCOUNT', 'BAD_PASSWORD', 'DISABLED')",
            name="reason_code",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", server_default=""
    )
    role_snapshot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", server_default=""
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    username_attempted: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", server_default=""
    )


class AdminAuditEvent(Base):
    """操作审计事件：业务成功与业务拒绝分别记录。"""

    __tablename__ = "admin_audit_events"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS', 'FAILURE')", name="result"
        ),
        CheckConstraint("duration_ms >= 0", name="duration_ms"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", server_default=""
    )
    role_snapshot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", server_default=""
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # 纯追溯字段：不设级联外键，不被任务清理牵连。
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


Index(
    "ix_admin_login_events_occurred_at_event_id",
    AdminLoginEvent.occurred_at.desc(),
    AdminLoginEvent.event_id.desc(),
)
Index(
    "ix_admin_login_events_actor_occurred_at",
    AdminLoginEvent.actor_user_id,
    AdminLoginEvent.occurred_at.desc(),
)
Index(
    "ix_admin_login_events_result_occurred_at",
    AdminLoginEvent.result,
    AdminLoginEvent.occurred_at.desc(),
)
Index("ix_admin_login_events_username", AdminLoginEvent.username_attempted)
Index("ix_admin_login_events_reason_code", AdminLoginEvent.reason_code)

Index(
    "ix_admin_audit_events_occurred_at_event_id",
    AdminAuditEvent.occurred_at.desc(),
    AdminAuditEvent.event_id.desc(),
)
Index(
    "ix_admin_audit_events_actor_occurred_at",
    AdminAuditEvent.actor_user_id,
    AdminAuditEvent.occurred_at.desc(),
)
Index(
    "ix_admin_audit_events_result_occurred_at",
    AdminAuditEvent.result,
    AdminAuditEvent.occurred_at.desc(),
)
Index(
    "ix_admin_audit_events_event_type_occurred_at",
    AdminAuditEvent.event_type,
    AdminAuditEvent.occurred_at.desc(),
)
Index(
    "ix_admin_audit_events_target",
    AdminAuditEvent.target_type,
    AdminAuditEvent.target_id,
)


class AdminJobDefinition(Base):
    """唯一留存任务的配置与保留位；job_id 由 CHECK 固定为白名单编码。"""

    __tablename__ = "admin_job_definitions"
    __table_args__ = (
        CheckConstraint(
            "job_id = 'admin.retention_cleanup'", name="job_id"
        ),
        CheckConstraint("missed_slots >= 0", name="missed_slots"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    next_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_scheduled_slot: Mapped[datetime | None] = mapped_column(
        Date, nullable=True
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    missed_slots: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AdminJobRun(Base):
    """一次保留执行；slot 唯一与活动保留位由部分唯一索引兜底。"""

    __tablename__ = "admin_job_runs"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('scheduled', 'manual')", name="trigger"
        ),
        CheckConstraint(
            "(trigger = 'scheduled' AND slot_key IS NOT NULL)"
            " OR (trigger = 'manual' AND slot_key IS NULL)",
            name="slot_rule",
        ),
        CheckConstraint(
            "state IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL',"
            " 'FAILED', 'INTERRUPTED')",
            name="state",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 0 AND 2", name="attempt_count"
        ),
        Index(
            "uq_admin_job_runs_slot",
            "job_id",
            "slot_key",
            unique=True,
            postgresql_where=text("trigger = 'scheduled'"),
        ),
        Index(
            "uq_admin_job_runs_active",
            "job_id",
            unique=True,
            postgresql_where=text("state IN ('QUEUED', 'RUNNING')"),
        ),
        Index(
            "ix_admin_job_runs_job_created",
            "job_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    slot_key: Mapped[object | None] = mapped_column(Date, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="QUEUED", server_default="QUEUED"
    )
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    counts_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdminJobSchedulerState(Base):
    """每个调度进程一行；不制造“全局单行在线”的假象。"""

    __tablename__ = "admin_job_scheduler_state"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    booted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


Index(
    "ix_admin_job_scheduler_state_heartbeat",
    AdminJobSchedulerState.heartbeat_at,
)
