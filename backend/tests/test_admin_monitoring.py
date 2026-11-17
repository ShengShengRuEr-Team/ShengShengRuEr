"""T08a：真实采样、阈值、stale 与失败语义（主文档 §9.1—§9.2）。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text


def _service(**kwargs):
    from app.services.admin.monitoring import MonitoringService

    return MonitoringService(**kwargs)


def _clear_scheduler_rows() -> None:
    from app.db.base import SessionLocal
    from app.db.models_admin import AdminJobSchedulerState

    with SessionLocal() as db:
        db.execute(delete(AdminJobSchedulerState))
        db.commit()


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.monotonic_value = 0.0

    def clock(self):
        return self.now

    def monotonic(self):
        self.monotonic_value += 0.01
        return self.monotonic_value


def test_collect_real_metrics_on_windows() -> None:
    _clear_scheduler_rows()
    service = _service()
    first = service.collect()
    metrics = first["metrics"]

    assert metrics["database.connection_available"]["value"] is True
    assert metrics["database.connection_available"]["status"] == "ok"
    assert metrics["database.probe_latency_ms"]["value"] >= 0
    assert metrics["database.database_size_bytes"]["value"] > 0
    assert metrics["database.active_connections"]["value"] >= 0
    assert metrics["database.pool_checked_out"]["status"] == "ok"
    assert metrics["database.pool_size"]["status"] == "ok"

    # 首次 CPU 差值为 0：明确 unknown(warmup)，不伪造有效值。
    assert metrics["server.system_cpu_percent"]["status"] == "unknown"
    assert metrics["server.system_cpu_percent"]["reason"] == "warmup"

    assert metrics["server.system_memory_used_percent"]["status"] == "ok"
    assert 0 <= metrics["server.system_memory_used_percent"]["value"] <= 100
    assert metrics["server.process_rss_bytes"]["value"] > 0
    assert metrics["server.api_uptime_seconds"]["status"] == "ok"
    assert metrics["server.audio_storage_used_percent"]["status"] == "ok"
    assert "server.audit_storage_health" in metrics
    assert metrics["server.admin_scheduler_health"]["status"] == "not_configured"

    second = service.collect()["metrics"]
    assert second["server.system_cpu_percent"]["status"] == "ok"
    assert second["server.process_cpu_percent"]["status"] == "ok"
    service.dispose()


def test_threshold_requires_three_consecutive_samples() -> None:
    service = _service()
    service._set_ok(
        "server.system_cpu_percent",
        90.0,
        unit="percent",
        source="psutil",
        scope="os_visible",
    )
    service._apply_threshold("server.system_cpu_percent", 90.0, 85.0, 95.0)
    assert service._metrics["server.system_cpu_percent"]["severity"] == "normal"
    service._apply_threshold("server.system_cpu_percent", 90.0, 85.0, 95.0)
    assert service._metrics["server.system_cpu_percent"]["severity"] == "normal"
    service._apply_threshold("server.system_cpu_percent", 90.0, 85.0, 95.0)
    assert service._metrics["server.system_cpu_percent"]["severity"] == "warning"

    service._apply_threshold("server.system_cpu_percent", 99.0, 85.0, 95.0)
    assert service._metrics["server.system_cpu_percent"]["severity"] == "critical"

    # 失败打断连击并清零。
    service._set_bad(
        "server.system_cpu_percent",
        status="error",
        reason="probe_failed",
        unit="percent",
    )
    service._set_ok(
        "server.system_cpu_percent",
        99.0,
        unit="percent",
        source="psutil",
        scope="os_visible",
    )
    assert service._metrics["server.system_cpu_percent"]["consecutive"] == 0
    service._apply_threshold("server.system_cpu_percent", 99.0, 85.0, 95.0)
    assert service._metrics["server.system_cpu_percent"]["severity"] == "normal"


def test_failure_keeps_last_success_and_becomes_stale() -> None:
    _clear_scheduler_rows()
    clock = FakeClock()
    service = _service(clock=clock.clock, monotonic=clock.monotonic)
    first = service.collect()["metrics"]["database.connection_available"]
    assert first["status"] == "ok"
    success_at = first["last_success_at"]

    def _boom():
        raise RuntimeError("connection refused")

    service._dispose_probe_engine()
    service._engine_factory = _boom
    failed = service.collect()["metrics"]["database.connection_available"]
    assert failed["status"] == "error"
    assert failed["value"] is None
    assert failed["last_success_at"] == success_at

    clock.now += timedelta(seconds=61)
    stale = service.snapshot()["metrics"]["database.connection_available"]
    assert stale["status"] == "stale"
    assert stale["reason"].startswith("probe_failed")
    service.dispose()


def test_timeout_is_classified_and_does_not_raise() -> None:
    from sqlalchemy.exc import OperationalError

    service = _service()

    def _timeout():
        raise OperationalError("SELECT 1", {}, Exception("statement timeout"))

    service._engine_factory = _timeout
    snapshot = service.collect()
    metric = snapshot["metrics"]["database.connection_available"]
    assert metric["status"] == "error"
    assert metric["reason"] == "timeout"
    assert snapshot["metrics"]["database.database_size_bytes"]["status"] == "unknown"
    service.dispose()


def test_monitoring_disabled_in_test_environment() -> None:
    from app.core.config import get_settings

    assert get_settings().admin_monitoring_enabled is False


def test_dispose_releases_probe_engine() -> None:
    service = _service()
    service.collect()
    assert service._probe_engine is not None
    service.dispose()
    assert service._probe_engine is None
