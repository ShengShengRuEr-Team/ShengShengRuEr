"""T07c：留存任务控制 API（主文档 §10.1 / AC-27）。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from tests.admin_support import (
    audit_event,
    request_id_of,
    session_of_token,
    session_local,
)
from tests.conftest import auth_headers

JOBS_URL = "/api/v1/admin/monitor/jobs"
JOB_ID = "admin.retention_cleanup"


def _session_local():
    return session_local()


@pytest.fixture(autouse=True)
def reset_jobs():
    from app.db.models_admin import (
        AdminJobDefinition,
        AdminJobRun,
        AdminJobSchedulerState,
    )

    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(delete(AdminJobRun))
        db.execute(delete(AdminJobSchedulerState))
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


def _heartbeat(*, age_seconds: int = 0) -> uuid.UUID:
    from app.db.models_admin import AdminJobSchedulerState

    SessionLocal = _session_local()
    instance = uuid.uuid4()
    now = datetime.now(UTC) - timedelta(seconds=age_seconds)
    with SessionLocal() as db:
        db.add(
            AdminJobSchedulerState(
                instance_id=instance,
                booted_at=now - timedelta(minutes=5),
                heartbeat_at=now,
                last_error_code=None,
                state="idle",
                version=1,
            )
        )
        db.commit()
    return instance


def test_jobs_auth_order(client: TestClient, student_token: str) -> None:
    assert client.get(JOBS_URL).status_code == 401
    assert (
        client.get(JOBS_URL, headers=auth_headers(student_token)).status_code
        == 403
    )
    assert (
        client.get(f"{JOBS_URL}/{JOB_ID}/runs").status_code == 401
    )
    assert (
        client.post(
            f"{JOBS_URL}/{JOB_ID}/run", json={"reason": "x"}
        ).status_code
        == 401
    )


def test_overview_health_states(client: TestClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    no_heartbeat = client.get(JOBS_URL, headers=headers)
    assert no_heartbeat.status_code == 200, no_heartbeat.text
    data = no_heartbeat.json()["data"]
    assert data["scheduler_health"] == "not_configured"
    assert data["job"]["job_id"] == JOB_ID
    assert data["job"]["enabled"] is True
    assert data["job"]["timezone"] == "Asia/Shanghai"
    assert data["instances"] == []

    _heartbeat(age_seconds=0)
    ok = client.get(JOBS_URL, headers=headers).json()["data"]
    assert ok["scheduler_health"] == "ok"
    assert len(ok["instances"]) == 1

    from app.db.models_admin import AdminJobSchedulerState

    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(delete(AdminJobSchedulerState))
        db.commit()
    _heartbeat(age_seconds=120)
    stale = client.get(JOBS_URL, headers=headers).json()["data"]
    assert stale["scheduler_health"] == "stale"


def test_runs_listing_and_unknown_job(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    page = client.get(f"{JOBS_URL}/{JOB_ID}/runs", headers=headers)
    assert page.status_code == 200
    data = page.json()["data"]
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["total"] == 0

    assert (
        client.get(f"{JOBS_URL}/other.job/runs", headers=headers).status_code
        == 404
    )
    assert (
        client.get(
            f"{JOBS_URL}/{JOB_ID}/runs?page_size=15", headers=headers
        ).status_code
        == 422
    )


def test_pause_and_resume_events_and_idempotency(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    url = f"{JOBS_URL}/{JOB_ID}/enabled"

    paused = client.post(
        url, json={"enabled": False, "reason": "维护"}, headers=headers
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["data"] == {
        "job_id": JOB_ID,
        "enabled": False,
        "changed": True,
    }
    event = audit_event(request_id_of(paused))
    assert event is not None and event.event_type == "JOB_PAUSED"
    assert event.summary == {"enabled": False}

    again = client.post(
        url, json={"enabled": False, "reason": "重复"}, headers=headers
    )
    assert again.status_code == 200
    assert again.json()["data"]["changed"] is False
    assert audit_event(request_id_of(again)) is None

    resumed = client.post(
        url, json={"enabled": True, "reason": "恢复"}, headers=headers
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["changed"] is True
    event = audit_event(request_id_of(resumed))
    assert event is not None and event.event_type == "JOB_RESUMED"

    overview = client.get(JOBS_URL, headers=headers).json()["data"]["job"]
    assert overview["enabled"] is True
    assert overview["next_scheduled_at"] is not None


def test_trigger_requires_heartbeat(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    response = client.post(
        f"{JOBS_URL}/{JOB_ID}/run", json={"reason": "立即"}, headers=headers
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 400

    _heartbeat(age_seconds=120)
    stale = client.post(
        f"{JOBS_URL}/{JOB_ID}/run", json={"reason": "立即"}, headers=headers
    )
    assert stale.status_code == 400


def test_trigger_queues_run_and_rejects_duplicate(
    client: TestClient, admin_token: str
) -> None:
    _heartbeat(age_seconds=0)
    headers = auth_headers(admin_token)
    response = client.post(
        f"{JOBS_URL}/{JOB_ID}/run", json={"reason": "立即"}, headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "QUEUED"
    run_id = uuid.UUID(data["run_id"])

    from app.db.models_admin import AdminJobDefinition, AdminJobRun

    SessionLocal = _session_local()
    with SessionLocal() as db:
        run = db.get(AdminJobRun, run_id)
        assert run is not None and run.trigger == "manual"
        assert run.state == "QUEUED"
        definition = db.get(AdminJobDefinition, JOB_ID)
        assert definition.active_run_id == run_id

    event = audit_event(request_id_of(response))
    assert event is not None and event.event_type == "JOB_TRIGGERED"
    assert event.summary == {"run_id": str(run_id)}

    duplicate = client.post(
        f"{JOBS_URL}/{JOB_ID}/run", json={"reason": "再来一次"}, headers=headers
    )
    assert duplicate.status_code == 400

    # API 提交后调度进程可立刻获锁。
    from app.services.admin import jobs as jobs_service

    with jobs_service.advisory_connection() as connection:
        assert connection is not None


def test_non_whitelist_job_ids(client: TestClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)
    assert (
        client.post(
            f"{JOBS_URL}/other.job/run", json={"reason": "x"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{JOBS_URL}/other.job/enabled",
            json={"enabled": False, "reason": "x"},
            headers=headers,
        ).status_code
        == 400
    )


def test_monitor_jobs_does_not_refresh_activity(
    client: TestClient, admin_token: str
) -> None:
    from app.db.models_admin import AuthSession

    SessionLocal = _session_local()
    session_id = session_of_token(admin_token)
    old = datetime.now(UTC) - timedelta(minutes=10)
    with SessionLocal() as db:
        db.execute(
            text("UPDATE auth_sessions SET last_activity_at=:t WHERE id=:id"),
            {"t": old, "id": session_id},
        )
        db.commit()

    assert client.get(JOBS_URL, headers=auth_headers(admin_token)).status_code == 200

    with SessionLocal() as db:
        current = db.scalar(
            text("SELECT last_activity_at FROM auth_sessions WHERE id=:id"),
            {"id": session_id},
        )
    assert current == old
