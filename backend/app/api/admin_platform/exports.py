"""CSV 导出路由：用户、登录日志、操作日志（主文档 §11.1）。

不分页、不流式：单快照生成完整 bytes 后一次性返回。
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.admin_platform.common import (
    request_ip,
    request_user_agent,
)
from app.api.deps import CurrentUser, require_permissions
from app.core.admin_enums import (
    EVENT_TYPES,
    LOG_RESULTS,
    LOGIN_FAILURE_TYPES,
    TARGET_TYPES,
)
from app.core.admin_permissions import (
    PERM_EXPORT_LOGIN_LOGS,
    PERM_EXPORT_OPERATION_LOGS,
    PERM_EXPORT_USERS,
    PERM_LOG_READ,
    PERM_USER_READ,
)
from app.core.request_context import current_request_id, monotonic_ms
from app.db.base import get_db
from app.services.admin import exports as exports_service
from app.services.admin import logs as logs_service

router = APIRouter(prefix="/admin", tags=["管理端-导出"])

FilterText = Annotated[str | None, Query(max_length=50)]
TimeValue = Annotated[str | None, Query()]

EventType = Annotated[Literal[tuple(EVENT_TYPES)], Query()]  # type: ignore[valid-type]
TargetType = Annotated[Literal[tuple(TARGET_TYPES)], Query()]  # type: ignore[valid-type]
LogResult = Annotated[Literal[tuple(LOG_RESULTS)], Query()]  # type: ignore[valid-type]
FailureType = Annotated[  # type: ignore[valid-type]
    Literal[tuple(LOGIN_FAILURE_TYPES)], Query()
]


def _csv_response(payload: bytes, filename: str) -> Response:
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/exports/users")
def export_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permissions(PERM_EXPORT_USERS, PERM_USER_READ)
    ),
    username: FilterText = None,
    nickname: FilterText = None,
    role: Annotated[Literal["admin", "student"] | None, Query()] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
) -> Response:
    payload, filename, _ = exports_service.export_users(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        username=username,
        nickname=nickname,
        role=role,
        status=status,
    )
    return _csv_response(payload, filename)


@router.get("/exports/login-logs")
def export_login_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permissions(PERM_EXPORT_LOGIN_LOGS, PERM_LOG_READ)
    ),
    username: FilterText = None,
    result: LogResult = None,
    failure_type: FailureType = None,
    ip: FilterText = None,
    start_at: TimeValue = None,
    end_at: TimeValue = None,
) -> Response:
    window = logs_service.resolve_time_window(start_at, end_at)
    payload, filename, _ = exports_service.export_login_logs(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        start=window.start,
        end=window.end,
        username=username,
        result=result,
        failure_type=failure_type,
        filter_ip=logs_service.validate_ip(ip),
    )
    return _csv_response(payload, filename)


@router.get("/exports/operation-logs")
def export_operation_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permissions(PERM_EXPORT_OPERATION_LOGS, PERM_LOG_READ)
    ),
    actor_username: FilterText = None,
    event_type: EventType = None,
    result: LogResult = None,
    target_type: TargetType = None,
    start_at: TimeValue = None,
    end_at: TimeValue = None,
) -> Response:
    window = logs_service.resolve_time_window(start_at, end_at)
    payload, filename, _ = exports_service.export_operation_logs(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        start=window.start,
        end=window.end,
        actor_username=actor_username,
        event_type=event_type,
        result=result,
        target_type=target_type,
    )
    return _csv_response(payload, filename)
