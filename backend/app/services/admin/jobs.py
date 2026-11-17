"""留存任务状态机：补跑、重试、中断恢复、互斥与执行（主文档 §10.1—§10.3）。"""

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.admin_jobs import (
    ADVISORY_LOCK_KEY,
    JOB_ID,
    RETRY_DELAY_SECONDS,
    RUNNING_STALE_SECONDS,
    STATE_FAILED,
    STATE_INTERRUPTED,
    STATE_PARTIAL,
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_SUCCEEDED,
    TRIGGER_SCHEDULED,
    latest_slot_before,
    next_run_after,
    slot_key_for,
)
from app.core.security import utc_now
from app.db.base import SessionLocal, engine
from app.db.models_admin import AdminJobRun
from app.repositories.admin import jobs as jobs_repo
from app.services.admin import audit, retention

logger = logging.getLogger(__name__)


@contextmanager
def advisory_connection() -> Iterator[object | None]:
    """专用物理连接上的 session 级锁；异常路径释放并关闭，不还池。"""

    connection = engine.connect()
    acquired = False
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": ADVISORY_LOCK_KEY},
            ).scalar()
        )
        # advisory lock 是会话级；结束 SELECT 开启的事务，避免 Session 的
        # commit 只是内部子事务、连接关闭时整体回滚。
        connection.commit()
        yield connection if acquired else None
    finally:
        try:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": ADVISORY_LOCK_KEY},
                )
                connection.commit()
        finally:
            connection.close()


def _enqueue_event(
    db: Session, event_type: str, *, run_id: uuid.UUID, summary: dict
) -> None:
    audit.enqueue_audit_event(
        db,
        audit.AuditEvent(
            event_type=event_type,
            result=audit.RESULT_SUCCESS,
            actor_user_id=None,
            actor_name="scheduler",
            role_snapshot=None,
            target_type="job",
            target_id=JOB_ID,
            summary_values=summary,
            request_id=uuid.uuid4(),
        ),
    )


def ensure_next_scheduled(db: Session, now: datetime) -> None:
    definition = jobs_repo.lock_definition(db)
    if definition.next_scheduled_at is None:
        definition.next_scheduled_at = next_run_after(now)
        db.commit()
    else:
        db.rollback()


def recover_stale_runs(db: Session, now: datetime) -> int:
    """RUNNING 心跳 >120 秒仅是候选；调用方必须已持有任务锁。"""

    threshold = now - timedelta(seconds=RUNNING_STALE_SECONDS)
    stale = list(
        db.scalars(
            select(AdminJobRun).where(
                AdminJobRun.job_id == JOB_ID,
                AdminJobRun.state == STATE_RUNNING,
                AdminJobRun.heartbeat_at < threshold,
            )
        ).all()
    )
    if not stale:
        return 0

    definition = jobs_repo.lock_definition(db)
    for run in stale:
        if run.attempt_count < 2:
            run.state = STATE_QUEUED
            run.queued_at = now
            run.retry_pending = False
            run.retry_at = None
        else:
            run.state = STATE_INTERRUPTED
            run.finished_at = now
            run.retry_pending = False
            if definition.active_run_id == run.id:
                definition.active_run_id = None
                definition.last_run_id = run.id
        run.heartbeat_at = now
    db.commit()
    return len(stale)


def catch_up(db: Session, now: datetime) -> AdminJobRun | None:
    """最近 24 小时只补最近一个 03:10；更早只累计 missed_slots。"""

    definition = jobs_repo.lock_definition(db)
    if not definition.enabled:
        db.rollback()
        return None

    latest = latest_slot_before(now)
    slot = slot_key_for(latest)
    missed = 0
    if definition.last_scheduled_slot is not None:
        missed = max(0, (slot - definition.last_scheduled_slot).days - 1)

    if definition.last_scheduled_slot == slot:
        definition.next_scheduled_at = next_run_after(now)
        db.commit()
        return None

    existing = db.scalar(
        select(AdminJobRun).where(
            AdminJobRun.job_id == JOB_ID,
            AdminJobRun.trigger == TRIGGER_SCHEDULED,
            AdminJobRun.slot_key == slot,
        )
    )
    if existing is not None:
        definition.last_scheduled_slot = slot
        definition.next_scheduled_at = next_run_after(now)
        db.commit()
        return None

    active = jobs_repo.active_run(db)
    if active is not None:
        # 已有保留位：本次计划不新建，等当前 run 结束后的下一个计划。
        definition.next_scheduled_at = next_run_after(now)
        db.commit()
        return None

    run = AdminJobRun(
        id=uuid.uuid4(),
        job_id=JOB_ID,
        trigger=TRIGGER_SCHEDULED,
        slot_key=slot,
        state=STATE_QUEUED,
        queued_at=now,
        attempt_count=0,
        counts={},
        counts_complete=True,
    )
    db.add(run)
    definition.active_run_id = run.id
    definition.last_scheduled_slot = slot
    definition.missed_slots += missed
    definition.next_scheduled_at = next_run_after(now)
    _enqueue_event(
        db,
        audit.EVENT_JOB_TRIGGERED,
        run_id=run.id,
        summary={"run_id": str(run.id)},
    )
    db.commit()
    return run


def claim_queued(db: Session, now: datetime) -> AdminJobRun | None:
    run = jobs_repo.queued_retry_due(db, now=now)
    if run is None:
        return None
    if run.retry_pending and run.retry_at is not None and run.retry_at > now:
        db.rollback()
        return None
    run.state = STATE_RUNNING
    run.started_at = now
    run.heartbeat_at = now
    run.attempt_count = min(2, run.attempt_count + 1)
    run.retry_pending = False
    run.retry_at = None
    db.commit()
    return run


def finish_run(
    db: Session,
    run: AdminJobRun,
    *,
    state: str,
    counts: dict[str, int],
    counts_complete: bool,
    error_code: str | None = None,
) -> None:
    now = utc_now()
    definition = jobs_repo.lock_definition(db)
    run.state = state
    run.counts = dict(counts)
    run.counts_complete = counts_complete
    run.error_code = error_code
    run.heartbeat_at = now
    run.finished_at = now

    if state == STATE_FAILED and run.attempt_count < 2:
        run.retry_pending = True
        run.retry_at = now + timedelta(seconds=RETRY_DELAY_SECONDS)
    else:
        run.retry_pending = False
        run.retry_at = None
        if definition.active_run_id == run.id:
            definition.active_run_id = None
            definition.last_run_id = run.id

    _enqueue_event(
        db,
        audit.EVENT_JOB_FINISHED,
        run_id=run.id,
        summary={
            "run_id": str(run.id),
            "state": state,
            "counts_complete": counts_complete,
        },
    )
    db.commit()


def execute_claimed(db: Session, run: AdminJobRun) -> None:
    definition = jobs_repo.get_definition(db)
    try:
        result = retention.run_retention(
            db, run, active_run_id=definition.active_run_id if definition else None
        )
    except Exception:
        finish_run(
            db,
            run,
            state=STATE_FAILED,
            counts=dict(run.counts or {}),
            counts_complete=False,
            error_code="deletion_failed",
        )
        raise

    state = STATE_PARTIAL if result.partial else STATE_SUCCEEDED
    finish_run(
        db,
        run,
        state=state,
        counts=result.counts,
        counts_complete=result.counts_complete,
    )


def promote_due_retries(db: Session, now: datetime) -> None:
    """FAILED + retry_pending 且到期的 run 回到队列（同 run，不新建 slot）。"""

    rows = list(
        db.scalars(
            select(AdminJobRun).where(
                AdminJobRun.job_id == JOB_ID,
                AdminJobRun.state == STATE_FAILED,
                AdminJobRun.retry_pending.is_(True),
                AdminJobRun.retry_at <= now,
            )
        ).all()
    )
    for run in rows:
        run.state = STATE_QUEUED
        run.queued_at = now
    if rows:
        db.commit()


def tick(*, now: datetime | None = None) -> dict:
    """一次调度 tick：获锁后恢复中断 → 补跑 → 领取并执行。"""

    moment = now or utc_now()
    with advisory_connection() as connection:
        if connection is None:
            return {"acquired": False}
        db = Session(bind=connection)
        try:
            ensure_next_scheduled(db, moment)
            recover_stale_runs(db, moment)
            promote_due_retries(db, moment)
            catch_up(db, moment)
            run = claim_queued(db, moment)
            if run is None:
                return {"acquired": True, "executed": None}
            try:
                execute_claimed(db, run)
            except Exception:
                logger.exception("留存清理执行失败 run_id=%s", run.id)
            return {"acquired": True, "executed": str(run.id)}
        finally:
            db.close()


# --------------------------------------------------------------------------- #
# 控制 API（T07c）
# --------------------------------------------------------------------------- #

from app.core.errors import bad_request  # noqa: E402
from app.schemas_admin.jobs import (  # noqa: E402
    JobDefinitionOut,
    JobEnabledResult,
    JobOverviewOut,
    JobRunOut,
    SchedulerInstanceOut,
)
from app.services.admin import events  # noqa: E402


def scheduler_health(db: Session, now: datetime | None = None) -> str:
    from sqlalchemy import func

    from app.core.admin_jobs import HEARTBEAT_STALE_SECONDS
    from app.db.models_admin import AdminJobSchedulerState

    moment = now or utc_now()
    latest = db.scalar(select(func.max(AdminJobSchedulerState.heartbeat_at)))
    if latest is None:
        return "not_configured"
    return (
        "ok"
        if (moment - latest).total_seconds() <= HEARTBEAT_STALE_SECONDS
        else "stale"
    )


def build_overview(db: Session, now: datetime | None = None) -> JobOverviewOut:
    definition = jobs_repo.get_definition(db)
    if definition is None:  # pragma: no cover - 迁移已 seed
        raise RuntimeError("缺少任务定义")
    schedulers = jobs_repo.list_schedulers(db)
    return JobOverviewOut(
        job=JobDefinitionOut(
            job_id=definition.job_id,
            enabled=definition.enabled,
            timezone=definition.timezone,
            next_scheduled_at=definition.next_scheduled_at,
            last_scheduled_slot=definition.last_scheduled_slot,
            last_run_id=definition.last_run_id,
            active_run_id=definition.active_run_id,
            missed_slots=definition.missed_slots,
            updated_at=definition.updated_at,
        ),
        scheduler_health=scheduler_health(db, now),
        instances=[
            SchedulerInstanceOut(
                instance_id=row.instance_id,
                booted_at=row.booted_at,
                heartbeat_at=row.heartbeat_at,
                last_error_code=row.last_error_code,
                state=row.state,
                version=row.version,
            )
            for row in schedulers
        ],
    )


def to_run_out(run: AdminJobRun) -> JobRunOut:
    return JobRunOut(
        id=run.id,
        job_id=run.job_id,
        trigger=run.trigger,
        slot_key=run.slot_key,
        actor_id=run.actor_id,
        state=run.state,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        heartbeat_at=run.heartbeat_at,
        attempt_count=run.attempt_count,
        retry_at=run.retry_at,
        retry_pending=run.retry_pending,
        counts=dict(run.counts or {}),
        counts_complete=run.counts_complete,
        error_code=run.error_code,
        created_at=run.created_at,
    )


def set_enabled(
    db: Session,
    *,
    actor,
    enabled: bool,
    reason: str,
    request_id,
    ip,
    user_agent,
    started_at: float,
) -> JobEnabledResult:
    definition = jobs_repo.lock_definition(db)
    changed = definition.enabled != enabled
    if changed:
        definition.enabled = enabled
        if enabled:
            definition.next_scheduled_at = next_run_after(utc_now())
        events.enqueue_success(
            db,
            event_type=(
                audit.EVENT_JOB_RESUMED if enabled else audit.EVENT_JOB_PAUSED
            ),
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            summary_values={"enabled": enabled},
            target_type="job",
            target_id=JOB_ID,
        )
    db.commit()
    return JobEnabledResult(
        job_id=definition.job_id,
        enabled=definition.enabled,
        changed=changed,
    )


def trigger_manual(
    db: Session,
    *,
    actor,
    reason: str,
    request_id,
    ip,
    user_agent,
    started_at: float,
) -> uuid.UUID:
    from sqlalchemy import func

    now = utc_now()

    def reject(code: str) -> Exception:
        return events.reject(
            db,
            bad_request(
                "调度进程不可用" if code == "scheduler_unavailable" else "任务正在运行"
            ),
            event_type=audit.EVENT_JOB_TRIGGERED,
            actor=actor,
            reason_code=code,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="job",
            target_id=JOB_ID,
        )

    if scheduler_health(db, now) != "ok":
        raise reject("scheduler_unavailable")

    # 事务级锁与 QUEUED 插入同事务：HTTP 线程不持有 session 级连接。
    locked = db.scalar(
        select(func.pg_try_advisory_xact_lock(ADVISORY_LOCK_KEY))
    )
    if not locked:
        raise reject("job_running")

    definition = jobs_repo.lock_definition(db)
    if definition.active_run_id is not None or jobs_repo.active_run(db):
        raise reject("job_running")

    run = AdminJobRun(
        id=uuid.uuid4(),
        job_id=JOB_ID,
        trigger="manual",
        state=STATE_QUEUED,
        queued_at=now,
        actor_id=actor.id,
        counts={},
        counts_complete=True,
    )
    db.add(run)
    definition.active_run_id = run.id
    events.enqueue_success(
        db,
        event_type=audit.EVENT_JOB_TRIGGERED,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={"run_id": str(run.id)},
        target_type="job",
        target_id=JOB_ID,
    )
    db.commit()
    return run.id
