"""管理端占位接口：仅管理员可访问，用于验证角色鉴权与页面权限一致。"""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, require_admin
from app.core.errors import ok
from app.schemas import AdminOverviewData, ApiResponse

router = APIRouter(prefix="/admin", tags=["管理端"])


@router.get("/overview", response_model=ApiResponse[AdminOverviewData])
def admin_overview(
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """返回管理端首页占位信息。

    学生 token 调用返回 403，用于验证「页面隐藏与后端接口权限保持一致」。
    """

    display_name = current_user.nickname or current_user.username
    return ok(
        AdminOverviewData(
            role="admin",
            message=f"管理员 {display_name} 已进入管理端",
        )
    )
