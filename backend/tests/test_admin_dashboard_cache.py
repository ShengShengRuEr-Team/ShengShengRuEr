"""首页汇总缓存（AC-20 缓存部分，主文档 §9.5）。

按 tests/conftest.py 约定，`app.*` 一律在夹具/用例内延迟导入。
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def _cache_module():
    from app.services.admin import dashboard_cache

    return dashboard_cache


def _service():
    from app.services.admin import dashboard as service

    return service


@pytest.fixture(autouse=True)
def reset_cache():
    _cache_module().reset_dashboard_cache()
    yield
    _cache_module().reset_dashboard_cache()


def _get(client: TestClient, token: str) -> dict:
    response = client.get("/api/v1/admin/dashboard", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_first_miss_then_hit_keeps_same_as_of(
    client: TestClient, admin_token: str
) -> None:
    first = _get(client, admin_token)
    second = _get(client, admin_token)

    assert first["cache"]["status"] == "miss"
    assert second["cache"]["status"] == "hit"
    # 命中缓存时 as_of 仍是快照生成时刻。
    assert second["as_of"] == first["as_of"]
    assert second["window_start"] == first["window_start"]
    assert second["window_end"] == first["window_end"]
    assert second["cards"] == first["cards"]
    assert second["cache"]["cached_at"] == first["cache"]["cached_at"]
    assert second["cache"]["ttl_seconds"] == 15

    metadata = _cache_module().get_dashboard_cache().metadata()
    assert metadata["entries"] == 1
    assert metadata["hits"] == 1
    assert metadata["misses"] == 1


def test_expired_entry_is_miss_and_rebuilt(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    cache_module = _cache_module()
    first = _get(client, admin_token)
    assert first["cache"]["status"] == "miss"

    start = cache_module.monotonic()
    monkeypatch.setattr(cache_module, "_monotonic", lambda: start + 16)

    second = _get(client, admin_token)
    assert second["cache"]["status"] == "miss"
    assert second["as_of"] >= first["as_of"]
    metadata = cache_module.get_dashboard_cache().metadata()
    assert metadata["misses"] >= 2
    assert metadata["entries"] == 1


def test_cache_keeps_at_most_one_entry(
    client: TestClient, admin_token: str
) -> None:
    for _ in range(3):
        _get(client, admin_token)
    metadata = _cache_module().get_dashboard_cache().metadata()
    assert metadata["entries"] == 1
    assert metadata["domain"] == "admin_dashboard_summary"
    assert metadata["key"] == "overview"


def test_new_instance_resets_counters_and_id(
    client: TestClient, admin_token: str
) -> None:
    cache_module = _cache_module()
    first_cache = cache_module.get_dashboard_cache()
    _get(client, admin_token)
    _get(client, admin_token)
    assert first_cache.hits >= 1

    new_cache = cache_module.reset_dashboard_cache()
    assert new_cache.instance_id != first_cache.instance_id
    assert new_cache.hits == 0
    assert new_cache.misses == 0

    data = _get(client, admin_token)
    assert data["cache"]["status"] == "miss"


def test_disabled_cache_is_not_configured(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "admin_dashboard_cache_enabled", False)

    first = _get(client, admin_token)
    second = _get(client, admin_token)

    assert first["cache"]["enabled"] is False
    assert first["cache"]["status"] == "not_configured"
    assert first["cache"]["cached_at"] is None
    assert second["cache"]["status"] == "not_configured"
    assert _cache_module().get_dashboard_cache().metadata()["entries"] == 0
    assert second["as_of"] >= first["as_of"]


def test_failure_is_not_cached(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.core.errors import AppError

    service = _service()
    cache_module = _cache_module()

    def _boom():
        raise AppError(500, "服务器内部错误")

    with monkeypatch.context() as m:
        m.setattr(service, "_compute_snapshot", _boom)
        failed = client.get(
            "/api/v1/admin/dashboard", headers=auth_headers(admin_token)
        )
    assert failed.status_code == 500
    assert cache_module.get_dashboard_cache().metadata()["entries"] == 0

    recovered = _get(client, admin_token)
    assert recovered["cache"]["status"] == "miss"
    assert cache_module.get_dashboard_cache().metadata()["entries"] == 1


def test_single_flight_rebuild(monkeypatch) -> None:
    service = _service()
    cache_module = _cache_module()
    calls = {"count": 0}
    original = service._compute_snapshot

    def _slow():
        calls["count"] += 1
        import time

        time.sleep(0.1)
        return original()

    monkeypatch.setattr(service, "_compute_snapshot", _slow)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.build_dashboard(), range(4)))

    assert calls["count"] == 1
    assert len({item.as_of for item in results}) == 1
    assert cache_module.get_dashboard_cache().metadata()["entries"] == 1
