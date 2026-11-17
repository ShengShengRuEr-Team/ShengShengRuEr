"""本人资料与改密接口（AC-05/06，主文档 §4.3）。"""

import pytest
from fastapi.testclient import TestClient

from tests.admin_support import (
    audit_event,
    cleanup_users,
    create_user,
    login_token,
    request_id_of,
)
from tests.conftest import auth_headers

ME_FIELDS = {"id", "username", "nickname", "role", "status", "created_at", "updated_at"}


def test_get_me_and_permissions(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    response = client.get("/api/v1/admin/me", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data) == ME_FIELDS
    assert data["username"] == "admin"
    assert data["role"] == "admin"

    assert client.get("/api/v1/admin/me").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/me", headers=auth_headers(student_token)
        ).status_code
        == 403
    )


def test_patch_me_nickname_only(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    original = client.get("/api/v1/admin/me", headers=headers).json()["data"]

    try:
        updated = client.patch(
            "/api/v1/admin/me", json={"nickname": "T03 管理员"}, headers=headers
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["nickname"] == "T03 管理员"

        info = client.get("/api/v1/getInfo", headers=headers).json()["data"]
        assert info["user"]["nickname"] == "T03 管理员"

        same = client.patch(
            "/api/v1/admin/me", json={"nickname": "T03 管理员"}, headers=headers
        )
        assert same.status_code == 200
        event = audit_event(request_id_of(same))
        assert event is not None
        assert event.event_type == "PROFILE_UPDATED"
        assert event.summary["changed_fields"] == []

        extra = client.patch(
            "/api/v1/admin/me",
            json={"nickname": "x", "is_admin": True},
            headers=headers,
        )
        assert extra.status_code == 422

        too_long = client.patch(
            "/api/v1/admin/me", json={"nickname": "a" * 51}, headers=headers
        )
        assert too_long.status_code == 422
    finally:
        client.patch(
            "/api/v1/admin/me",
            json={"nickname": original["nickname"]},
            headers=headers,
        )


@pytest.fixture
def temp_admin(client: TestClient, admin_token: str):
    data, payload = create_user(client, admin_token, role="admin")
    try:
        yield data, payload
    finally:
        cleanup_users([data["id"]])


def test_change_own_password_revokes_all_sessions(
    client: TestClient, temp_admin
) -> None:
    data, payload = temp_admin
    first = login_token(client, payload["username"], payload["password"])
    second = login_token(client, payload["username"], payload["password"])
    new_password = "T03-self-password-789"

    wrong = client.post(
        "/api/v1/admin/me/password",
        json={"old_password": "wrong-password", "new_password": new_password},
        headers=auth_headers(first),
    )
    assert wrong.status_code == 400, wrong.text
    failure = audit_event(request_id_of(wrong))
    assert failure is not None
    assert failure.result == "FAILURE"
    assert failure.reason_code == "old_password_mismatch"

    weak = client.post(
        "/api/v1/admin/me/password",
        json={"old_password": payload["password"], "new_password": "short"},
        headers=auth_headers(first),
    )
    assert weak.status_code == 422

    same = client.post(
        "/api/v1/admin/me/password",
        json={
            "old_password": payload["password"],
            "new_password": payload["password"],
        },
        headers=auth_headers(first),
    )
    assert same.status_code == 400
    assert audit_event(request_id_of(same)).reason_code == "password_unchanged"

    changed = client.post(
        "/api/v1/admin/me/password",
        json={"old_password": payload["password"], "new_password": new_password},
        headers=auth_headers(first),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"] == {"changed": True, "reauth_required": True}

    event = audit_event(request_id_of(changed))
    assert event is not None
    assert event.event_type == "SELF_PASSWORD_CHANGED"
    assert event.result == "SUCCESS"
    assert event.summary["revoked_session_count"] >= 2
    assert payload["password"] not in str(event.summary)
    assert new_password not in str(event.summary)

    # 全部设备失效，包括发起改密的那一个。
    assert client.get("/api/v1/getInfo", headers=auth_headers(first)).status_code == 401
    assert client.get("/api/v1/getInfo", headers=auth_headers(second)).status_code == 401

    # 旧密码不再可用，新密码可登录。
    assert (
        client.post(
            "/api/v1/login",
            json={"username": payload["username"], "password": payload["password"]},
        ).status_code
        == 401
    )
    fresh = login_token(client, payload["username"], new_password)
    assert client.get("/api/v1/getInfo", headers=auth_headers(fresh)).status_code == 200


def test_student_cannot_use_self_endpoints(
    client: TestClient, student_token: str
) -> None:
    headers = auth_headers(student_token)
    assert client.get("/api/v1/admin/me", headers=headers).status_code == 403
    assert (
        client.patch(
            "/api/v1/admin/me", json={"nickname": "x"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/admin/me/password",
            json={"old_password": "x", "new_password": "T03-password-123"},
            headers=headers,
        ).status_code
        == 403
    )


def test_password_equal_to_username_rejected(
    client: TestClient, temp_admin
) -> None:
    data, payload = temp_admin
    token = login_token(client, payload["username"], payload["password"])
    response = client.post(
        "/api/v1/admin/me/password",
        json={
            "old_password": payload["password"],
            "new_password": payload["username"],
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 400, response.text
    assert audit_event(request_id_of(response)).reason_code == (
        "password_equals_username"
    )
