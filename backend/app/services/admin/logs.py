"""审计日志服务：时间窗、DTO 清洗与详情（主文档 §7.3）。

时间窗规则：
- 默认北京时间「今天 00:00 前 6 天」到「明天 00:00」，左闭右开；
- 只传一端 422；反向区间 422；相等返回空；
- 单次跨度 ≤90 天；无时区字符串 422。
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.admin_permissions import role_snapshot as _role_snapshot
from app.core.errors import AppError
from app.db.models_admin import AdminAuditEvent, AdminLoginEvent
from app.repositories.admin import logs as logs_repo
from app.schemas_admin.logs import (
    LoginLogOut,
    LoginLogPage,
    OperationLogOut,
    OperationLogPage,
)
from app.services.admin import audit

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_WINDOW_DAYS = 7  # 今天 + 前 6 天
MAX_WINDOW_DAYS = 90
USER_AGENT_SUMMARY_LENGTH = 80


def _invalid_parameter() -> AppError:
    return AppError(422, "请求参数校验失败")


def role_snapshot_label(roles: tuple[str, ...]) -> str | None:
    return _role_snapshot(roles)


def parse_time(value: str, *, field: str) -> datetime:
    candidate = value.strip()
    if not candidate:
        raise _invalid_parameter()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        raise _invalid_parameter() from None
    if parsed.tzinfo is None:
        # 文档要求时间必须带时区，不做隐式猜测。
        raise _invalid_parameter()
    del field
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime


def resolve_time_window(
    start_at: str | None,
    end_at: str | None,
    *,
    now: datetime | None = None,
) -> TimeWindow:
    if (start_at is None) != (end_at is None):
        raise _invalid_parameter()

    if start_at is not None and end_at is not None:
        start = parse_time(start_at, field="start_at")
        end = parse_time(end_at, field="end_at")
    else:
        current = (now or datetime.now(UTC)).astimezone(DISPLAY_TZ)
        today_start = datetime.combine(
            current.date(), time.min, tzinfo=DISPLAY_TZ
        )
        start = (today_start - timedelta(days=DEFAULT_WINDOW_DAYS - 1)).astimezone(
            UTC
        )
        end = (today_start + timedelta(days=1)).astimezone(UTC)

    if end < start:
        raise _invalid_parameter()
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise _invalid_parameter()
    return TimeWindow(start=start, end=end)


def _ua_summary(value: str) -> str:
    return (value or "")[:USER_AGENT_SUMMARY_LENGTH]


def _ip_text(value) -> str | None:
    """psycopg 对 INET 返回 ipaddress 对象，DTO 统一成字符串。"""

    return None if value is None else str(value)


def validate_ip(value: str | None) -> str | None:
    """筛选 IP 必须是合法地址；非法按 422，不做模糊匹配。"""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    import ipaddress

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        raise _invalid_parameter() from None


def to_login_log(row: AdminLoginEvent) -> LoginLogOut:
    return LoginLogOut(
        event_id=row.event_id,
        request_id=row.request_id,
        occurred_at=row.occurred_at,
        event_type=row.event_type,
        username_attempted=row.username_attempted,
        actor_user_id=row.actor_user_id,
        actor_name=row.actor_name,
        role_snapshot=row.role_snapshot,
        result=row.result,
        reason_code=row.reason_code,
        ip=_ip_text(row.ip),
        user_agent_summary=_ua_summary(row.user_agent),
        duration_ms=row.duration_ms,
    )


def to_operation_log(row: AdminAuditEvent) -> OperationLogOut:
    return OperationLogOut(
        event_id=row.event_id,
        request_id=row.request_id,
        occurred_at=row.occurred_at,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        actor_name=row.actor_name,
        role_snapshot=row.role_snapshot,
        target_type=row.target_type,
        target_id=row.target_id,
        result=row.result,
        reason_code=row.reason_code,
        # 读取侧再按白名单过滤一次。
        summary=audit.filter_summary(row.event_type, row.summary),
        ip=_ip_text(row.ip),
        user_agent_summary=_ua_summary(row.user_agent),
        duration_ms=row.duration_ms,
        run_id=row.run_id,
    )


def list_login_logs(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    username: str | None,
    result: str | None,
    failure_type: str | None,
    ip: str | None,
    page: int,
    page_size: int,
) -> LoginLogPage:
    rows, total = logs_repo.list_login_events(
        db,
        start=start,
        end=end,
        username=username,
        result=result,
        failure_type=failure_type,
        ip=ip,
        page=page,
        page_size=page_size,
    )
    return LoginLogPage(
        items=[to_login_log(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_login_log(db: Session, event_id: uuid.UUID) -> LoginLogOut | None:
    row = logs_repo.get_login_event(db, event_id)
    return to_login_log(row) if row is not None else None


def list_operation_logs(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    actor_username: str | None,
    event_type: str | None,
    result: str | None,
    target_type: str | None,
    page: int,
    page_size: int,
) -> OperationLogPage:
    rows, total = logs_repo.list_operation_events(
        db,
        start=start,
        end=end,
        actor_username=actor_username,
        event_type=event_type,
        result=result,
        target_type=target_type,
        page=page,
        page_size=page_size,
    )
    return OperationLogPage(
        items=[to_operation_log(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_operation_log(
    db: Session, event_id: uuid.UUID
) -> OperationLogOut | None:
    row = logs_repo.get_operation_event(db, event_id)
    return to_operation_log(row) if row is not None else None
