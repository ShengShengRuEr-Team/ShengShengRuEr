"""用户管理路由：列表/详情/创建/编辑/启停/重置密码（主文档 §4.3）。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.admin_platform.common import (
    parse_positive_int,
    validate_page_size,
    request_ip,
    request_user_agent,
)
from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import (
    PERM_USER_CREATE,
    PERM_USER_READ,
    PERM_USER_RESET_PASSWORD,
    PERM_USER_STATUS,
    PERM_USER_UPDATE,
)
from app.core.errors import not_found, ok
from app.core.request_context import current_request_id, monotonic_ms
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_admin.users import (
    PasswordResetResult,
    ResetPasswordRequest,
    UserCreateRequest,
    UserOut,
    UserPage,
    UserProfileUpdateRequest,
    UserStatusRequest,
    UserStatusResult,
)
from app.services.admin import accounts

router = APIRouter(prefix="/admin", tags=["管理端-用户"])

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query()]
FilterText = Annotated[str | None, Query(max_length=50)]


def _as_out(record) -> UserOut:
    return UserOut(**record.__dict__)


@router.get("/users", response_model=ApiResponse[UserPage])
def list_users(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_USER_READ)),
    username: FilterText = None,
    nickname: FilterText = None,
    role: Annotated[Literal["admin", "student"] | None, Query()] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> dict:
    validate_page_size(page_size)
    records, total = accounts.list_users(
        db,
        username=username,
        nickname=nickname,
        role=role,
        status=status,
        page=page,
        page_size=page_size,
    )
    page_data = UserPage(
        items=[_as_out(record) for record in records],
        total=total,
        page=page,
        page_size=page_size,
    )
    return ok(page_data)


@router.get("/users/{user_id}", response_model=ApiResponse[UserOut])
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_USER_READ)),
) -> dict:
    target_id = parse_positive_int(user_id)
    record = accounts.get_user(db, target_id)
    if record is None:
        raise not_found("用户不存在")
    return ok(_as_out(record))


@router.post("/users", response_model=ApiResponse[UserOut])
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_USER_CREATE)),
) -> dict:
    record = accounts.create_user(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        role=payload.role,
    )
    return ok(_as_out(record), "创建成功")


@router.patch("/users/{user_id}", response_model=ApiResponse[UserOut])
def update_user(
    user_id: str,
    payload: UserProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_USER_UPDATE)),
) -> dict:
    target_id = parse_positive_int(user_id)
    record = accounts.update_nickname(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        target_id=target_id,
        nickname=payload.nickname,
    )
    return ok(_as_out(record), "更新成功")


@router.post(
    "/users/{user_id}/status", response_model=ApiResponse[UserStatusResult]
)
def change_user_status(
    user_id: str,
    payload: UserStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_USER_STATUS)),
) -> dict:
    target_id = parse_positive_int(user_id)
    result = accounts.change_status(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        target_id=target_id,
        status=payload.status,
        reason=payload.reason,
    )
    return ok(UserStatusResult(**result), "操作成功")


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ApiResponse[PasswordResetResult],
)
def reset_user_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permission(PERM_USER_RESET_PASSWORD)
    ),
) -> dict:
    target_id = parse_positive_int(user_id)
    result = accounts.reset_password(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        target_id=target_id,
        new_password=payload.new_password,
        reason=payload.reason,
    )
    return ok(PasswordResetResult(**result), "密码已重置")
