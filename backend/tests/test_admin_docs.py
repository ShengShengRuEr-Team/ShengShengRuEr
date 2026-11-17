"""私有接口文档与受限 GET 调试（AC-13/14/15 的 T06 部分，主文档 §8）。"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.admin_support import audit_event, request_id_of
from tests.conftest import auth_headers

DEBUG_HEADERS = {"X-Admin-Docs-Debug": "1"}


def _debug(token: str) -> dict[str, str]:
    return {**auth_headers(token), **DEBUG_HEADERS}


# --------------------------------------------------------------------------- #
# 公开入口关闭
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
        "/api/v1/openapi.json",
    ],
)
def test_public_docs_entries_are_404(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404, (path, response.status_code)
    assert "<!doctype html" not in response.text.lower()


def test_old_interfaces_unchanged(
    client: TestClient, admin_token: str
) -> None:
    response = client.get("/api/v1/admin/overview", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert set(response.json()["data"]) == {"role", "message"}


# --------------------------------------------------------------------------- #
# 受保护 schema
# --------------------------------------------------------------------------- #
def test_protected_schema_auth(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    assert client.get("/api/v1/admin/openapi.json").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/openapi.json", headers=auth_headers(student_token)
        ).status_code
        == 403
    )
    response = client.get(
        "/api/v1/admin/openapi.json", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")


def test_protected_schema_content_and_allowlist(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/openapi.json", headers=auth_headers(admin_token)
    )
    schema = response.json()

    # 原始 JSON：不套统一业务外壳。
    assert "code" not in schema and "data" not in schema
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/admin/users" in schema["paths"]
    assert "/api/v1/admin/dashboard" in schema["paths"]

    allowlist = schema["x-admin-debug-allowlist"]
    from app.core.admin_permissions import DOC_DEBUG_ALLOWLIST

    assert len(allowlist) == len(DOC_DEBUG_ALLOWLIST)
    assert "/api/v1/admin/monitor/database" in schema["paths"]
    for entry in allowlist:
        assert set(entry) == {"method", "path_template", "permission"}
        assert entry["method"] == "GET"
        assert entry["permission"].startswith("admin:")
        assert entry["path_template"].startswith("/api/v1/admin/")

    # 零秘密：不含配置值、连接串或演示密码。
    body = response.text
    for forbidden in (
        "JWT_SECRET_KEY",
        "DATABASE_URL",
        "postgresql+psycopg",
        "admin123",
        "student123",
    ):
        assert forbidden not in body


def test_schema_removed_permission_returns_403(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.core import admin_permissions

    full = admin_permissions.ROLE_PERMISSIONS["admin"]
    monkeypatch.setitem(
        admin_permissions.ROLE_PERMISSIONS,
        "admin",
        full - {"admin:docs:read"},
    )
    assert (
        client.get(
            "/api/v1/admin/openapi.json", headers=auth_headers(admin_token)
        ).status_code
        == 403
    )


# --------------------------------------------------------------------------- #
# 受限 GET 调试
# --------------------------------------------------------------------------- #
def test_debug_whitelisted_get_records_event(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/users?username=abc&token=SHOULD-NOT-BE-LOGGED",
        headers=_debug(admin_token),
    )
    assert response.status_code == 200, response.text

    event = audit_event(request_id_of(response))
    assert event is not None
    assert event.event_type == "DOC_GET_DEBUG"
    assert event.result == "SUCCESS"
    assert event.target_type == "docs"
    assert event.target_id == "/api/v1/admin/users"
    assert event.summary == {
        "method": "GET",
        "path_template": "/api/v1/admin/users",
        "status_code": 200,
    }
    assert event.duration_ms >= 0
    # 不记录实际 query、Authorization 或 token。
    dumped = json.dumps(event.summary, ensure_ascii=False)
    assert "SHOULD-NOT-BE-LOGGED" not in dumped
    assert "username" not in dumped


def test_debug_detail_template_and_error_status(
    client: TestClient, admin_token: str
) -> None:
    missing = 999_999_999
    response = client.get(
        f"/api/v1/admin/users/{missing}", headers=_debug(admin_token)
    )
    assert response.status_code == 404, response.text

    event = audit_event(request_id_of(response))
    assert event is not None
    assert event.result == "FAILURE"
    assert event.summary["path_template"] == "/api/v1/admin/users/{user_id}"
    assert event.summary["status_code"] == 404


def test_normal_request_without_marker_is_unchanged(
    client: TestClient, admin_token: str
) -> None:
    response = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert audit_event(request_id_of(response)) is None


def test_debug_rejects_non_whitelist_and_writes(
    client: TestClient, admin_token: str
) -> None:
    headers = _debug(admin_token)
    assert client.get("/api/v1/admin/openapi.json", headers=headers).status_code == 400
    assert client.get("/api/v1/admin/exports/users", headers=headers).status_code == 400
    assert (
        client.post("/api/v1/admin/users", headers=headers, json={}).status_code
        == 400
    )
    assert client.get("/api/v1/admin/overview", headers=headers).status_code == 400


def test_debug_auth_and_permission_order(
    client: TestClient, admin_token: str, student_token: str, monkeypatch
) -> None:
    # 无 token -> 401（认证先于其它判定）。
    assert client.get("/api/v1/admin/users", headers=DEBUG_HEADERS).status_code == 401
    # 学生 -> 403（角色）。
    assert (
        client.get(
            "/api/v1/admin/users",
            headers={**auth_headers(student_token), **DEBUG_HEADERS},
        ).status_code
        == 403
    )
    # 管理员缺 docs:debug -> 403。
    from app.core import admin_permissions

    full = admin_permissions.ROLE_PERMISSIONS["admin"]
    monkeypatch.setitem(
        admin_permissions.ROLE_PERMISSIONS,
        "admin",
        full - {"admin:docs:debug"},
    )
    assert client.get("/api/v1/admin/users", headers=_debug(admin_token)).status_code == 403
    # 恢复后，缺目标权限 -> 403。
    monkeypatch.setitem(admin_permissions.ROLE_PERMISSIONS, "admin", full)
    monkeypatch.setitem(
        admin_permissions.ROLE_PERMISSIONS,
        "admin",
        full - {"admin:user:read"},
    )
    assert client.get("/api/v1/admin/users", headers=_debug(admin_token)).status_code == 403


def test_debug_rejects_ambiguous_paths(
    client: TestClient, admin_token: str
) -> None:
    headers = _debug(admin_token)
    for path in (
        "/api/v1/admin/users/",
        "/api/v1/admin//users",
        "/api/v1/admin/users%2F1",
        "/api/v1/admin/users%252F1",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 400, (path, response.status_code)


def test_debug_malformed_marker(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/users",
        headers={**auth_headers(admin_token), "X-Admin-Docs-Debug": "yes"},
    )
    assert response.status_code == 400


def test_debug_audit_failure_returns_500(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.core import docs_debug_middleware as middleware

    def _boom(self, *args, **kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(middleware.DocsDebugMiddleware, "_audit", _boom)

    response = client.get("/api/v1/admin/users", headers=_debug(admin_token))
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == 500
    assert body["data"] is None
