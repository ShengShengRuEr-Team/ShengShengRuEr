"""固定权限目录契约（主文档 §4.2 / AC-28 后端部分）。

覆盖：21 个权限码逐字一致、admin 全量、student 空集、getInfo 新字段与旧字段兼容、
权限码守卫的学生 403 / 无 token 401 / 移除单码后 403。
"""

from fastapi.testclient import TestClient

from app.core import admin_permissions
from app.core.admin_permissions import (
    ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    permission_codes,
)
from app.core.permissions import ROLE_ADMIN, ROLE_STUDENT
from tests.conftest import auth_headers

# 逐字抄自主文档 §4.2，测试内再写一份，避免实现与断言同源。
EXPECTED_PERMISSIONS: tuple[str, ...] = (
    "admin:user:read",
    "admin:user:create",
    "admin:user:update",
    "admin:user:status",
    "admin:user:resetPassword",
    "admin:self:read",
    "admin:self:update",
    "admin:self:password",
    "admin:session:read",
    "admin:session:revoke",
    "admin:log:read",
    "admin:docs:read",
    "admin:docs:debug",
    "admin:monitor:read",
    "admin:job:read",
    "admin:job:control",
    "admin:cache:clear",
    "admin:dashboard:read",
    "admin:export:users",
    "admin:export:loginLogs",
    "admin:export:operationLogs",
)


def test_catalog_matches_spec_exactly() -> None:
    """21 个权限码，顺序与正式规格一致，无重复、无通配符。"""

    assert len(EXPECTED_PERMISSIONS) == 21
    assert ADMIN_PERMISSIONS == EXPECTED_PERMISSIONS
    assert len(set(ADMIN_PERMISSIONS)) == 21
    assert all("*" not in code for code in ADMIN_PERMISSIONS)
    assert all(code.split(":")[0] == "admin" for code in ADMIN_PERMISSIONS)
    assert all(len(code.split(":")) == 3 for code in ADMIN_PERMISSIONS)


def test_role_mapping_is_fixed() -> None:
    assert ROLE_PERMISSIONS[ROLE_ADMIN] == frozenset(EXPECTED_PERMISSIONS)
    assert ROLE_PERMISSIONS[ROLE_STUDENT] == frozenset()
    assert permission_codes([ROLE_ADMIN]) == EXPECTED_PERMISSIONS
    assert permission_codes([ROLE_STUDENT]) == ()
    assert permission_codes(["unknown-role"]) == ()


def test_admin_getinfo_returns_all_permissions(
    client: TestClient, admin_token: str
) -> None:
    response = client.get("/api/v1/getInfo", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    # 旧字段类型与含义不变。
    assert set(data) == {"user", "roles", "is_admin", "permissions"}
    assert data["roles"] == ["admin"]
    assert data["is_admin"] is True
    assert set(data["user"]) == {"user_id", "username", "nickname"}

    # 新增字段：admin 拥有 21 个固定权限码。
    assert data["permissions"] == list(EXPECTED_PERMISSIONS)
    assert len(data["permissions"]) == 21


def test_student_getinfo_has_empty_permissions(
    client: TestClient, student_token: str
) -> None:
    response = client.get("/api/v1/getInfo", headers=auth_headers(student_token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["is_admin"] is False
    assert data["permissions"] == []


def test_permission_route_auth_order(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    """顺序固定：无 token 401 → 学生 403 → 管理员 200。"""

    assert client.get("/api/v1/admin/overview").status_code == 401
    student = client.get(
        "/api/v1/admin/overview", headers=auth_headers(student_token)
    )
    assert student.status_code == 403
    admin = client.get(
        "/api/v1/admin/overview", headers=auth_headers(admin_token)
    )
    assert admin.status_code == 200


def test_removing_one_permission_denies_admin(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    """移除单个权限码后，即使仍是管理员也应 403（无自动放行）。"""

    patched = dict(ROLE_PERMISSIONS)
    patched[ROLE_ADMIN] = frozenset(EXPECTED_PERMISSIONS) - {
        "admin:dashboard:read"
    }
    monkeypatch.setattr(admin_permissions, "ROLE_PERMISSIONS", patched)

    assert client.get("/api/v1/admin/overview").status_code == 401
    denied = client.get(
        "/api/v1/admin/overview", headers=auth_headers(admin_token)
    )
    assert denied.status_code == 403, denied.text

    # getInfo 同步反映被移除的码，不因 is_admin 自动补齐。
    info = client.get("/api/v1/getInfo", headers=auth_headers(admin_token))
    assert "admin:dashboard:read" not in info.json()["data"]["permissions"]
    assert len(info.json()["data"]["permissions"]) == 20
