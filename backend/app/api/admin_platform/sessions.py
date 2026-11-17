"""在线会话路由：列表与单条强退（主文档 §6.3）。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.admin_platform.common import (
    parse_uuid,
    request_ip,
    request_user_agent,
)
from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import PERM_SESSION_READ, PERM_SESSION_REVOKE
from app.core.errors import ok
from app.core.request_context import current_request_id, monotonic_ms
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_admin.sessions import (
    SessionPage,
    SessionRevokeRequest,
    SessionRevokeResult,
)
from app.services.admin import sessions as sessions_service

router = APIRouter(prefix="/admin", tags=["管理端-在线会话"])

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[Literal[10, 20, 50, 100], Query()]
FilterText = Annotated[str | None, Query(max_length=50)]


@router.get("/monitor/sessions", response_model=ApiResponse[SessionPage])
def list_online_sessions(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_SESSION_READ)),
    username: FilterText = None,
    role: Annotated[Literal["admin", "student"] | None, Query()] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    page_data = sessions_service.list_sessions(
        db,
        viewer=current_user,
        username=username,
        role=role,
        page=page,
        page_size=page_size,
    )
    return ok(page_data)


@router.post(
    "/monitor/sessions/{session_id}/revoke",
    response_model=ApiResponse[SessionRevokeResult],
)
def revoke_session(
    session_id: str,
    payload: SessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permission(PERM_SESSION_REVOKE)
    ),
) -> dict:
    parsed_session_id = parse_uuid(session_id)
    result = sessions_service.revoke_session(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        session_id=parsed_session_id,
        reason=payload.reason,
    )
    return ok(SessionRevokeResult(**result), "会话已撤销")
