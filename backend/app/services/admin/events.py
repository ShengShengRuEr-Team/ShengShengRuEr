"""管理写操作的审计事件辅助：成功同事务、失败独立事务。

失败事件绝不覆盖原始 400/404/500；审计异常只记日志。
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.admin_permissions import role_snapshot
from app.core.errors import AppError
from app.core.request_context import elapsed_ms, new_event_id
from app.services.admin import audit

logger = logging.getLogger(__name__)


def enqueue_success(
    db: Session,
    *,
    event_type: str,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    summary_values: dict,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    audit.enqueue_audit_event(
        db,
        audit.AuditEvent(
            event_type=event_type,
            result=audit.RESULT_SUCCESS,
            event_id=new_event_id(),
            request_id=request_id,
            actor_user_id=actor.id,
            actor_name=actor.username,
            role_snapshot=role_snapshot(actor.roles),
            target_type=target_type,
            target_id=target_id,
            summary_values=summary_values,
            ip=ip,
            user_agent=user_agent,
            duration_ms=elapsed_ms(started_at),
        ),
    )


def record_failure(
    *,
    event_type: str,
    actor: CurrentUser,
    reason_code: str,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    event = audit.AuditEvent(
        event_type=event_type,
        result=audit.RESULT_FAILURE,
        event_id=new_event_id(),
        request_id=request_id,
        actor_user_id=actor.id,
        actor_name=actor.username,
        role_snapshot=role_snapshot(actor.roles),
        target_type=target_type,
        target_id=target_id,
        reason_code=reason_code,
        summary_values={},
        ip=ip,
        user_agent=user_agent,
        duration_ms=elapsed_ms(started_at),
    )
    try:
        audit.persist_audit_failure(event)
    except Exception:  # noqa: BLE001 - 失败审计不得影响原错误
        logger.exception(
            "管理操作失败审计异常 event_id=%s request_id=%s",
            event.event_id,
            event.request_id,
        )


def reject(
    db: Session,
    exc: AppError,
    *,
    event_type: str,
    actor: CurrentUser,
    reason_code: str,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    target_type: str | None = None,
    target_id: str | None = None,
) -> AppError:
    """回滚业务事务、记录失败事件，返回原异常供调用方 raise。"""

    db.rollback()
    record_failure(
        event_type=event_type,
        actor=actor,
        reason_code=reason_code,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        target_type=target_type,
        target_id=target_id,
    )
    return exc
