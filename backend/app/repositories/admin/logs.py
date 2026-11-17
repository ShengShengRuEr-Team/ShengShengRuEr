"""审计日志查询仓储：固定筛选、分页与详情。

只构造查询，不提交事务、不写审计。
"""

import uuid
from datetime import datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.db.models_admin import AdminAuditEvent, AdminLoginEvent


def list_login_events(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    username: str | None,
    result: str | None,
    failure_type: str | None,
    ip: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AdminLoginEvent], int]:
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

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(
            AdminLoginEvent.occurred_at.desc(), AdminLoginEvent.event_id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def get_login_event(db: Session, event_id: uuid.UUID) -> AdminLoginEvent | None:
    return db.get(AdminLoginEvent, event_id)


def list_operation_events(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    actor_username: str | None,
    event_type: str | None,
    result: str | None,
    target_type: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AdminAuditEvent], int]:
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

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(
            AdminAuditEvent.occurred_at.desc(), AdminAuditEvent.event_id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def get_operation_event(
    db: Session, event_id: uuid.UUID
) -> AdminAuditEvent | None:
    return db.get(AdminAuditEvent, event_id)
