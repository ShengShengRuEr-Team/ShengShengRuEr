"""个人中心路由：查看本人、改昵称、旧密码校验改密（主文档 §4.3）。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.admin_platform.common import (
    request_ip,
    request_user_agent,
)
from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import (
    PERM_SELF_PASSWORD,
    PERM_SELF_READ,
    PERM_SELF_UPDATE,
)
from app.core.errors import not_found, ok
from app.core.request_context import current_request_id, monotonic_ms
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_admin.users import (
    SelfPasswordChangeRequest,
    SelfPasswordResult,
    UserOut,
    UserProfileUpdateRequest,
)
from app.services.admin import accounts

router = APIRouter(prefix="/admin", tags=["管理端-本人"])


@router.get("/me", response_model=ApiResponse[UserOut])
def get_me(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_SELF_READ)),
) -> dict:
    record = accounts.get_user(db, current_user.id)
    if record is None:  # pragma: no cover - 认证已确认用户存在
        raise not_found("用户不存在")
    return ok(UserOut(**record.__dict__))


@router.patch("/me", response_model=ApiResponse[UserOut])
def update_me(
    payload: UserProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_SELF_UPDATE)),
) -> dict:
    record = accounts.update_nickname(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        target_id=current_user.id,
        nickname=payload.nickname,
    )
    return ok(UserOut(**record.__dict__), "更新成功")


@router.post("/me/password", response_model=ApiResponse[SelfPasswordResult])
def change_my_password(
    payload: SelfPasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(
        require_permission(PERM_SELF_PASSWORD)
    ),
) -> dict:
    result = accounts.change_own_password(
        db,
        actor=current_user,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    return ok(SelfPasswordResult(**result), "密码已修改，请重新登录")
