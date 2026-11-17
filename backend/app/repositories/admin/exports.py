"""导出查询仓储：按 (时间列, 主键) 降序键集分批，避免一次性载入全表。"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, cast, select, tuple_
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.models_admin import AdminAuditEvent, AdminLoginEvent
from app.repositories.admin.users import UserRecord, role_projection

EXPORT_BATCH_SIZE = 1000


def user_batch(
    db: Session,
    *,
    username: str | None,
    nickname: str | None,
    role: str | None,
    status: str | None,
    after: tuple[datetime, int] | None,
    limit: int = EXPORT_BATCH_SIZE,
) -> list[UserRecord]:
    role_sq, role_expr = role_projection()
    stmt = (
        select(
            User.id,
            User.username,
            User.nickname,
            role_expr.label("role"),
            User.status,
            User.created_at,
            User.updated_at,
        )
        .outerjoin(role_sq, role_sq.c.user_id == User.id)
    )
    if username:
        stmt = stmt.where(User.username.contains(username, autoescape=True))
    if nickname:
        stmt = stmt.where(User.nickname.contains(nickname, autoescape=True))
    if role == "admin":
        stmt = stmt.where(role_expr == "admin")
    elif role == "student":
        stmt = stmt.where(
            role_sq.c.is_student.is_(True), role_sq.c.is_admin.is_not(True)
        )
    if status:
        stmt = stmt.where(User.status == status)
    if after is not None:
        stmt = stmt.where(tuple_(User.created_at, User.id) < tuple_(*after))

    rows = db.execute(
        stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit)
    ).all()
    return [UserRecord(**row._mapping) for row in rows]


def login_batch(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    username: str | None,
    result: str | None,
    failure_type: str | None,
    ip: str | None,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int = EXPORT_BATCH_SIZE,
) -> list[AdminLoginEvent]:
    stmt = select(AdminLoginEvent).where(
        AdminLoginEvent.occurred_at >= start,
        AdminLoginEvent.occurred_at < end,
    )
    if username:
        stmt = stmt.where(
            AdminLoginEvent.username_attempted.contains(username, autoescape=True)
        )
    if result:
        stmt = stmt.where(AdminLoginEvent.result == result)
    if failure_type:
        stmt = stmt.where(AdminLoginEvent.reason_code == failure_type)
    if ip:
        stmt = stmt.where(cast(AdminLoginEvent.ip, String) == ip)
    if after is not None:
        stmt = stmt.where(
            tuple_(AdminLoginEvent.occurred_at, AdminLoginEvent.event_id)
            < tuple_(*after)
        )
    return list(
        db.scalars(
            stmt.order_by(
                AdminLoginEvent.occurred_at.desc(),
                AdminLoginEvent.event_id.desc(),
            ).limit(limit)
        ).all()
    )


def operation_batch(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    actor_username: str | None,
    event_type: str | None,
    result: str | None,
    target_type: str | None,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int = EXPORT_BATCH_SIZE,
) -> list[AdminAuditEvent]:
    stmt = select(AdminAuditEvent).where(
        AdminAuditEvent.occurred_at >= start,
        AdminAuditEvent.occurred_at < end,
    )
    if actor_username:
        stmt = stmt.where(
            AdminAuditEvent.actor_name.contains(actor_username, autoescape=True)
        )
    if event_type:
        stmt = stmt.where(AdminAuditEvent.event_type == event_type)
    if result:
        stmt = stmt.where(AdminAuditEvent.result == result)
    if target_type:
        stmt = stmt.where(AdminAuditEvent.target_type == target_type)
    if after is not None:
        stmt = stmt.where(
            tuple_(AdminAuditEvent.occurred_at, AdminAuditEvent.event_id)
            < tuple_(*after)
        )
    return list(
        db.scalars(
            stmt.order_by(
                AdminAuditEvent.occurred_at.desc(),
                AdminAuditEvent.event_id.desc(),
            ).limit(limit)
        ).all()
    )


@dataclass(frozen=True)
class ExportPage:
    rows: list
    exhausted: bool
