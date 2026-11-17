"""审计日志接口（AC-12/AC-28 的日志部分，主文档 §7.3）。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.admin_support import request_id_of, session_local
from tests.conftest import auth_headers

LOGIN_FIELDS = {
    "event_id",
    "request_id",
    "occurred_at",
    "event_type",
    "username_attempted",
    "actor_user_id",
    "actor_name",
    "role_snapshot",
    "result",
    "reason_code",
    "ip",
    "user_agent_summary",
    "duration_ms",
}

OPERATION_FIELDS = (
    LOGIN_FIELDS | {"target_type", "target_id", "summary", "run_id"}
) - {"username_attempted"}


def _insert_login_event(
    *,
    username: str,
    occurred_at: datetime | None = None,
    result: str = "FAILURE",
    reason_code: str | None = "BAD_PASSWORD",
    ip: str | None = "203.0.113.7",
    user_agent: str = "pytest-agent",
    summary: dict | None = None,
) -> uuid.UUID:
    from app.db.models_admin import AdminLoginEvent

    event_id = uuid.uuid4()
    SessionLocal = session_local()
    with SessionLocal() as db:
        db.add(
            AdminLoginEvent(
                event_id=event_id,
                request_id=uuid.uuid4(),
                event_type="LOGIN_FAILED" if result == "FAILURE" else "LOGIN_SUCCEEDED",
                actor_user_id=None,
                actor_name="" if result == "FAILURE" else username,
                role_snapshot=None,
                result=result,
                reason_code=reason_code,
                summary=summary or {},
                ip=ip,
                user_agent=user_agent,
                duration_ms=12,
                occurred_at=occurred_at or datetime.now(UTC),
                username_attempted=username,
            )
        )
        db.commit()
    return event_id


def _insert_operation_event(
    *,
    actor_name: str,
    occurred_at: datetime | None = None,
    event_type: str = "SESSION_REVOKED",
    result: str = "SUCCESS",
    target_type: str = "session",
    target_id: str = "abc",
    summary: dict | None = None,
    user_agent: str = "pytest-agent",
) -> uuid.UUID:
    from app.db.models_admin import AdminAuditEvent

    event_id = uuid.uuid4()
    SessionLocal = session_local()
    with SessionLocal() as db:
        db.add(
            AdminAuditEvent(
                event_id=event_id,
                request_id=uuid.uuid4(),
                event_type=event_type,
                actor_user_id=None,
                actor_name=actor_name,
                role_snapshot="admin",
                target_type=target_type,
                target_id=target_id,
                result=result,
                reason_code=None,
                summary=summary or {},
                ip="198.51.100.9",
                user_agent=user_agent,
                duration_ms=3,
                occurred_at=occurred_at or datetime.now(UTC),
                run_id=None,
            )
        )
        db.commit()
    return event_id


def _cleanup(event_ids: list[uuid.UUID]) -> None:
    SessionLocal = session_local()
    with SessionLocal() as db:
        for event_id in event_ids:
            db.execute(
                text("DELETE FROM admin_login_events WHERE event_id = :i"),
                {"i": event_id},
            )
            db.execute(
                text("DELETE FROM admin_audit_events WHERE event_id = :i"),
                {"i": event_id},
            )
        db.commit()


@pytest.fixture
def login_events():
    ids: list[uuid.UUID] = []

    def _make(**kwargs) -> uuid.UUID:
        event_id = _insert_login_event(**kwargs)
        ids.append(event_id)
        return event_id

    yield _make
    _cleanup(ids)


@pytest.fixture
def operation_events():
    ids: list[uuid.UUID] = []

    def _make(**kwargs) -> uuid.UUID:
        event_id = _insert_operation_event(**kwargs)
        ids.append(event_id)
        return event_id

    yield _make
    _cleanup(ids)


def test_logs_auth_order(client: TestClient, student_token: str) -> None:
    for path in (
        "/api/v1/admin/logs/login",
        "/api/v1/admin/logs/operation",
        f"/api/v1/admin/logs/login/{uuid.uuid4()}",
        f"/api/v1/admin/logs/operation/{uuid.uuid4()}",
    ):
        assert client.get(path).status_code == 401
        assert (
            client.get(path, headers=auth_headers(student_token)).status_code == 403
        )
    # 认证先于参数校验。
    assert client.get("/api/v1/admin/logs/login/abc").status_code == 401


def test_login_log_shape_filters_and_pagination(
    client: TestClient, admin_token: str, login_events
) -> None:
    token = uuid.uuid4().hex[:8]
    username = f"log_{token}"
    for _ in range(3):
        login_events(username=username)
    login_events(username=username, result="SUCCESS", reason_code=None)

    headers = auth_headers(admin_token)
    response = client.get(
        f"/api/v1/admin/logs/login?username={username}", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["total"] == 4
    assert set(data["items"][0]) == LOGIN_FIELDS
    # 倒序：最后插入的最新。
    occurred = [item["occurred_at"] for item in data["items"]]
    assert occurred == sorted(occurred, reverse=True)

    failures = client.get(
        f"/api/v1/admin/logs/login?username={username}&result=FAILURE",
        headers=headers,
    ).json()["data"]
    assert failures["total"] == 3

    by_type = client.get(
        f"/api/v1/admin/logs/login?username={username}&failure_type=BAD_PASSWORD",
        headers=headers,
    ).json()["data"]
    assert by_type["total"] == 3

    by_ip = client.get(
        "/api/v1/admin/logs/login?ip=203.0.113.7&page_size=10", headers=headers
    )
    assert by_ip.status_code == 200

    assert (
        client.get(
            "/api/v1/admin/logs/login?ip=not-an-ip", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/admin/logs/login?username={username}&page_size=15",
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/logs/login?result=MAYBE", headers=headers
        ).status_code
        == 422
    )


def test_operation_log_shape_and_summary_refilter(
    client: TestClient, admin_token: str, operation_events
) -> None:
    actor = f"actor_{uuid.uuid4().hex[:6]}"
    operation_events(
        actor_name=actor,
        event_type="SESSION_REVOKED",
        summary={
            "session_id": "abc",
            "target_user_id": 7,
            "password": "P@ss",
            "jti": "secret-jti",
        },
        user_agent="A" * 200,
    )

    response = client.get(
        f"/api/v1/admin/logs/operation?actor_username={actor}",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert set(item) == OPERATION_FIELDS
    # 读取侧白名单过滤：只保留该事件允许的 summary 键。
    assert item["summary"] == {"session_id": "abc", "target_user_id": 7}
    # UA 只给摘要。
    assert len(item["user_agent_summary"]) == 80
    text_body = response.text.lower()
    for forbidden in ("jti", "token", "password", "hash"):
        assert forbidden not in text_body

    by_type = client.get(
        "/api/v1/admin/logs/operation?event_type=SESSION_REVOKED",
        headers=auth_headers(admin_token),
    )
    assert by_type.status_code == 200
    assert (
        client.get(
            "/api/v1/admin/logs/operation?event_type=NOT_REGISTERED",
            headers=auth_headers(admin_token),
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/logs/operation?target_type=unknown",
            headers=auth_headers(admin_token),
        ).status_code
        == 422
    )


def test_default_window_and_time_rules(
    client: TestClient, admin_token: str, login_events
) -> None:
    headers = auth_headers(admin_token)
    old_name = f"old_{uuid.uuid4().hex[:6]}"
    login_events(username=old_name, occurred_at=datetime.now(UTC) - timedelta(days=10))

    default = client.get(
        f"/api/v1/admin/logs/login?username={old_name}", headers=headers
    ).json()["data"]
    assert default["total"] == 0

    start = (datetime.now(UTC) - timedelta(days=11)).isoformat()
    end = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    explicit = client.get(
        "/api/v1/admin/logs/login",
        params={"username": old_name, "start_at": start, "end_at": end},
        headers=headers,
    ).json()["data"]
    assert explicit["total"] == 1

    one_sided = client.get(
        "/api/v1/admin/logs/login", params={"start_at": start}, headers=headers
    )
    assert one_sided.status_code == 422

    reversed_range = client.get(
        "/api/v1/admin/logs/login",
        params={"start_at": end, "end_at": start},
        headers=headers,
    )
    assert reversed_range.status_code == 422

    too_long = client.get(
        "/api/v1/admin/logs/login",
        params={
            "start_at": (datetime.now(UTC) - timedelta(days=91)).isoformat(),
            "end_at": datetime.now(UTC).isoformat(),
        },
        headers=headers,
    )
    assert too_long.status_code == 422

    naive = client.get(
        "/api/v1/admin/logs/login",
        params={"start_at": "2026-11-01T00:00:00", "end_at": "2026-11-02T00:00:00"},
        headers=headers,
    )
    assert naive.status_code == 422


def test_end_exclusive_start_inclusive(
    client: TestClient, admin_token: str, login_events
) -> None:
    headers = auth_headers(admin_token)
    name = f"edge_{uuid.uuid4().hex[:6]}"
    start = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=1)
    login_events(username=name, occurred_at=start)
    login_events(username=name, occurred_at=end)

    data = client.get(
        "/api/v1/admin/logs/login",
        params={
            "username": name,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
        headers=headers,
    ).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["occurred_at"].startswith("2026-11-01T08:00:00")

    equal = client.get(
        "/api/v1/admin/logs/login",
        params={
            "username": name,
            "start_at": start.isoformat(),
            "end_at": start.isoformat(),
        },
        headers=headers,
    ).json()["data"]
    assert equal["total"] == 0


def test_log_detail_and_errors(
    client: TestClient, admin_token: str, login_events, operation_events
) -> None:
    headers = auth_headers(admin_token)
    login_id = login_events(username=f"detail_{uuid.uuid4().hex[:6]}")
    operation_id = operation_events(actor_name="detail-actor")

    login_detail = client.get(
        f"/api/v1/admin/logs/login/{login_id}", headers=headers
    )
    assert login_detail.status_code == 200
    assert login_detail.json()["data"]["event_id"] == str(login_id)

    operation_detail = client.get(
        f"/api/v1/admin/logs/operation/{operation_id}", headers=headers
    )
    assert operation_detail.status_code == 200
    assert operation_detail.json()["data"]["event_id"] == str(operation_id)

    assert (
        client.get(
            f"/api/v1/admin/logs/login/{uuid.uuid4()}", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/admin/logs/operation/{uuid.uuid4()}", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/admin/logs/login/not-a-uuid", headers=headers).status_code
        == 422
    )


def test_request_id_header_present(client: TestClient, admin_token: str) -> None:
    response = client.get(
        "/api/v1/admin/logs/login", headers=auth_headers(admin_token)
    )
    assert isinstance(request_id_of(response), uuid.UUID)
