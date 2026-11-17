"""T08b：监控读取、缓存清理、TLS 证据、OAuth、健康与白名单（§9.2—§9.5）。"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers

API = "/api/v1/admin/monitor"


def _session():
    from app.db.base import SessionLocal

    return SessionLocal()


def test_monitor_auth(client: TestClient, student_token: str) -> None:
    assert client.get(f"{API}/database").status_code == 401
    for path in ("database", "server", "cache", "cache/entries", "transport", "oauth"):
        assert (
            client.get(f"{API}/{path}", headers=auth_headers(student_token)).status_code
            == 403
        )
    assert (
        client.post(
            f"{API}/cache/clear",
            json={"domain": "x", "expected_instance_id": "y", "reason": "r"},
            headers=auth_headers(student_token),
        ).status_code
        == 403
    )


def test_database_and_server_payloads(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    db = client.get(f"{API}/database", headers=headers)
    assert db.status_code == 200, db.text
    body = db.json()["data"]
    assert body["sampling"] == "on_demand"
    metrics = body["metrics"]
    assert metrics["database.connection_available"]["status"] == "ok"
    assert set(metrics) <= {
        name for name in metrics if name.startswith("database.")
    }

    server = client.get(f"{API}/server", headers=headers)
    assert server.status_code == 200
    data = server.json()["data"]
    assert "server.system_memory_used_percent" in data["metrics"]
    assert data["module3"]["status"] == "not_configured"
    assert data["module3"]["reason"] == "disabled"
    assert data["module3"]["worker_liveness"] == "unknown"

    raw = server.text + db.text
    from app.core.config import get_settings

    assert get_settings().database_url not in raw
    assert "password" not in raw.lower()
    assert "JWT_SECRET_KEY" not in raw


def test_cache_overview_entries_and_clear(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    overview = client.get(f"{API}/cache", headers=headers)
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["domain"] == "admin_dashboard_summary"
    assert data["redis"]["status"] == "not_configured"

    entries = client.get(f"{API}/cache/entries", headers=headers).json()["data"]
    assert entries["total"] in (0, 1)
    if entries["items"]:
        assert set(entries["items"][0]) == {
            "key",
            "cached_at",
            "expires_at",
            "ttl_seconds",
            "remaining_seconds",
        }

    cleared = client.post(
        f"{API}/cache/clear",
        json={
            "domain": "admin_dashboard_summary",
            "expected_instance_id": data["instance_id"],
            "reason": "维护",
        },
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["deleted_count"] in (0, 1)

    bad_domain = client.post(
        f"{API}/cache/clear",
        json={
            "domain": "other",
            "expected_instance_id": data["instance_id"],
            "reason": "维护",
        },
        headers=headers,
    )
    assert bad_domain.status_code == 400
    bad_instance = client.post(
        f"{API}/cache/clear",
        json={
            "domain": "admin_dashboard_summary",
            "expected_instance_id": str(uuid.uuid4()),
            "reason": "维护",
        },
        headers=headers,
    )
    assert bad_instance.status_code == 400


def test_started_audit_failure_prevents_deletion(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.services.admin import cache_admin

    class BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            raise RuntimeError("audit down")

        def rollback(self):
            pass

    monkeypatch.setattr(cache_admin, "SessionLocal", lambda: BrokenSession())
    called = {"deleted": False}
    original = cache_admin.dashboard_cache.get_dashboard_cache

    class Cache:
        instance_id = uuid.uuid4()
        build_lock = None

        def entries_metadata(self):
            return []

        def clear(self):
            called["deleted"] = True

    monkeypatch.setattr(cache_admin.dashboard_cache, "get_dashboard_cache", lambda: Cache())
    from app.api.deps import require_permission  # noqa: F401

    # 通过服务直接验证：STARTED 落库失败 → 抛 500 且未删除。
    from app.api.deps import CurrentUser
    from app.core.errors import AppError
    from app.core.request_context import monotonic_ms

    from datetime import UTC, datetime, timedelta

    actor = CurrentUser(
        id=1,
        username="admin",
        nickname="管理员",
        roles=("admin",),
        jti="x",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        auth_version=0,
        session_id=uuid.uuid4(),
    )
    with pytest.raises(AppError):
        cache_admin.clear_cache(
            actor=actor,
            domain="admin_dashboard_summary",
            expected_instance_id=str(Cache.instance_id),
            reason="维护",
            request_id=uuid.uuid4(),
            ip=None,
            user_agent="test",
            started_at=monotonic_ms(),
        )
    assert called["deleted"] is False
    monkeypatch.setattr(cache_admin.dashboard_cache, "get_dashboard_cache", original)


def test_oauth_fixed_response(client: TestClient, admin_token: str) -> None:
    response = client.get(f"{API}/oauth", headers=auth_headers(admin_token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "not_configured"
    assert data["enabled"] is False
    assert data["events"] == []


def test_transport_direct_http(admin_token: str) -> None:
    from app.main import application

    with TestClient(application) as tls_client:
        payload = tls_client.get(
            f"{API}/transport", headers=auth_headers(admin_token)
        ).json()["data"]
        assert payload["direct_scheme"] == "http"
        assert payload["external_tls_state"] in {"not_configured", "unknown"}
        assert "configured_public_origin" in payload


def test_transport_evidence_rules(monkeypatch) -> None:
    from app.core import transport_evidence as te

    settings = SimpleNamespace(
        trusted_proxy_cidrs="127.0.0.1/32",
        proxy_header_mode="x_forwarded",
        public_origin="https://example.test",
    )
    monkeypatch.setattr(te, "get_settings", lambda: settings)

    base = {"scheme": "http", "client": ("127.0.0.1", 1234), "headers": []}
    trusted_https = dict(base, headers=[(b"x-forwarded-proto", b"https")])
    evidence = te.build_evidence(trusted_https)
    assert evidence.peer_trusted is True
    assert evidence.external_tls_state == "tls"

    multi = dict(base, headers=[(b"x-forwarded-proto", b"https,https")])
    assert te.build_evidence(multi).external_tls_state == "unknown"

    forged = dict(base, client=("203.0.113.9", 1), headers=[(b"x-forwarded-proto", b"https")])
    assert te.build_evidence(forged).external_tls_state == "unknown"

    duplicate = dict(base, headers=[(b"x-forwarded-proto", b"https"), (b"x-forwarded-proto", b"http")])
    assert te.build_evidence(duplicate).external_tls_state == "unknown"


def test_health_live_and_ready(client: TestClient, monkeypatch) -> None:
    assert client.get("/health/live").json() == {"status": "alive"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200, ready.text
    assert ready.json() == {"status": "ready"}

    from app.api import health

    monkeypatch.setattr(health, "REQUIRED_TABLES", ("users", "no_such_table"))
    broken = client.get("/health/ready")
    assert broken.status_code == 503
    assert broken.json() == {"status": "not_ready"}
    assert "password" not in broken.text.lower()


def test_ready_handles_db_failure(monkeypatch) -> None:
    from fastapi.testclient import TestClient as TC

    from app.api import health
    from app.main import app

    class BoomEngine:
        def connect(self):
            raise RuntimeError("connection refused postgresql://u:p@h/db")

    monkeypatch.setattr(health, "_engine", lambda: BoomEngine())
    with TC(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "postgres" not in response.text


def test_doc_debug_allowlist_matches_routes() -> None:
    from app.core.admin_permissions import DOC_DEBUG_ALLOWLIST
    from app.main import app

    paths = app.openapi()["paths"]

    def permissions_of(route) -> set[str]:
        found: set[str] = set()
        stack = list(route.dependant.dependencies)
        while stack:
            dep = stack.pop()
            stack.extend(dep.dependencies)
            closure = getattr(dep.call, "__closure__", None)
            if closure:
                for cell in closure:
                    try:
                        value = cell.cell_contents
                    except ValueError:
                        continue
                    if isinstance(value, str) and value.startswith("admin:"):
                        found.add(value)
        return found

    def _walk(routes, prefix: str = ""):
        for route in routes:
            include = getattr(route, "original_router", None)
            if include is not None:
                yield from _walk(
                    include.routes,
                    prefix + (route.include_context.prefix or ""),
                )
            elif hasattr(route, "path") and hasattr(route, "dependant"):
                yield prefix + route.path, route

    flattened = list(_walk(app.routes))

    for method, template, permission in DOC_DEBUG_ALLOWLIST:
        assert template in paths, template
        assert method.lower() in paths[template], (method, template)
        matches = [
            route
            for full_path, route in flattened
            if full_path == template
            and method in getattr(route, "methods", set())
        ]
        assert matches, (method, template)
        assert permission in permissions_of(matches[0]), (
            template,
            permission,
            permissions_of(matches[0]),
        )


def test_monitor_debug_requests_pass_whitelist(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token) | {"X-Admin-Docs-Debug": "1"}
    allowed = client.get(f"{API}/oauth", headers=headers)
    assert allowed.status_code == 200, allowed.text
    blocked = client.post(f"{API}/cache/clear", headers=headers, json={})
    assert blocked.status_code == 400
