"""T07b：调度状态机、互斥、补跑、重试与中断恢复（主文档 §10.1—§10.3）。"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

BEIJING = ZoneInfo("Asia/Shanghai")


def _session():
    from app.db.base import SessionLocal

    return SessionLocal


def _run_model():
    from app.db.models_admin import AdminJobRun

    return AdminJobRun


@pytest.fixture(autouse=True)
def reset_job_state():
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition, AdminJobRun

    SessionLocal = _session()
    with SessionLocal() as db:
        db.execute(delete(AdminJobRun))
        db.execute(
            text("DELETE FROM admin_audit_events WHERE target_type = 'job'")
        )
        definition = db.get(AdminJobDefinition, JOB_ID)
        definition.enabled = True
        definition.next_scheduled_at = None
        definition.last_scheduled_slot = None
        definition.active_run_id = None
        definition.last_run_id = None
        definition.missed_slots = 0
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(AdminJobRun))
        db.execute(
            text("DELETE FROM admin_audit_events WHERE target_type = 'job'")
        )
        definition = _definition(db)
        definition.enabled = True
        definition.next_scheduled_at = None
        definition.last_scheduled_slot = None
        definition.active_run_id = None
        definition.last_run_id = None
        definition.missed_slots = 0
        db.commit()


def _definition(db):
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition

    return db.get(AdminJobDefinition, JOB_ID)


def _make_run(db, **overrides):
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobRun

    values = {
        "id": uuid.uuid4(),
        "job_id": JOB_ID,
        "trigger": "manual",
        "state": "QUEUED",
        "queued_at": datetime.now(BEIJING),
        "attempt_count": 0,
        "counts": {},
        "counts_complete": True,
    }
    values.update(overrides)
    run = AdminJobRun(**values)
    db.add(run)
    db.commit()
    return run


def test_slot_and_active_uniqueness() -> None:
    from app.db.models_admin import AdminJobRun

    SessionLocal = _session()
    today = date(2026, 11, 17)
    with SessionLocal() as db:
        db.add(
            AdminJobRun(
                id=uuid.uuid4(),
                job_id="admin.retention_cleanup",
                trigger="scheduled",
                slot_key=today,
                state="QUEUED",
                queued_at=datetime.now(BEIJING),
                counts={},
            )
        )
        db.commit()

        db.add(
            AdminJobRun(
                id=uuid.uuid4(),
                job_id="admin.retention_cleanup",
                trigger="scheduled",
                slot_key=today,
                state="QUEUED",
                queued_at=datetime.now(BEIJING),
                counts={},
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_active_retention_unique() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _make_run(db)
        db.add(
            _run_model()(
                id=uuid.uuid4(),
                job_id="admin.retention_cleanup",
                trigger="manual",
                state="RUNNING",
                counts={},
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_catch_up_creates_latest_slot_and_counts_missed() -> None:
    from app.services.admin import jobs

    SessionLocal = _session()
    now = datetime(2026, 11, 17, 4, 0, tzinfo=BEIJING)
    with SessionLocal() as db:
        definition = _definition(db)
        definition.last_scheduled_slot = date(2026, 11, 14)
        db.commit()

        run = jobs.catch_up(db, now)
        assert run is not None
        assert run.slot_key == date(2026, 11, 17)
        assert run.trigger == "scheduled"
        definition = _definition(db)
        assert definition.missed_slots == 2  # 15、16 日错过多
        assert definition.active_run_id == run.id
        assert definition.next_scheduled_at.isoformat().startswith(
            "2026-11-18T03:10:00+08:00"
        )

        assert jobs.catch_up(db, now) is None
        assert db.scalar(
            text("SELECT count(*) FROM admin_job_runs")
        ) == 1


def test_paused_job_does_not_catch_up() -> None:
    from app.services.admin import jobs

    SessionLocal = _session()
    now = datetime(2026, 11, 17, 4, 0, tzinfo=BEIJING)
    with SessionLocal() as db:
        definition = _definition(db)
        definition.enabled = False
        definition.last_scheduled_slot = date(2026, 11, 14)
        db.commit()

        assert jobs.catch_up(db, now) is None
        definition = _definition(db)
        assert definition.missed_slots == 0
        assert db.scalar(text("SELECT count(*) FROM admin_job_runs")) == 0


def test_retry_flow_same_run_max_two_attempts() -> None:
    from app.services.admin import jobs

    SessionLocal = _session()
    now = datetime(2026, 11, 17, 10, 0, tzinfo=BEIJING)
    with SessionLocal() as db:
        run = _make_run(db)
        _definition(db).active_run_id = run.id
        db.commit()

        claimed = jobs.claim_queued(db, now)
        assert claimed is not None and claimed.state == "RUNNING"
        assert claimed.attempt_count == 1

        jobs.finish_run(
            db,
            claimed,
            state="FAILED",
            counts={},
            counts_complete=False,
            error_code="deletion_failed",
        )
        db.refresh(claimed)
        assert claimed.retry_pending is True
        assert claimed.retry_at is not None

        jobs.promote_due_retries(db, claimed.retry_at - timedelta(seconds=1))
        db.refresh(claimed)
        assert claimed.state == "FAILED"
        assert jobs.claim_queued(db, claimed.retry_at) is None

        jobs.promote_due_retries(db, claimed.retry_at + timedelta(seconds=1))
        db.refresh(claimed)
        assert claimed.state == "QUEUED"

        second = jobs.claim_queued(db, claimed.retry_at + timedelta(seconds=2))
        assert second is not None and second.attempt_count == 2

        jobs.finish_run(
            db,
            second,
            state="FAILED",
            counts={},
            counts_complete=False,
            error_code="deletion_failed",
        )
        db.refresh(second)
        assert second.retry_pending is False
        assert _definition(db).active_run_id is None


def test_stale_running_requeues_or_interrupts_after_lock() -> None:
    from app.services.admin import jobs

    SessionLocal = _session()
    now = datetime(2026, 11, 17, 10, 0, tzinfo=BEIJING)
    stale = now - timedelta(seconds=130)

    with SessionLocal() as db:
        run = _make_run(db, state="RUNNING", attempt_count=1, heartbeat_at=stale)
        _definition(db).active_run_id = run.id
        db.commit()

        assert jobs.recover_stale_runs(db, now) == 1
        db.refresh(run)
        assert run.state == "QUEUED"

    with SessionLocal() as db:
        db.execute(delete(_run_model()))
        db.commit()
        run = _make_run(db, state="RUNNING", attempt_count=2, heartbeat_at=stale)
        _definition(db).active_run_id = run.id
        db.commit()

        assert jobs.recover_stale_runs(db, now) == 1
        db.refresh(run)
        assert run.state == "INTERRUPTED"
        assert _definition(db).active_run_id is None


def test_advisory_lock_blocks_second_executor() -> None:
    from app.services.admin import jobs

    with jobs.advisory_connection() as connection:
        assert connection is not None
        result = jobs.tick()
    assert result["acquired"] is False


def test_lock_released_after_exception(monkeypatch) -> None:
    from app.services.admin import jobs

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs, "recover_stale_runs", _boom)
    with pytest.raises(RuntimeError):
        jobs.tick()

    # 异常路径必须释放 session 级锁，后续执行者能立刻获锁。
    with jobs.advisory_connection() as connection:
        assert connection is not None


def test_manual_trigger_xact_lock_is_released_after_commit() -> None:
    from app.core.admin_jobs import ADVISORY_LOCK_KEY
    from app.services.admin import jobs

    SessionLocal = _session()
    with SessionLocal() as db:
        got = db.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": ADVISORY_LOCK_KEY},
        ).scalar()
        assert got is True
        db.add(
            _run_model()(
                id=uuid.uuid4(),
                job_id="admin.retention_cleanup",
                trigger="manual",
                state="QUEUED",
                queued_at=datetime.now(BEIJING),
                counts={},
            )
        )
        db.commit()

    # API 返回后调度进程可立刻获锁。
    with jobs.advisory_connection() as connection:
        assert connection is not None


def test_tick_executes_scheduled_run_and_finishes() -> None:
    from app.services.admin import jobs

    SessionLocal = _session()
    now = datetime(2026, 11, 17, 4, 0, tzinfo=BEIJING)
    with SessionLocal() as db:
        definition = _definition(db)
        definition.last_scheduled_slot = date(2026, 11, 16)
        db.commit()

    result = jobs.tick(now=now)
    assert result["acquired"] is True
    assert result["executed"] is not None

    with SessionLocal() as db:
        run = db.get(_run_model(), uuid.UUID(result["executed"]))
        assert run is not None
        assert run.state in {"SUCCEEDED", "PARTIAL"}
        assert run.attempt_count == 1
        assert _definition(db).active_run_id is None
        events = db.execute(
            text(
                "SELECT event_type, summary FROM admin_audit_events"
                " WHERE target_type='job' ORDER BY occurred_at"
            )
        ).all()
        types = [row.event_type for row in events]
        assert "JOB_TRIGGERED" in types
        assert "JOB_FINISHED" in types


def test_heartbeat_row_written_and_updated() -> None:
    from app.admin_scheduler import write_heartbeat
    from app.db.models_admin import AdminJobSchedulerState

    SessionLocal = _session()
    instance = uuid.uuid4()
    booted = datetime.now(BEIJING)
    with SessionLocal() as db:
        db.execute(delete(AdminJobSchedulerState))
        db.commit()

    write_heartbeat(instance, booted, state="idle")
    with SessionLocal() as db:
        row = db.get(AdminJobSchedulerState, instance)
        assert row is not None and row.state == "idle"
        first = row.heartbeat_at

    write_heartbeat(instance, booted, state="running")
    with SessionLocal() as db:
        row = db.get(AdminJobSchedulerState, instance)
        assert row.state == "running"
        assert row.heartbeat_at >= first
