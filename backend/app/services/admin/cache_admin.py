"""缓存监控与清理（§9.5/AC-20/21）。

清理顺序：CACHE_CLEAR_STARTED 独立提交（失败不删）→ 持实例缓存锁删除 →
CACHE_CLEARED 独立提交；删除后完成审计失败返回 500 并标记结果未确认。
"""

import uuid
from datetime import datetime

from app.api.deps import CurrentUser
from app.core.errors import AppError, bad_request
from app.core.request_context import elapsed_ms, new_event_id
from app.db.base import SessionLocal
from app.services.admin import audit, dashboard_cache, events


def overview_payload() -> dict:
    cache = dashboard_cache.get_dashboard_cache()
    metadata = cache.metadata()
    return {
        "domain": metadata["domain"],
        "instance_id": metadata["instance_id"],
        "enabled": metadata["enabled"],
        "entries": metadata["entries"],
        "ttl_seconds": metadata["ttl_seconds"],
        "hits": metadata["hits"],
        "misses": metadata["misses"],
        "redis": {"status": "not_configured", "reason": "redis_not_deployed"},
    }


def entries_payload() -> list[dict]:
    return dashboard_cache.get_dashboard_cache().entries_metadata()


def _write_event(
    db,
    event_type: str,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    summary: dict,
) -> None:
    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values=summary,
        target_type="cache",
        target_id=dashboard_cache.DOMAIN,
    )


def clear_cache(
    *,
    actor: CurrentUser,
    domain: str,
    expected_instance_id: str,
    reason: str,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
) -> int:
    cache = dashboard_cache.get_dashboard_cache()
    if domain != dashboard_cache.DOMAIN:
        raise bad_request("不支持的缓存域")
    if str(cache.instance_id) != expected_instance_id:
        raise bad_request("缓存实例不匹配，请在目标实例上重试")

    started_summary = {
        "domain": domain,
        "instance_id": str(cache.instance_id),
    }
    try:
        with SessionLocal() as db:
            _write_event(
                db,
                audit.EVENT_CACHE_CLEAR_STARTED,
                actor=actor,
                request_id=request_id,
                ip=ip,
                user_agent=user_agent,
                started_at=started_at,
                summary=started_summary,
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - STARTED 落库失败则不删
        raise AppError(500, "服务器内部错误") from exc

    with cache.build_lock:
        deleted_count = len(cache.entries_metadata())
        cache.clear()

    completed_summary = {
        "domain": domain,
        "instance_id": str(cache.instance_id),
        "deleted_count": deleted_count,
    }
    try:
        with SessionLocal() as db:
            _write_event(
                db,
                audit.EVENT_CACHE_CLEARED,
                actor=actor,
                request_id=request_id,
                ip=ip,
                user_agent=user_agent,
                started_at=started_at,
                summary=completed_summary,
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - 删除已发生，结果未确认
        try:
            audit.persist_audit_failure(
                audit.AuditEvent(
                    event_type=audit.EVENT_CACHE_CLEARED,
                    result=audit.RESULT_FAILURE,
                    event_id=new_event_id(),
                    request_id=request_id,
                    actor_user_id=actor.id,
                    actor_name=actor.username,
                    target_type="cache",
                    target_id=domain,
                    reason_code="audit_write_failed",
                    summary_values={},
                    ip=ip,
                    user_agent=user_agent,
                    duration_ms=elapsed_ms(started_at),
                )
            )
        except Exception:  # noqa: BLE001
            pass
        raise AppError(500, "服务器内部错误") from exc
    return deleted_count


def record_clear_failure(
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    reason_code: str,
    ip: str | None,
    user_agent: str,
    started_at: float,
) -> None:
    """清理拒绝事件走独立事务，不覆盖原始 400。"""

    event = audit.AuditEvent(
        event_type=audit.EVENT_CACHE_CLEARED,
        result=audit.RESULT_FAILURE,
        event_id=new_event_id(),
        request_id=request_id,
        actor_user_id=actor.id,
        actor_name=actor.username,
        target_type="cache",
        target_id=dashboard_cache.DOMAIN,
        reason_code=reason_code,
        summary_values={},
        ip=ip,
        user_agent=user_agent,
        duration_ms=elapsed_ms(started_at),
    )
    try:
        audit.persist_audit_failure(event)
    except Exception:  # noqa: BLE001
        pass
