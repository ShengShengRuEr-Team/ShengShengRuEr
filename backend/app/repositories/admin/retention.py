"""留存删除 SQL：固定白名单表、稳定 keyset、严格 `<` 边界（主文档 §5.4）。"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

LOGIN_DELETE = text(
    """
    DELETE FROM admin_login_events
    WHERE event_id IN (
        SELECT event_id FROM admin_login_events
        WHERE occurred_at < :cutoff
        ORDER BY occurred_at, event_id
        LIMIT :limit
    )
    """
)

AUDIT_DELETE = text(
    """
    DELETE FROM admin_audit_events
    WHERE event_id IN (
        SELECT event_id FROM admin_audit_events
        WHERE occurred_at < :cutoff
          AND (run_id IS NULL OR run_id <> :run_id)
        ORDER BY occurred_at, event_id
        LIMIT :limit
    )
    """
)

RUNS_DELETE = text(
    """
    DELETE FROM admin_job_runs
    WHERE id IN (
        SELECT id FROM admin_job_runs
        WHERE created_at < :cutoff
          AND state NOT IN ('QUEUED', 'RUNNING')
          AND retry_pending IS FALSE
          AND id <> :current_run_id
          AND (:active_run_id IS NULL OR id <> :active_run_id)
        ORDER BY created_at, id
        LIMIT :limit
    )
    """
)

SESSIONS_DELETE = text(
    """
    DELETE FROM auth_sessions
    WHERE id IN (
        SELECT id FROM auth_sessions
        WHERE greatest(expires_at, coalesce(revoked_at, expires_at)) < :cutoff
          AND (revoked_at IS NOT NULL OR expires_at <= now())
        ORDER BY expires_at, id
        LIMIT :limit
    )
    """
)

REVOCATIONS_DELETE = text(
    """
    DELETE FROM token_revocations
    WHERE id IN (
        SELECT id FROM token_revocations
        WHERE expires_at < :cutoff
        ORDER BY expires_at, id
        LIMIT :limit
    )
    """
)


def delete_batch(
    db: Session,
    table: str,
    *,
    cutoff: datetime,
    limit: int,
    run_id: uuid.UUID,
    active_run_id: uuid.UUID | None,
) -> int:
    if table == "admin_login_events":
        result = db.execute(LOGIN_DELETE, {"cutoff": cutoff, "limit": limit})
    elif table == "admin_audit_events":
        result = db.execute(
            AUDIT_DELETE,
            {"cutoff": cutoff, "limit": limit, "run_id": run_id},
        )
    elif table == "admin_job_runs":
        result = db.execute(
            RUNS_DELETE,
            {
                "cutoff": cutoff,
                "limit": limit,
                "current_run_id": run_id,
                "active_run_id": active_run_id,
            },
        )
    elif table == "auth_sessions":
        result = db.execute(
            SESSIONS_DELETE, {"cutoff": cutoff, "limit": limit}
        )
    elif table == "token_revocations":
        result = db.execute(
            REVOCATIONS_DELETE, {"cutoff": cutoff, "limit": limit}
        )
    else:  # pragma: no cover - 白名单外拒绝
        raise ValueError(f"不在删除白名单内的表：{table}")
    return int(result.rowcount or 0)
