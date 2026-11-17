"""审计日志路由：登录/操作日志列表与详情（主文档 §7.3）。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin_platform.common import parse_uuid, validate_page_size
from app.api.deps import CurrentUser, require_permission
from app.core.admin_enums import (
    EVENT_TYPES,
    LOG_RESULTS,
    LOGIN_FAILURE_TYPES,
    TARGET_TYPES,
)
from app.core.admin_permissions import PERM_LOG_READ
from app.core.errors import not_found, ok
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_admin.logs import (
    LoginLogOut,
    LoginLogPage,
    OperationLogOut,
    OperationLogPage,
)
from app.services.admin import logs as logs_service

router = APIRouter(prefix="/admin", tags=["管理端-日志"])

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query()]
FilterText = Annotated[str | None, Query(max_length=50)]
TimeValue = Annotated[str | None, Query()]

EventType = Annotated[Literal[tuple(EVENT_TYPES)], Query()]  # type: ignore[valid-type]
TargetType = Annotated[Literal[tuple(TARGET_TYPES)], Query()]  # type: ignore[valid-type]
LogResult = Annotated[Literal[tuple(LOG_RESULTS)], Query()]  # type: ignore[valid-type]
FailureType = Annotated[  # type: ignore[valid-type]
    Literal[tuple(LOGIN_FAILURE_TYPES)], Query()
]


@router.get("/logs/login", response_model=ApiResponse[LoginLogPage])
def list_login_logs(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_LOG_READ)),
    username: FilterText = None,
    result: LogResult = None,
    failure_type: FailureType = None,
    ip: FilterText = None,
    start_at: TimeValue = None,
    end_at: TimeValue = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    validate_page_size(page_size)
    window = logs_service.resolve_time_window(start_at, end_at)
    return ok(
        logs_service.list_login_logs(
            db,
            start=window.start,
            end=window.end,
            username=username,
            result=result,
            failure_type=failure_type,
            ip=logs_service.validate_ip(ip),
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/logs/login/{event_id}", response_model=ApiResponse[LoginLogOut]
)
def get_login_log(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_LOG_READ)),
) -> dict:
    parsed = parse_uuid(event_id)
    record = logs_service.get_login_log(db, parsed)
    if record is None:
        raise not_found("日志不存在")
    return ok(record)


@router.get("/logs/operation", response_model=ApiResponse[OperationLogPage])
def list_operation_logs(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_LOG_READ)),
    actor_username: FilterText = None,
    event_type: EventType = None,
    result: LogResult = None,
    target_type: TargetType = None,
    start_at: TimeValue = None,
    end_at: TimeValue = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    validate_page_size(page_size)
    window = logs_service.resolve_time_window(start_at, end_at)
    return ok(
        logs_service.list_operation_logs(
            db,
            start=window.start,
            end=window.end,
            actor_username=actor_username,
            event_type=event_type,
            result=result,
            target_type=target_type,
            page=page,
            page_size=page_size,
        )
    )


@router.get(
    "/logs/operation/{event_id}", response_model=ApiResponse[OperationLogOut]
)
def get_operation_log(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_LOG_READ)),
) -> dict:
    parsed = parse_uuid(event_id)
    record = logs_service.get_operation_log(db, parsed)
    if record is None:
        raise not_found("日志不存在")
    return ok(record)
