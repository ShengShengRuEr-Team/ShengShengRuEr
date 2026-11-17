"""在线会话服务：同一 as_of 的一致快照查询与单会话强退（主文档 §6.3）。"""

import uuid
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import bad_request, not_found
from app.core.security import utc_now
from app.db.models_admin import AuthSession
from app.repositories.admin import sessions as sessions_repo
from app.schemas_admin.sessions import SessionOut, SessionPage
from app.services.admin import audit, events, guards

FAILURE_SESSION_NOT_FOUND = "session_not_found"
FAILURE_CURRENT_SESSION = "current_session"

ONLINE_WINDOW = timedelta(minutes=5)
USER_AGENT_SUMMARY_LENGTH = 80


def list_sessions(
    db: Session,
    *,
    viewer: CurrentUser,
    username: str | None,
    role: str | None,
    page: int,
    page_size: int,
) -> SessionPage:
    # 计数、去重与分页基于同一快照；只读，不写活动时间。
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    as_of = utc_now()
    window_start = as_of - ONLINE_WINDOW

    records, total, active_accounts, active_sessions = (
        sessions_repo.list_online_sessions(
            db,
            as_of=as_of,
            window_start=window_start,
            username=username,
            role=role,
            page=page,
            page_size=page_size,
        )
    )
    items = [
        SessionOut(
            session_id=record.id,
            user_id=record.user_id,
            username=record.username,
            role=record.role,
            ip=record.ip,
            user_agent_summary=(record.user_agent or "")[
                :USER_AGENT_SUMMARY_LENGTH
            ],
            issued_at=record.issued_at,
            last_activity_at=record.last_activity_at,
            expires_at=record.expires_at,
            is_current=record.id == viewer.session_id,
        )
        for record in records
    ]
    return SessionPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        as_of=as_of,
        active_account_count=active_accounts,
        active_session_count=active_sessions,
    )


def revoke_session(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    session_id: uuid.UUID,
    reason: str,
) -> dict:
    event_type = audit.EVENT_SESSION_REVOKED
    target_id = str(session_id)

    guards.set_lock_timeout(db)
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.id == session_id)
        .with_for_update()
    )
    if session is None:
        raise events.reject(
            db,
            not_found("会话不存在"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_SESSION_NOT_FOUND,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="session",
            target_id=target_id,
        )
    if session.id == actor.session_id:
        raise events.reject(
            db,
            bad_request("不能强退当前会话"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_CURRENT_SESSION,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="session",
            target_id=target_id,
        )

    if session.revoked_at is not None or session.expires_at <= utc_now():
        # 已关闭会话视为幂等成功，不做状态变更，不写审计。
        db.rollback()
        return {"session_id": session_id, "changed": False}

    session.revoked_at = utc_now()
    session.revoke_reason = "kicked"
    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={
            "session_id": str(session.id),
            "target_user_id": session.user_id,
        },
        target_type="session",
        target_id=target_id,
    )
    db.commit()
    return {"session_id": session_id, "changed": True}
