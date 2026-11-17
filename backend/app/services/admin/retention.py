"""留存清理执行：批删除、预算检查与计数（主文档 §5.4/§10.2）。"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.admin_jobs import (
    AUDIT_RETENTION_DAYS,
    BATCH_SIZE,
    DELETION_TABLES,
    JOB_RUN_RETENTION_DAYS,
    LOGIN_RETENTION_DAYS,
    MAX_ROWS_PER_ATTEMPT,
    MAX_SECONDS_PER_ATTEMPT,
    SESSION_RETENTION_DAYS,
)
from app.core.security import utc_now
from app.db.models_admin import AdminJobRun
from app.repositories.admin import retention as retention_repo

#: 可在测试中替换的单调时钟。
_monotonic = time.monotonic


@dataclass
class RetentionResult:
    counts: dict[str, int] = field(default_factory=dict)
    rows: int = 0
    partial: bool = False
    counts_complete: bool = True


def _cutoffs(as_of: datetime) -> dict[str, datetime]:
    return {
        "admin_login_events": as_of - timedelta(days=LOGIN_RETENTION_DAYS),
        "admin_audit_events": as_of - timedelta(days=AUDIT_RETENTION_DAYS),
        "admin_job_runs": as_of - timedelta(days=JOB_RUN_RETENTION_DAYS),
        "auth_sessions": as_of - timedelta(days=SESSION_RETENTION_DAYS),
        "token_revocations": as_of,
    }


def run_retention(
    db: Session,
    run: AdminJobRun,
    *,
    active_run_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> RetentionResult:
    """按固定顺序分批删除；每批删除 + 计数 + 心跳同一事务。"""

    as_of = now or utc_now()
    cutoffs = _cutoffs(as_of)
    result = RetentionResult(counts=dict(run.counts or {}))
    started = _monotonic()

    try:
        for table in DELETION_TABLES:
            while True:
                elapsed = _monotonic() - started
                if (
                    result.rows >= MAX_ROWS_PER_ATTEMPT
                    or elapsed >= MAX_SECONDS_PER_ATTEMPT
                ):
                    result.partial = True
                    db.commit()
                    return result
                deleted = retention_repo.delete_batch(
                    db,
                    table,
                    cutoff=cutoffs[table],
                    limit=BATCH_SIZE,
                    run_id=run.id,
                    active_run_id=active_run_id,
                )
                if deleted:
                    result.counts[table] = (
                        result.counts.get(table, 0) + deleted
                    )
                    result.rows += deleted
                    run.counts = dict(result.counts)
                    run.heartbeat_at = utc_now()
                    db.commit()
                if deleted < BATCH_SIZE:
                    break
        db.commit()
    except Exception:
        # 提交结果未知：明确标记计数不完整，不编造精确删除量。
        db.rollback()
        result.counts_complete = False
        raise
    return result
