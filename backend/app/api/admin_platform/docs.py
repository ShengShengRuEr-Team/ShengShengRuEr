"""私有接口文档路由（主文档 §8.1）。"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import PERM_DOCS_READ
from app.core.docs_debug import allowlist_document

router = APIRouter(prefix="/admin", tags=["管理端-接口文档"])


@router.get("/openapi.json", include_in_schema=False)
def protected_openapi(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PERM_DOCS_READ)),
) -> JSONResponse:
    """返回真实注册路由生成的 schema，原始 JSON、不套业务外壳、不缓存。"""

    schema = dict(request.app.openapi())
    schema["x-admin-debug-allowlist"] = allowlist_document()
    return JSONResponse(
        content=schema,
        headers={"Cache-Control": "no-store"},
    )
