"""15 秒采样服务：数据库/OS/存储/审计/调度健康（主文档 §9.1—§9.2）。

- 采样只在本实例进行，不跨实例相加；
- 每轮总预算 5 秒，DB 探针使用独立短连接（connect_timeout=2、
  statement_timeout=1500ms），超时后丢弃连接；
- 失败立即置 error 并保留旧值与旧成功时间；失败超过 60 秒未更新转 stale；
- 阈值只在连续 3 个有效样本后才升级 severity，失败/未知打断连击。
"""

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import psutil
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.security import utc_now

INTERVAL_SECONDS = 15
BUDGET_SECONDS = 5.0
STALE_SECONDS = 60
DB_CONNECT_TIMEOUT = 2
DB_STATEMENT_TIMEOUT_MS = 1500
THRESHOLD_SAMPLES = 3

CPU_THRESHOLD = (85.0, 95.0)
MEMORY_THRESHOLD = (85.0, 95.0)
STORAGE_THRESHOLD = (85.0, 95.0)
LATENCY_THRESHOLD = (500.0, 1500.0)


def _metric(
    *,
    value: Any = None,
    unit: str,
    source: str,
    scope: str,
    status: str,
    reason: str | None = None,
    severity: str = "none",
    observed_at: datetime,
    last_success_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "source": source,
        "scope": scope,
        "status": status,
        "reason": reason,
        "severity": severity,
        "observed_at": observed_at,
        "last_attempt_at": observed_at,
        "last_success_at": last_success_at,
        "consecutive": 0,
    }


class MonitoringService:
    def __init__(
        self,
        *,
        clock=utc_now,
        monotonic=time.monotonic,
        engine_factory=None,
    ) -> None:
        self.instance_id = uuid.uuid4()
        self._clock = clock
        self._monotonic = monotonic
        self._engine_factory = engine_factory or self._default_engine
        self.booted_at = clock()
        self._booted_monotonic = monotonic()
        self._metrics: dict[str, dict[str, Any]] = {}
        self._probe_engine: Engine | None = None
        self._lock = threading.Lock()
        self._os_samples = 0

    # -- 生命周期 ---------------------------------------------------------
    def collect(self) -> dict[str, Any]:
        with self._lock:
            self._collect_database()
            self._collect_os()
            self._collect_storage()
            self._collect_audit_health()
            self._collect_scheduler_health()
        return self.snapshot()

    def dispose(self) -> None:
        with self._lock:
            self._dispose_probe_engine()

    def snapshot(self) -> dict[str, Any]:
        now = self._clock()
        metrics: dict[str, Any] = {}
        for name, metric in self._metrics.items():
            item = dict(metric)
            if (
                item["status"] == "error"
                and item["last_attempt_at"] is not None
                and now - item["last_attempt_at"]
                >= timedelta(seconds=STALE_SECONDS)
            ):
                item["status"] = "stale"
            metrics[name] = item
        return {
            "instance_id": self.instance_id,
            "booted_at": self.booted_at,
            "server_time": now,
            "metrics": metrics,
        }

    # -- 写入辅助 ---------------------------------------------------------
    def _set_ok(
        self,
        name: str,
        value: Any,
        *,
        unit: str,
        source: str,
        scope: str,
        severity: str = "normal",
        reason: str | None = None,
    ) -> None:
        now = self._clock()
        previous = self._metrics.get(name, {})
        previous.update(
            {
                "value": value,
                "unit": unit,
                "source": source,
                "scope": scope,
                "status": "ok",
                "reason": reason,
                "severity": severity,
                "observed_at": now,
                "last_attempt_at": now,
                "last_success_at": now,
            }
        )
        self._metrics[name] = previous

    def _set_bad(
        self,
        name: str,
        *,
        status: str,
        reason: str,
        unit: str = "none",
        source: str = "monitor",
        scope: str = "instance",
    ) -> None:
        now = self._clock()
        previous = self._metrics.get(name, _metric(
            unit=unit, source=source, scope=scope, status=status,
            observed_at=now,
        ))
        previous.update(
            {
                "value": None,
                "unit": unit,
                "source": source,
                "scope": scope,
                "status": status,
                "reason": reason,
                "severity": "none" if status != "error" else "warning",
                "observed_at": now,
                "last_attempt_at": now,
            }
        )
        previous["consecutive"] = 0
        self._metrics[name] = previous

    def _apply_threshold(
        self, name: str, value: float | None, low: float, high: float
    ) -> None:
        metric = self._metrics.get(name)
        if metric is None:
            return
        if metric["status"] != "ok" or value is None:
            metric["consecutive"] = 0
            return
        metric["consecutive"] = int(metric.get("consecutive", 0)) + 1
        if metric["consecutive"] < THRESHOLD_SAMPLES:
            metric["severity"] = "normal"
            return
        if value >= high:
            metric["severity"] = "critical"
        elif value >= low:
            metric["severity"] = "warning"
        else:
            metric["severity"] = "normal"

    # -- 探针 -------------------------------------------------------------
    def _default_engine(self) -> Engine:
        url = get_settings().database_url
        return create_engine(
            url,
            poolclass=NullPool,
            connect_args={
                "connect_timeout": DB_CONNECT_TIMEOUT,
                "options": "-c timezone=UTC",
                "application_name": "ssre-monitor",
            },
        )

    def _get_probe_engine(self) -> Engine:
        if self._probe_engine is None:
            self._probe_engine = self._engine_factory()
        return self._probe_engine

    def _dispose_probe_engine(self) -> None:
        if self._probe_engine is not None:
            try:
                self._probe_engine.dispose()
            finally:
                self._probe_engine = None

    def _collect_database(self) -> None:
        started = self._monotonic()
        try:
            engine = self._get_probe_engine()
            with engine.connect() as connection:
                connection.execute(
                    text(f"SET statement_timeout = '{DB_STATEMENT_TIMEOUT_MS}ms'")
                )
                query_started = self._monotonic()
                connection.execute(text("SELECT 1"))
                latency_ms = (self._monotonic() - query_started) * 1000
                size = connection.execute(
                    text("SELECT pg_database_size(current_database())")
                ).scalar()
                counts = connection.execute(
                    text(
                        "SELECT"
                        " count(*) FILTER (WHERE state = 'active'),"
                        " count(*)"
                        " FROM pg_stat_activity"
                        " WHERE datname = current_database()"
                    )
                ).one()

            self._set_ok(
                "database.connection_available",
                True,
                unit="bool",
                source="postgresql",
                scope="instance",
            )
            self._set_ok(
                "database.probe_latency_ms",
                round(latency_ms, 2),
                unit="ms",
                source="postgresql",
                scope="instance",
            )
            self._apply_threshold(
                "database.probe_latency_ms", latency_ms, *LATENCY_THRESHOLD
            )
            self._set_ok(
                "database.database_size_bytes",
                int(size or 0),
                unit="bytes",
                source="postgresql",
                scope="database",
            )
            self._set_ok(
                "database.active_connections",
                int(counts[0] or 0),
                unit="count",
                source="postgresql",
                scope="database",
            )
            self._set_ok(
                "database.total_connections",
                int(counts[1] or 0),
                unit="count",
                source="postgresql",
                scope="database",
            )
        except Exception as exc:  # noqa: BLE001 - 采样失败不得抛到主循环
            self._dispose_probe_engine()
            reason = _classify_exception(exc)
            self._set_bad(
                "database.connection_available",
                status="error",
                reason=reason,
                unit="bool",
                source="postgresql",
            )
            for name, unit in (
                ("database.probe_latency_ms", "ms"),
                ("database.database_size_bytes", "bytes"),
                ("database.active_connections", "count"),
                ("database.total_connections", "count"),
            ):
                self._set_bad(
                    name,
                    status="unknown",
                    reason=reason,
                    unit=unit,
                    source="postgresql",
                )
        finally:
            del started

        self._collect_pool()

    def _collect_pool(self) -> None:
        try:
            from sqlalchemy.pool import QueuePool

            from app.db.base import engine as business_engine

            pool = business_engine.pool
            if not isinstance(pool, QueuePool):
                for name in (
                    "database.pool_checked_out",
                    "database.pool_size",
                    "database.pool_overflow",
                ):
                    self._set_bad(
                        name,
                        status="not_applicable",
                        reason="pool_type_not_queuepool",
                        unit="count",
                        source="sqlalchemy_pool",
                    )
                return
            checked_out = pool.checkedout()
            size = pool.size()
            overflow = pool.overflow()
            self._set_ok(
                "database.pool_checked_out",
                checked_out,
                unit="count",
                source="sqlalchemy_pool",
                scope="instance",
            )
            self._set_ok(
                "database.pool_size",
                size,
                unit="count",
                source="sqlalchemy_pool",
                scope="instance",
            )
            self._set_ok(
                "database.pool_overflow",
                overflow,
                unit="count",
                source="sqlalchemy_pool",
                scope="instance",
            )
        except Exception as exc:  # noqa: BLE001
            for name in (
                "database.pool_checked_out",
                "database.pool_size",
                "database.pool_overflow",
            ):
                self._set_bad(
                    name,
                    status="unknown",
                    reason=_classify_exception(exc),
                    unit="count",
                    source="sqlalchemy_pool",
                )

    def _collect_os(self) -> None:
        self._os_samples += 1
        try:
            process = psutil.Process()
            cpu_percent = psutil.cpu_percent(interval=None)
            memory_percent = psutil.virtual_memory().percent
            process_cpu = process.cpu_percent(interval=None)
            rss = process.memory_info().rss
        except Exception as exc:  # noqa: BLE001
            reason = _classify_exception(exc)
            for name, unit in (
                ("server.system_cpu_percent", "percent"),
                ("server.system_memory_used_percent", "percent"),
                ("server.process_cpu_percent", "percent"),
                ("server.process_rss_bytes", "bytes"),
            ):
                self._set_bad(
                    name, status="unknown", reason=reason, unit=unit,
                    source="psutil", scope="os_visible",
                )
            return

        if self._os_samples == 1:
            # 首次 CPU 差值为 0，不伪造成有效使用率。
            for name in (
                "server.system_cpu_percent",
                "server.process_cpu_percent",
            ):
                self._set_bad(
                    name,
                    status="unknown",
                    reason="warmup",
                    unit="percent",
                    source="psutil",
                    scope="os_visible",
                )
        else:
            self._set_ok(
                "server.system_cpu_percent",
                round(cpu_percent, 2),
                unit="percent",
                source="psutil",
                scope="os_visible",
            )
            self._apply_threshold(
                "server.system_cpu_percent", cpu_percent, *CPU_THRESHOLD
            )
            self._set_ok(
                "server.process_cpu_percent",
                round(process_cpu, 2),
                unit="percent",
                source="psutil",
                scope="process",
            )

        self._set_ok(
            "server.system_memory_used_percent",
            round(memory_percent, 2),
            unit="percent",
            source="psutil",
            scope="os_visible",
        )
        self._apply_threshold(
            "server.system_memory_used_percent", memory_percent, *MEMORY_THRESHOLD
        )
        self._set_ok(
            "server.process_rss_bytes",
            int(rss),
            unit="bytes",
            source="psutil",
            scope="process",
        )
        self._set_ok(
            "server.api_uptime_seconds",
            round(self._monotonic() - self._booted_monotonic, 2),
            unit="seconds",
            source="process",
            scope="instance",
        )

    def _collect_storage(self) -> None:
        try:
            path = get_settings().audio_storage_path
            usage = psutil.disk_usage(str(path))
            if not path.exists():
                self._set_bad(
                    "server.audio_storage_free_bytes",
                    status="error",
                    reason="storage_dir_missing",
                    unit="bytes",
                    source="psutil",
                    scope="filesystem",
                )
                self._set_bad(
                    "server.audio_storage_used_percent",
                    status="error",
                    reason="storage_dir_missing",
                    unit="percent",
                    source="psutil",
                    scope="filesystem",
                )
                return
            self._set_ok(
                "server.audio_storage_free_bytes",
                int(usage.free),
                unit="bytes",
                source="psutil",
                scope="filesystem",
            )
            self._set_ok(
                "server.audio_storage_used_percent",
                round(usage.percent, 2),
                unit="percent",
                source="psutil",
                scope="filesystem",
            )
            self._apply_threshold(
                "server.audio_storage_used_percent", usage.percent, *STORAGE_THRESHOLD
            )
        except Exception as exc:  # noqa: BLE001
            reason = _classify_exception(exc)
            for name, unit in (
                ("server.audio_storage_free_bytes", "bytes"),
                ("server.audio_storage_used_percent", "percent"),
            ):
                self._set_bad(
                    name, status="error", reason=reason, unit=unit,
                    source="psutil", scope="filesystem",
                )

    def _collect_audit_health(self) -> None:
        try:
            from app.services.admin.audit import audit_storage_health

            snapshot = audit_storage_health()
            state = str(snapshot.get("state", "unknown"))
            if state == "ok":
                status, severity = "ok", "normal"
            elif state == "warning":
                status, severity = "error", "warning"
            elif state == "critical":
                status, severity = "error", "critical"
            else:
                status, severity = "unknown", "none"
            self._set_ok(
                "server.audit_storage_health",
                state,
                unit="state",
                source="audit_service",
                scope="instance",
                severity=severity,
                reason=snapshot.get("last_error_code"),
            )
            if status != "ok":
                metric = self._metrics["server.audit_storage_health"]
                metric["status"] = status
        except Exception as exc:  # noqa: BLE001
            self._set_bad(
                "server.audit_storage_health",
                status="unknown",
                reason=_classify_exception(exc),
                unit="state",
                source="audit_service",
            )

    def _collect_scheduler_health(self) -> None:
        name = "server.admin_scheduler_health"
        try:
            engine = self._get_probe_engine()
            with engine.connect() as connection:
                connection.execute(
                    text(f"SET statement_timeout = '{DB_STATEMENT_TIMEOUT_MS}ms'")
                )
                latest = connection.execute(
                    text("SELECT max(heartbeat_at) FROM admin_job_scheduler_state")
                ).scalar()
        except Exception as exc:  # noqa: BLE001
            self._set_bad(
                name,
                status="unknown",
                reason=_classify_exception(exc),
                unit="state",
                source="scheduler_heartbeat",
            )
            return

        if latest is None:
            self._set_bad(
                name,
                status="not_configured",
                reason="no_scheduler_instance",
                unit="state",
                source="scheduler_heartbeat",
            )
            return
        age = (self._clock() - latest).total_seconds()
        if age > 60:
            self._set_bad(
                name,
                status="stale",
                reason="heartbeat_stale",
                unit="state",
                source="scheduler_heartbeat",
            )
        else:
            self._set_ok(
                name,
                "ok",
                unit="state",
                source="scheduler_heartbeat",
                scope="instance",
            )


def _classify_exception(exc: Exception) -> str:
    name = type(exc).__name__
    lower = str(exc).lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "permission" in lower or "privilege" in lower:
        return "permission_denied"
    if "does not exist" in lower or "undefinedtable" in lower:
        return "missing_structure"
    return f"probe_failed:{name}"


_service: MonitoringService | None = None


def set_monitoring_service(service: MonitoringService | None) -> None:
    global _service
    _service = service


def get_monitoring_service() -> MonitoringService | None:
    return _service
