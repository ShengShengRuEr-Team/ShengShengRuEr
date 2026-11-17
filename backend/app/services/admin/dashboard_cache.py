"""首页汇总的进程内 TTL 缓存（主文档 §9.5：真实缓存，不是名义缓存）。

- 唯一域 admin_dashboard_summary、唯一键 overview，每进程最多 1 项；
- TTL 15 秒，用单调时钟判断过期，命中时 as_of 不变；
- 实例内锁单飞；hits/misses 从进程启动累加，过期访问计 miss；
- 实例 UUID 每进程一个；重启后计数归零、instance_id 变化（T08 复用）。
"""

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.security import utc_now

DOMAIN = "admin_dashboard_summary"
KEY = "overview"
TTL_SECONDS = 15

#: 可在测试中替换的单调时钟。
_monotonic = time.monotonic


def monotonic() -> float:
    return _monotonic()


@dataclass(frozen=True)
class CachedSnapshot:
    cards: dict[str, int]
    as_of: datetime
    window_start: datetime
    window_end: datetime
    timezone: str
    cached_at: datetime
    expires_monotonic: float


class DashboardCache:
    def __init__(self, *, ttl_seconds: int = TTL_SECONDS) -> None:
        self.domain = DOMAIN
        self.key = KEY
        self.instance_id = uuid.uuid4()
        self.ttl_seconds = ttl_seconds
        self._entry: CachedSnapshot | None = None
        self._lock = threading.Lock()
        #: 单飞：同一时刻只允许一个请求重建缓存。
        self.build_lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def lookup(self, *, count: bool = True) -> CachedSnapshot | None:
        with self._lock:
            entry = self._entry
            if entry is None:
                if count:
                    self.misses += 1
                return None
            if monotonic() >= entry.expires_monotonic:
                self._entry = None
                if count:
                    self.misses += 1
                return None
            if count:
                self.hits += 1
            return entry

    def store(self, snapshot: CachedSnapshot) -> None:
        with self._lock:
            self._entry = snapshot

    def entries_metadata(self) -> list[dict]:
        """只返回元数据，不返回值（T08 缓存页）。"""

        with self._lock:
            entry = self._entry
            if entry is None or monotonic() >= entry.expires_monotonic:
                return []
            remaining = max(
                0, int(entry.expires_monotonic - monotonic())
            )
            return [
                {
                    "key": self.key,
                    "cached_at": entry.cached_at,
                    "expires_at": cache_expiry(entry.cached_at),
                    "ttl_seconds": self.ttl_seconds,
                    "remaining_seconds": remaining,
                }
            ]

    def clear(self) -> None:
        with self._lock:
            self._entry = None

    def metadata(self) -> dict:
        with self._lock:
            entry = self._entry
            expired = entry is not None and monotonic() >= entry.expires_monotonic
            return {
                "domain": self.domain,
                "key": self.key,
                "instance_id": str(self.instance_id),
                "enabled": getattr(self, "enabled", True),
                "ttl_seconds": self.ttl_seconds,
                "entries": 0 if entry is None or expired else 1,
                "hits": self.hits,
                "misses": self.misses,
            }


_cache: DashboardCache | None = None
_cache_lock = threading.Lock()


def get_dashboard_cache() -> DashboardCache:
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = DashboardCache()
        return _cache


def reset_dashboard_cache() -> DashboardCache:
    """测试/多实例模拟：丢弃当前实例缓存并返回新实例。"""

    global _cache
    with _cache_lock:
        _cache = DashboardCache()
        return _cache


def cache_expiry(cached_at: datetime, ttl_seconds: int = TTL_SECONDS) -> datetime:
    return cached_at + timedelta(seconds=ttl_seconds)
