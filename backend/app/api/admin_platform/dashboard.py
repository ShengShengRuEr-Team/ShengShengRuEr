"""管理端首页汇总路由（主文档 §9.5）。"""

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import PERM_DASHBOARD_READ
from app.core.errors import ok
from app.schemas import ApiResponse
from app.schemas_admin.dashboard import DashboardData
from app.services.admin import dashboard as dashboard_service

router = APIRouter(prefix="/admin", tags=["管理端-首页"])


@router.get("/dashboard", response_model=ApiResponse[DashboardData])
def get_dashboard(
    current_user: CurrentUser = Depends(require_permission(PERM_DASHBOARD_READ)),
) -> dict:
    """读取首页汇总；只读一致快照 + 进程内 TTL 缓存。"""

    return ok(dashboard_service.build_dashboard())
