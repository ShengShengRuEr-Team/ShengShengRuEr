"""用户管理接口（AC-01/02/03/04，主文档 §4.3/§6.2）。"""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.admin_support import (
    DEFAULT_PASSWORD,
    audit_event,
    cleanup_users,
    create_user,
    login_token,
    request_id_of,
    session_local,
    set_user,
    unique,
    user_row,
)
from tests.conftest import auth_headers

USER_FIELDS = {
    "id",
    "username",
    "nickname",
    "role",
    "status",
    "created_at",
    "updated_at",
}


@pytest.fixture
def temp_users(client: TestClient, admin_token: str):
    created: list[int] = []

    def _make(role: str = "student", **kwargs):
        data, payload = create_user(client, admin_token, role=role, **kwargs)
        created.append(data["id"])
        token = login_token(client, payload["username"], payload["password"])
        return data, payload, token

    yield _make

    cleanup_users(created)


def test_list_users_shape_and_auth_order(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    response = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    data = body["data"]
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["page"] == 1 and data["page_size"] == 20
    assert data["total"] >= 2
    assert set(data["items"][0]) == USER_FIELDS
    for item in data["items"]:
        assert item["role"] in {"admin", "student"}
        assert item["status"] in {"active", "disabled"}

    assert client.get("/api/v1/admin/users").status_code == 401
    denied = client.get(
        "/api/v1/admin/users", headers=auth_headers(student_token)
    )
    assert denied.status_code == 403

    # 认证先于参数校验：无 token + 畸形分页必须 401。
    assert client.get("/api/v1/admin/users?page=0").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/users?page=0", headers=auth_headers(student_token)
        ).status_code
        == 403
    )


def test_list_filters_and_validation(
    client: TestClient, admin_token: str, temp_users
) -> None:
    data, payload, _ = temp_users(nickname="筛选目标甲")
    headers = auth_headers(admin_token)

    by_username = client.get(
        f"/api/v1/admin/users?username={payload['username']}", headers=headers
    )
    assert by_username.status_code == 200
    assert by_username.json()["data"]["total"] == 1
    assert by_username.json()["data"]["items"][0]["id"] == data["id"]

    by_nickname = client.get(
        "/api/v1/admin/users?nickname=筛选目标甲", headers=headers
    )
    assert by_nickname.status_code == 200
    assert by_nickname.json()["data"]["total"] >= 1

    students = client.get("/api/v1/admin/users?role=student", headers=headers)
    assert all(
        item["role"] == "student" for item in students.json()["data"]["items"]
    )

    # 通配符按普通字符处理，不给用户通配查询。
    wildcard = client.get("/api/v1/admin/users?username=%25", headers=headers)
    assert wildcard.status_code == 200
    assert wildcard.json()["data"]["total"] == 0

    assert (
        client.get("/api/v1/admin/users?page=0", headers=headers).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/users?page_size=15", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/users?role=teacher", headers=headers
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/admin/users?username=" + "a" * 51, headers=headers
        ).status_code
        == 422
    )


def test_get_user_detail_and_errors(
    client: TestClient, admin_token: str, student_token: str, temp_users
) -> None:
    data, _, _ = temp_users()
    headers = auth_headers(admin_token)

    detail = client.get(f"/api/v1/admin/users/{data['id']}", headers=headers)
    assert detail.status_code == 200
    assert set(detail.json()["data"]) == USER_FIELDS

    assert (
        client.get("/api/v1/admin/users/999999999", headers=headers).status_code
        == 404
    )

    # 顺序：无 token 401 → 学生 403 → 管理员畸形参数 422。
    assert client.get("/api/v1/admin/users/abc").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/users/abc", headers=auth_headers(student_token)
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/users/abc", headers=headers).status_code
        == 422
    )
    assert (
        client.get("/api/v1/admin/users/0", headers=headers).status_code == 422
    )


def test_create_user_validation_and_duplicate(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    username = unique("t03")
    created, _ = create_user(client, admin_token, username=username)
    try:
        assert created["role"] == "student"
        assert created["status"] == "active"
        assert created["username"] == username

        duplicate = client.post(
            "/api/v1/admin/users",
            json={
                "username": username,
                "password": DEFAULT_PASSWORD,
            },
            headers=headers,
        )
        assert duplicate.status_code == 400, duplicate.text
        assert duplicate.json()["code"] == 400

        invalid_username = client.post(
            "/api/v1/admin/users",
            json={"username": "ab", "password": DEFAULT_PASSWORD},
            headers=headers,
        )
        assert invalid_username.status_code == 422

        weak_password = client.post(
            "/api/v1/admin/users",
            json={"username": unique("t03"), "password": "short1"},
            headers=headers,
        )
        assert weak_password.status_code == 422

        extra = client.post(
            "/api/v1/admin/users",
            json={
                "username": unique("t03"),
                "password": DEFAULT_PASSWORD,
                "is_admin": True,
            },
            headers=headers,
        )
        assert extra.status_code == 422

        bad_role = client.post(
            "/api/v1/admin/users",
            json={
                "username": unique("t03"),
                "password": DEFAULT_PASSWORD,
                "role": "teacher",
            },
            headers=headers,
        )
        assert bad_role.status_code == 422

        # 创建失败审计：重复用户名记 FAILURE。
        failure = audit_event(request_id_of(duplicate))
        assert failure is not None
        assert failure.result == "FAILURE"
        assert failure.reason_code == "username_taken"
    finally:
        cleanup_users([created["id"]])


def test_concurrent_duplicate_username_only_one_row(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    username = unique("t03race")
    payload = {"username": username, "password": DEFAULT_PASSWORD}
    results: list[int] = []
    lock = threading.Lock()

    def attempt() -> None:
        response = client.post(
            "/api/v1/admin/users", json=payload, headers=headers
        )
        with lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    SessionLocal = session_local()
    with SessionLocal() as db:
        rows = db.execute(
            text("SELECT id FROM users WHERE username = :u"), {"u": username}
        ).scalars().all()
        for user_id in rows:
            db.execute(
                text("DELETE FROM user_roles WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(
                text("DELETE FROM users WHERE id = :u"), {"u": user_id}
            )
        db.commit()

    assert sorted(results) == [200, 400], results
    assert len(rows) == 1


def test_patch_nickname_and_no_change_audit(
    client: TestClient, admin_token: str, temp_users
) -> None:
    data, _, _ = temp_users()
    headers = auth_headers(admin_token)
    url = f"/api/v1/admin/users/{data['id']}"

    updated = client.patch(url, json={"nickname": "新昵称"}, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["nickname"] == "新昵称"

    same = client.patch(url, json={"nickname": "新昵称"}, headers=headers)
    assert same.status_code == 200
    event = audit_event(request_id_of(same))
    assert event is not None
    assert event.event_type == "PROFILE_UPDATED"
    assert event.result == "SUCCESS"
    assert event.summary["changed_fields"] == []

    extra = client.patch(
        url, json={"nickname": "x", "status": "disabled"}, headers=headers
    )
    assert extra.status_code == 422

    assert (
        client.patch(
            "/api/v1/admin/users/999999999",
            json={"nickname": "x"},
            headers=headers,
        ).status_code
        == 404
    )


def test_disable_revokes_sessions_and_version(
    client: TestClient, admin_token: str, temp_users
) -> None:
    data, payload, token = temp_users()
    headers = auth_headers(admin_token)
    url = f"/api/v1/admin/users/{data['id']}/status"

    disabled = client.post(
        url, json={"status": "disabled", "reason": "违规"}, headers=headers
    )
    assert disabled.status_code == 200, disabled.text
    result = disabled.json()["data"]
    assert result["status"] == "disabled"
    assert result["changed"] is True
    assert result["revoked_session_count"] >= 1

    # 旧 token 与重新登录都被拒。
    assert client.get("/api/v1/getInfo", headers=auth_headers(token)).status_code == 401
    assert (
        client.post(
            "/api/v1/login",
            json={"username": payload["username"], "password": payload["password"]},
        ).status_code
        == 401
    )

    version_after_disable = user_row(data["id"]).auth_version
    assert version_after_disable == 1

    # 重复停用：changed=false，不增版本。
    again = client.post(
        url, json={"status": "disabled", "reason": "重复"}, headers=headers
    )
    assert again.status_code == 200
    assert again.json()["data"]["changed"] is False
    assert user_row(data["id"]).auth_version == version_after_disable

    # 启用：不恢复旧版本，旧 token 仍 401。
    enabled = client.post(
        url, json={"status": "active", "reason": "恢复"}, headers=headers
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["changed"] is True
    assert user_row(data["id"]).auth_version == version_after_disable
    assert client.get("/api/v1/getInfo", headers=auth_headers(token)).status_code == 401

    # 新登录可用（版本已固定为新值）。
    fresh = login_token(client, payload["username"], payload["password"])
    assert client.get("/api/v1/getInfo", headers=auth_headers(fresh)).status_code == 200


def test_disable_self_returns_400(
    client: TestClient, admin_token: str
) -> None:
    me = client.get("/api/v1/admin/me", headers=auth_headers(admin_token))
    my_id = me.json()["data"]["id"]
    response = client.post(
        f"/api/v1/admin/users/{my_id}/status",
        json={"status": "disabled", "reason": "自停"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 400, response.text
    event = audit_event(request_id_of(response))
    assert event is not None and event.reason_code == "self_forbidden"


def test_last_active_admin_guard_at_service_level() -> None:
    """最后管理员保护是防御性分支：直接调用服务层验证锁内 count。"""

    from app.api.deps import CurrentUser
    from app.core.errors import AppError
    from app.db.models import Role, User, UserRole
    from app.services.admin import accounts

    SessionLocal = session_local()
    with SessionLocal() as db:
        admin_row = db.execute(
            text("SELECT id, username, auth_version FROM users WHERE username='admin'")
        ).first()
        student_row = db.execute(
            text(
                "SELECT u.id, u.username, u.auth_version FROM users u "
                "JOIN user_roles ur ON ur.user_id = u.id "
                "JOIN roles r ON r.id = ur.role_id WHERE r.role_key='student' "
                "LIMIT 1"
            )
        ).first()
        assert admin_row is not None and student_row is not None
        # 仅保留 admin 一个 active 管理员，确保 target 是最后一个。
        actor = CurrentUser(
            id=student_row.id,
            username=student_row.username,
            nickname="",
            roles=("student",),
            jti="t03",
            expires_at=datetime_now(),
            auth_version=student_row.auth_version,
            session_id=uuid.uuid4(),
        )
        try:
            accounts.change_status(
                db,
                actor=actor,
                request_id=uuid.uuid4(),
                ip=None,
                user_agent="pytest",
                started_at=0.0,
                target_id=admin_row.id,
                status="disabled",
                reason="guard",
            )
        except AppError as exc:
            assert exc.status_code == 400
            assert "最后一个有效管理员" in exc.msg
        else:  # pragma: no cover
            raise AssertionError("最后管理员保护未生效")
        finally:
            db.rollback()
            # 防御性恢复：若保护失效导致 admin 被停用，恢复状态避免污染后续用例。
            set_user(admin_row.id, status="active")


def datetime_now():
    from app.core.security import utc_now

    return utc_now()


def test_reset_password_flow(
    client: TestClient, admin_token: str, temp_users
) -> None:
    data, payload, token = temp_users()
    headers = auth_headers(admin_token)
    url = f"/api/v1/admin/users/{data['id']}/reset-password"
    new_password = "T03-new-password-456"

    me = client.get("/api/v1/admin/me", headers=headers).json()["data"]

    self_reset = client.post(
        f"/api/v1/admin/users/{me['id']}/reset-password",
        json={"new_password": new_password, "reason": "本人"},
        headers=headers,
    )
    assert self_reset.status_code == 400

    same = client.post(
        url,
        json={
            "new_password": payload["password"],
            "reason": "同值",
        },
        headers=headers,
    )
    assert same.status_code == 400

    weak = client.post(
        url, json={"new_password": "short", "reason": "弱密码"}, headers=headers
    )
    assert weak.status_code == 422

    reset = client.post(
        url, json={"new_password": new_password, "reason": "遗忘"}, headers=headers
    )
    assert reset.status_code == 200, reset.text
    result = reset.json()["data"]
    assert result["changed"] is True
    assert result["revoked_session_count"] >= 1

    assert client.get("/api/v1/getInfo", headers=auth_headers(token)).status_code == 401
    assert (
        client.post(
            "/api/v1/login",
            json={"username": payload["username"], "password": payload["password"]},
        ).status_code
        == 401
    )
    fresh = login_token(client, payload["username"], new_password)
    assert client.get("/api/v1/getInfo", headers=auth_headers(fresh)).status_code == 200

    # 重置 disabled 用户仍为 disabled。
    set_user(data["id"], status="disabled")
    disabled_reset = client.post(
        url,
        json={"new_password": "T03-another-pass-789", "reason": "停用重置"},
        headers=headers,
    )
    assert disabled_reset.status_code == 200
    assert user_row(data["id"]).status == "disabled"
