"""首页汇总服务（主文档 §9.5 / 需求 §10.1）。

统计在单只读一致快照中计算：事务第一条语句即
``SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY``，
随后设置 5000ms statement_timeout；超时/异常返回 500，不缓存、不返回部分结果。

缓存命中时 as_of 仍是快照生成时刻；cached_at/expires_at/age 反映读取时刻。
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import utc_now
from app.db.base import engine
from app.repositories.admin.dashboard import compute_cards
from app.schemas_admin.dashboard import (
    DashboardCacheInfo,
    DashboardCards,
    DashboardData,
)
from app.services.admin import dashboard_cache

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
WINDOW_DAYS = 7  # 今天 00:00 之前 6 天起
STATEMENT_TIMEOUT_MS = 5000


def resolve_window(as_of: datetime) -> tuple[datetime, datetime]:
    """北京时间今天 00:00 前 6 天至明天 00:00；上界取 min(明天 00:00, as_of)。"""

    local = as_of.astimezone(DISPLAY_TZ)
    today_start = datetime.combine(local.date(), time.min, tzinfo=DISPLAY_TZ)
    start_local = today_start - timedelta(days=WINDOW_DAYS - 1)
    end_local = today_start + timedelta(days=1)
    window_start = start_local.astimezone(UTC)
    window_end = min(end_local.astimezone(UTC), as_of)
    return window_start, window_end


def _compute_snapshot() -> dashboard_cache.CachedSnapshot:
    as_of = utc_now()
    window_start, window_end = resolve_window(as_of)
    try:
        with engine.connect() as connection:
            # 必须是事务第一条语句：不得在已有事务中途切换隔离级别。
            connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
            connection.execute(
                text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
            )
            cards = compute_cards(
                connection,
                window_start=window_start,
                window_end=window_end,
            )
            connection.rollback()
    except SQLAlchemyError as exc:  # 超时、断库、SQL 失败一律 500
        raise AppError(500, "服务器内部错误") from exc

    return dashboard_cache.CachedSnapshot(
        cards=cards,
        as_of=as_of,
        window_start=window_start,
        window_end=window_end,
        timezone="Asia/Shanghai",
        cached_at=utc_now(),
        expires_monotonic=dashboard_cache.monotonic()
        + dashboard_cache.TTL_SECONDS,
    )


def _cache_info(
    *,
    enabled: bool,
    status: str,
    snapshot: dashboard_cache.CachedSnapshot | None,
    now: datetime,
) -> DashboardCacheInfo:
    if not enabled or snapshot is None:
        return DashboardCacheInfo(
            enabled=enabled,
            status="not_configured" if not enabled else status,  # type: ignore[arg-type]
            ttl_seconds=dashboard_cache.TTL_SECONDS,
            cached_at=None,
            expires_at=None,
            age_seconds=None,
        )
    age = max(0, int((now - snapshot.cached_at).total_seconds()))
    return DashboardCacheInfo(
        enabled=True,
        status=status,  # type: ignore[arg-type]
        ttl_seconds=dashboard_cache.TTL_SECONDS,
        cached_at=snapshot.cached_at,
        expires_at=dashboard_cache.cache_expiry(snapshot.cached_at),
        age_seconds=age,
    )


def build_dashboard() -> DashboardData:
    settings = get_settings()
    enabled = settings.admin_dashboard_cache_enabled
    cache = dashboard_cache.get_dashboard_cache()
    cache.enabled = enabled  # 供 T08 元数据展示

    if not enabled:
        snapshot = _compute_snapshot()
        return DashboardData(
            as_of=snapshot.as_of,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
            timezone=snapshot.timezone,
            cache=_cache_info(
                enabled=False, status="not_configured", snapshot=None, now=utc_now()
            ),
            cards=DashboardCards(**snapshot.cards),
        )

    cached = cache.lookup()
    if cached is not None:
        return DashboardData(
            as_of=cached.as_of,
            window_start=cached.window_start,
            window_end=cached.window_end,
            timezone=cached.timezone,
            cache=_cache_info(
                enabled=True, status="hit", snapshot=cached, now=utc_now()
            ),
            cards=DashboardCards(**cached.cards),
        )

    # 单飞：只有一个请求重建，其余等待后复用同一次结果。
    with cache.build_lock:
        cached = cache.lookup(count=False)
        if cached is not None:
            return DashboardData(
                as_of=cached.as_of,
                window_start=cached.window_start,
                window_end=cached.window_end,
                timezone=cached.timezone,
                cache=_cache_info(
                    enabled=True, status="hit", snapshot=cached, now=utc_now()
                ),
                cards=DashboardCards(**cached.cards),
            )
        snapshot = _compute_snapshot()
        cache.store(snapshot)

    return DashboardData(
        as_of=snapshot.as_of,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        timezone=snapshot.timezone,
        cache=_cache_info(
            enabled=True, status="miss", snapshot=snapshot, now=utc_now()
        ),
        cards=DashboardCards(**snapshot.cards),
    )
