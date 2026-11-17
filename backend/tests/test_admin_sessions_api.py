"""在线会话列表与单会话强退（AC-07/08，主文档 §6.3）。"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.admin_support import (
    audit_event,
    cleanup_users,
    create_user,
    get_session,
    login_token,
    request_id_of,
    seconds_ago,
    session_of_token,
    set_session,
)
from tests.conftest import auth_headers

SESSION_FIELDS = {
    "session_id",
    "user_id",
    "username",
    "role",
    "ip",
    "user_agent_summary",
    "issued_at",
    "last_activity_at",
    "expires_at",
    "is_current",
}


@pytest.fixture
def online_user(client: TestClient, admin_token: str):
    data, payload = create_user(client, admin_token)
    first = login_token(client, payload["username"], payload["password"])
    second = login_token(client, payload["username"], payload["password"])
    try:
        yield data, payload, first, second
    finally:
        cleanup_users([data["id"]])


def _find(items: list[dict], session_id: uuid.UUID) -> dict | None:
    return next(
        (item for item in items if item["session_id"] == str(session_id)), None
    )


def test_sessions_shape_and_no_secrets(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/monitor/sessions", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    assert set(data) == {
        "items",
        "total",
        "page",
        "page_size",
        "as_of",
        "active_account_count",
        "active_session_count",
    }
    assert data["active_session_count"] == len(data["items"]) or data["total"] >= len(
        data["items"]
    )
    assert data["active_account_count"] <= data["active_session_count"]

    own = session_of_token(admin_token)
    mine = _find(data["items"], own)
    assert mine is not None
    assert mine["is_current"] is True
    assert set(mine) == SESSION_FIELDS
    uuid.UUID(mine["session_id"])

    text = response.text.lower()
    assert "jti" not in text
    assert "token" not in text
    assert "authorization" not in text


def test_sessions_auth_order(
    client: TestClient, student_token: str
) -> None:
    assert client.get("/api/v1/admin/monitor/sessions").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/monitor/sessions", headers=auth_headers(student_token)
        ).status_code
        == 403
    )
    # 认证先于参数校验。
    assert client.get("/api/v1/admin/monitor/sessions?page=0").status_code == 401


def test_sessions_filters_and_pagination(
    client: TestClient, admin_token: str, online_user
) -> None:
    data, payload, _, _ = online_user
    headers = auth_headers(admin_token)

    by_name = client.get(
        f"/api/v1/admin/monitor/sessions?username={payload['username']}",
        headers=headers,
    )
    assert by_name.status_code == 200
    assert by_name.json()["data"]["total"] >= 2
    assert by_name.json()["data"]["active_account_count"] == 1

    students = client.get(
        "/api/v1/admin/monitor/sessions?role=student", headers=headers
    )
    assert students.status_code == 200
    assert all(
        item["role"] == "student" for item in students.json()["data"]["items"]
    )

    assert (
        client.get(
            "/api/v1/admin/monitor/sessions?page_size=15", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/monitor/sessions?role=teacher", headers=headers
        ).status_code
        == 422
    )


def test_online_window_is_strict_five_minutes(
    client: TestClient, admin_token: str, online_user
) -> None:
    data, payload, first, _ = online_user
    headers = auth_headers(admin_token)
    session_id = session_of_token(first)

    set_session(session_id, last_activity_at=seconds_ago(5 * 60 + 5))
    excluded = client.get(
        f"/api/v1/admin/monitor/sessions?username={payload['username']}",
        headers=headers,
    ).json()["data"]
    assert _find(excluded["items"], session_id) is None

    set_session(session_id, last_activity_at=seconds_ago(5 * 60 - 30))
    included = client.get(
        f"/api/v1/admin/monitor/sessions?username={payload['username']}",
        headers=headers,
    ).json()["data"]
    assert _find(included["items"], session_id) is not None


def test_revoke_other_session_only(
    client: TestClient, admin_token: str, online_user
) -> None:
    data, payload, first, second = online_user
    headers = auth_headers(admin_token)
    target = session_of_token(second)

    revoked = client.post(
        f"/api/v1/admin/monitor/sessions/{target}/revoke",
        json={"reason": "异地登录"},
        headers=headers,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"] == {"session_id": str(target), "changed": True}

    event = audit_event(request_id_of(revoked))
    assert event is not None
    assert event.event_type == "SESSION_REVOKED"
    assert event.result == "SUCCESS"
    assert event.summary["session_id"] == str(target)

    # 目标会话失效，另一会话继续可用。
    assert client.get("/api/v1/getInfo", headers=auth_headers(second)).status_code == 401
    assert client.get("/api/v1/getInfo", headers=auth_headers(first)).status_code == 200

    # 重复强退：已关闭，幂等成功。
    again = client.post(
        f"/api/v1/admin/monitor/sessions/{target}/revoke",
        json={"reason": "重复"},
        headers=headers,
    )
    assert again.status_code == 200
    assert again.json()["data"]["changed"] is False

    row = get_session(target)
    assert row is not None and row.revoke_reason == "kicked"


def test_revoke_current_session_rejected(
    client: TestClient, admin_token: str
) -> None:
    own = session_of_token(admin_token)
    response = client.post(
        f"/api/v1/admin/monitor/sessions/{own}/revoke",
        json={"reason": "误操作"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 400, response.text
    assert audit_event(request_id_of(response)).reason_code == "current_session"


def test_revoke_unknown_session_404(
    client: TestClient, admin_token: str
) -> None:
    unknown = uuid.uuid4()
    response = client.post(
        f"/api/v1/admin/monitor/sessions/{unknown}/revoke",
        json={"reason": "不存在"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404, response.text
    event = audit_event(request_id_of(response))
    assert event is not None and event.reason_code == "session_not_found"


def test_revoke_validation_and_auth_order(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    url = "/api/v1/admin/monitor/sessions/not-a-uuid/revoke"
    body = {"reason": "x"}

    assert client.post(url, json=body).status_code == 401
    assert (
        client.post(url, json=body, headers=auth_headers(student_token)).status_code
        == 403
    )
    assert (
        client.post(url, json=body, headers=auth_headers(admin_token)).status_code
        == 422
    )

    valid = uuid.uuid4()
    assert (
        client.post(
            f"/api/v1/admin/monitor/sessions/{valid}/revoke",
            json={"reason": ""},
            headers=auth_headers(admin_token),
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/admin/monitor/sessions/{valid}/revoke",
            json={"reason": "x", "extra": 1},
            headers=auth_headers(admin_token),
        ).status_code
        == 422
    )
