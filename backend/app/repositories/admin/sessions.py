"""在线会话查询仓储：同一 as_of 的过滤集、计数与分页。"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.models_admin import AuthSession
from app.repositories.admin.users import role_projection

ONLINE_WINDOW = "5 minutes"


@dataclass(frozen=True)
class SessionRecord:
    id: uuid.UUID
    user_id: int
    username: str
    role: str | None
    ip: str | None
    user_agent: str
    issued_at: datetime
    last_activity_at: datetime
    expires_at: datetime


def _online_select(as_of: datetime, window_start: datetime):
    role_sq, role_expr = role_projection()
    stmt = (
        select(
            AuthSession.id,
            AuthSession.user_id,
            User.username,
            role_expr.label("role"),
            AuthSession.ip,
            AuthSession.user_agent,
            AuthSession.issued_at,
            AuthSession.last_activity_at,
            AuthSession.expires_at,
        )
        .join(User, User.id == AuthSession.user_id)
        .outerjoin(role_sq, role_sq.c.user_id == User.id)
        .where(
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > as_of,
            User.status == "active",
            AuthSession.auth_version == User.auth_version,
            AuthSession.last_activity_at > window_start,
        )
    )
    return stmt, role_expr


def list_online_sessions(
    db: Session,
    *,
    as_of: datetime,
    window_start: datetime,
    username: str | None,
    role: str | None,
    page: int,
    page_size: int,
) -> tuple[list[SessionRecord], int, int, int]:
    """返回 (当前页记录, total, active_account_count, active_session_count)。"""

    stmt, role_expr = _online_select(as_of, window_start)
    if username:
        stmt = stmt.where(User.username.contains(username, autoescape=True))
    if role:
        stmt = stmt.where(role_expr == role)

    subquery = stmt.subquery()
    total_sessions = db.scalar(
        select(func.count()).select_from(subquery)
    )
    total_accounts = db.scalar(
        select(func.count(func.distinct(subquery.c.user_id)))
    )
    rows = db.execute(
        stmt.order_by(
            AuthSession.last_activity_at.desc(), AuthSession.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    records = [
        SessionRecord(
            id=row.id,
            user_id=row.user_id,
            username=row.username,
            role=row.role,
            ip=row.ip,
            user_agent=row.user_agent,
            issued_at=row.issued_at,
            last_activity_at=row.last_activity_at,
            expires_at=row.expires_at,
        )
        for row in rows
    ]
    return (
        records,
        int(total_sessions or 0),
        int(total_accounts or 0),
        int(total_sessions or 0),
    )
