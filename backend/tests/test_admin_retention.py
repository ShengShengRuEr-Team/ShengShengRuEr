"""T07b：留存删除边界、计数、预算与失败语义（主文档 §5.4/§10.2）。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, text

from tests.admin_support import session_local


def _session_local():
    return session_local()


def _admin_id() -> int:
    SessionLocal = _session_local()
    with SessionLocal() as db:
        return db.execute(
            text("SELECT id FROM users WHERE username='admin'")
        ).scalar()


@pytest.fixture(autouse=True)
def reset_jobs():
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition, AdminJobRun

    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(delete(AdminJobRun))
        db.execute(
            text(
                "DELETE FROM admin_login_events WHERE user_agent LIKE 'retention-%'"
            )
        )
        db.execute(
            text(
                "DELETE FROM admin_audit_events WHERE user_agent LIKE 'retention-%'"
            )
        )
        db.execute(
            text(
                "DELETE FROM auth_sessions WHERE user_agent LIKE 'retention-%'"
            )
        )
        db.execute(
            text("DELETE FROM token_revocations WHERE jti LIKE 'retention-%'")
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


def _make_running_run():
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition, AdminJobRun

    SessionLocal = _session_local()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        run = AdminJobRun(
            id=uuid.uuid4(),
            job_id=JOB_ID,
            trigger="manual",
            state="RUNNING",
            queued_at=now,
            started_at=now,
            heartbeat_at=now,
            attempt_count=1,
            counts={},
            counts_complete=True,
        )
        db.add(run)
        definition = db.get(AdminJobDefinition, JOB_ID)
        definition.active_run_id = run.id
        db.commit()
        return run.id


def test_retention_boundaries_and_counts() -> None:
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminAuditEvent, AdminJobDefinition, AdminJobRun
    from app.db.models_admin import (
        AdminLoginEvent,
        AdminJobRun as RunModel,
    )
    from app.services.admin import retention

    SessionLocal = _session_local()
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    run_id = _make_running_run()
    admin_id = _admin_id()
    login_ids: list[uuid.UUID] = []
    audit_ids: list[uuid.UUID] = []
    session_ids: list[uuid.UUID] = []
    revocation_ids: list[int] = []
    run_ids: list[uuid.UUID] = []

    def login(occurred, name):
        event_id = uuid.uuid4()
        login_ids.append(event_id)
        return AdminLoginEvent(
            event_id=event_id,
            request_id=uuid.uuid4(),
            event_type="LOGIN_FAILED",
            actor_name="",
            result="FAILURE",
            reason_code="BAD_PASSWORD",
            summary={},
            user_agent="retention-test",
            duration_ms=1,
            occurred_at=occurred,
            username_attempted=name,
        )

    def audit(occurred, run_ref=None):
        event_id = uuid.uuid4()
        audit_ids.append(event_id)
        return AdminAuditEvent(
            event_id=event_id,
            request_id=uuid.uuid4(),
            event_type="USER_CREATED",
            actor_name="admin",
            result="SUCCESS",
            summary={},
            user_agent="retention-test",
            duration_ms=1,
            occurred_at=occurred,
            run_id=run_ref,
        )

    old = now - timedelta(days=91)
    with SessionLocal() as db:
        db.add_all(
            [
                login(now - timedelta(days=91), "old"),
                login(now - timedelta(days=90), "boundary"),
                login(now - timedelta(days=1), "recent"),
                audit(now - timedelta(days=181)),
                audit(now - timedelta(days=180)),
                audit(now - timedelta(days=365), run_ref=run_id),
            ]
        )
        from app.db.models_admin import AuthSession

        def make_session(expires, revoked):
            sid = uuid.uuid4()
            session_ids.append(sid)
            return AuthSession(
                id=sid,
                user_id=admin_id,
                jti_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                auth_version=0,
                issued_at=now - timedelta(days=30),
                expires_at=expires,
                last_activity_at=now - timedelta(days=30),
                revoked_at=revoked,
                revoke_reason="kicked" if revoked else None,
                ip=None,
                user_agent="retention-test",
            )

        db.add_all(
            [
                make_session(now - timedelta(days=8), None),  # 删除
                make_session(now - timedelta(days=7), None),  # 等于边界保留
                make_session(now + timedelta(days=1), None),  # 未到期保留
                make_session(now + timedelta(days=30), now - timedelta(days=8)),
                make_session(now - timedelta(days=8), now - timedelta(days=9)),
            ]
        )
        from app.db.models import TokenRevocation

        for index, expires in enumerate(
            [now - timedelta(seconds=1), now, now + timedelta(days=1)]
        ):
            revocation_ids.append(index)
            db.add(
                TokenRevocation(
                    jti=f"retention-{uuid.uuid4().hex}",
                    user_id=admin_id,
                    expires_at=expires,
                )
            )

        def job_run(state, created_at, retry_pending=False):
            rid = uuid.uuid4()
            run_ids.append(rid)
            return AdminJobRun(
                id=rid,
                job_id=JOB_ID,
                trigger="manual",
                state=state,
                queued_at=created_at,
                attempt_count=2,
                counts={},
                counts_complete=True,
                retry_pending=retry_pending,
                created_at=created_at,
            )

        db.add_all(
            [
                job_run("SUCCEEDED", now - timedelta(days=181)),
                job_run("SUCCEEDED", now - timedelta(days=180)),
                job_run("FAILED", now - timedelta(days=181), retry_pending=True),
            ]
        )
        db.commit()

        db.add(AdminLoginEvent(user_agent="retention-marker"))
        db.rollback()  # 撤销占位事件，仅保留上面已提交数据

    with SessionLocal() as db:
        run = db.get(RunModel, run_id)
        definition = db.get(AdminJobDefinition, JOB_ID)
        result = retention.run_retention(
            db,
            run,
            active_run_id=definition.active_run_id,
            now=now,
        )
        assert result.partial is False
        assert result.counts_complete is True
        assert result.counts["admin_login_events"] == 1
        assert result.counts["admin_audit_events"] == 1
        assert result.counts["auth_sessions"] == 2
        assert result.counts["token_revocations"] >= 1
        assert result.counts["admin_job_runs"] == 1

        # 相等边界与未到期记录保留。
        remaining_logins = set(
            db.execute(
                text(
                    "SELECT username_attempted FROM admin_login_events"
                    " WHERE user_agent='retention-test'"
                )
            ).scalars()
        )
        assert remaining_logins == {"boundary", "recent"}
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM admin_audit_events"
                    " WHERE user_agent='retention-test'"
                )
            )
            == 2
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM token_revocations"
                    " WHERE jti LIKE 'retention-%'"
                )
            )
            == 2
        )


def test_retention_does_not_touch_module3_attempts_or_users() -> None:
    from app.db.models_admin import AdminJobDefinition
    from app.db.models_admin import AdminJobRun as RunModel
    from app.services.admin import retention

    SessionLocal = _session_local()
    run_id = _make_running_run()
    tables = (
        "exam_papers",
        "attempts",
        "attempt_answers",
        "users",
        "roles",
        "audio_files",
    )
    with SessionLocal() as db:
        before = {
            table: db.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in tables
        }
        run = db.get(RunModel, run_id)
        definition = db.get(AdminJobDefinition, "admin.retention_cleanup")
        retention.run_retention(
            db, run, active_run_id=definition.active_run_id
        )
        after = {
            table: db.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in tables
        }
    assert before == after


def test_row_budget_returns_partial(monkeypatch) -> None:
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition, AdminJobRun
    from app.db.models_admin import AdminLoginEvent
    from app.services.admin import retention

    SessionLocal = _session_local()
    run_id = _make_running_run()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                AdminLoginEvent(
                    event_id=uuid.uuid4(),
                    request_id=uuid.uuid4(),
                    event_type="LOGIN_FAILED",
                    actor_name="",
                    result="FAILURE",
                    reason_code="BAD_PASSWORD",
                    summary={},
                    user_agent="retention-budget",
                    duration_ms=1,
                    occurred_at=now - timedelta(days=120),
                    username_attempted=f"budget-{index}",
                )
                for index in range(1500)
            ]
        )
        db.commit()

        monkeypatch.setattr(retention, "MAX_ROWS_PER_ATTEMPT", 1)
        run = db.get(AdminJobRun, run_id)
        definition = db.get(AdminJobDefinition, JOB_ID)
        result = retention.run_retention(
            db, run, active_run_id=definition.active_run_id, now=now
        )

    assert result.partial is True
    assert result.counts["admin_login_events"] == 1000
    with SessionLocal() as db:
        remaining = db.scalar(
            text(
                "SELECT count(*) FROM admin_login_events"
                " WHERE user_agent='retention-budget'"
            )
        )
    assert remaining == 500


def test_deadline_returns_partial(monkeypatch) -> None:
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition, AdminJobRun, AdminLoginEvent
    from app.services.admin import retention

    SessionLocal = _session_local()
    run_id = _make_running_run()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add_all(
            [
                AdminLoginEvent(
                    event_id=uuid.uuid4(),
                    request_id=uuid.uuid4(),
                    event_type="LOGIN_FAILED",
                    actor_name="",
                    result="FAILURE",
                    reason_code="BAD_PASSWORD",
                    summary={},
                    user_agent="retention-deadline",
                    duration_ms=1,
                    occurred_at=now - timedelta(days=120),
                    username_attempted=f"deadline-{index}",
                )
                for index in range(1500)
            ]
        )
        db.commit()
        before = db.scalar(
            text(
                "SELECT count(*) FROM admin_login_events"
                " WHERE user_agent='retention-deadline'"
            )
        )

        ticks = iter([0.0, 0.0, 1000.0])
        monkeypatch.setattr(retention, "_monotonic", lambda: next(ticks, 1000.0))
        run = db.get(AdminJobRun, run_id)
        definition = db.get(AdminJobDefinition, JOB_ID)
        result = retention.run_retention(
            db, run, active_run_id=definition.active_run_id, now=now
        )

    assert result.partial is True
    assert result.counts["admin_login_events"] == 1000
    with SessionLocal() as db:
        remaining = db.scalar(
            text(
                "SELECT count(*) FROM admin_login_events"
                " WHERE user_agent='retention-deadline'"
            )
        )
    assert before - remaining == 1000
    assert remaining >= 1  # 达到时间预算后停止，不继续删完


def test_failure_marks_counts_incomplete_and_schedules_retry(monkeypatch) -> None:
    from app.core.admin_jobs import JOB_ID
    from app.db.models_admin import AdminJobDefinition
    from app.db.models_admin import AdminJobRun as RunModel
    from app.repositories.admin import retention as retention_repo
    from app.services.admin import jobs

    SessionLocal = _session_local()
    run_id = _make_running_run()
    calls = {"count": 0}

    def _delete(db, table, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return 5
        raise RuntimeError("db down")

    monkeypatch.setattr(retention_repo, "delete_batch", _delete)

    with SessionLocal() as db:
        run = db.get(RunModel, run_id)
        with pytest.raises(RuntimeError):
            jobs.execute_claimed(db, run)
        db.expire_all()
        run = db.get(RunModel, run_id)
        assert run.state == "FAILED"
        assert run.counts_complete is False
        assert run.retry_pending is True
        assert run.attempt_count == 1
        definition = db.get(AdminJobDefinition, JOB_ID)
        assert definition.active_run_id == run.id
