"""FastAPI 应用入口与全局装配。"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    admin,
    admin_listening_papers,
    attempt_status,
    attempts,
    auth,
    listening_papers,
)
from app.api.admin_platform import (
    dashboard as admin_dashboard,
    docs as admin_docs,
    exports as admin_exports,
    logs as admin_logs,
    me,
    sessions as admin_sessions,
    users as admin_users,
)
from app.core.errors import AppError
from app.core.docs_debug_middleware import DocsDebugMiddleware
from app.core.request_context import (
    bind_request_id,
    new_request_id,
    reset_request_id,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="英语四六级听力错题与推荐系统 - 模块一",
    version="1.0.0",
    # 公开文档入口全局关闭（含开发环境），替代入口为受保护的 /admin/openapi.json。
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# 必须在 request_id 中间件之前加入，使其位于其内层（request_id 为最外层）。
app.add_middleware(DocsDebugMiddleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """每个请求生成 request_id，成功与业务失败都回写 X-Request-ID。"""

    request_id = new_request_id()
    request.state.request_id = request_id
    token = bind_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers["X-Request-ID"] = str(request_id)
    return response


def _request_id_headers(request: Request) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        return {}
    return {"X-Request-ID": str(request_id)}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.msg, "data": None},
        headers={**(exc.headers or {}), **_request_id_headers(request)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # 不回显请求值，避免 422 错误信息泄露敏感字段。
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": "请求参数校验失败", "data": None},
        headers=_request_id_headers(request),
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": detail, "data": None},
        headers=_request_id_headers(request),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s", exc)
    request_id = getattr(request.state, "request_id", None) or uuid.uuid4()
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误", "data": None},
        headers={"X-Request-ID": str(request_id)},
    )


app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(admin_users.router, prefix="/api/v1")
app.include_router(me.router, prefix="/api/v1")
app.include_router(admin_sessions.router, prefix="/api/v1")
app.include_router(admin_logs.router, prefix="/api/v1")
app.include_router(admin_exports.router, prefix="/api/v1")
app.include_router(admin_dashboard.router, prefix="/api/v1")
app.include_router(admin_docs.router, prefix="/api/v1")
app.include_router(listening_papers.router, prefix="/api/v1")
app.include_router(admin_listening_papers.router, prefix="/api/v1")
app.include_router(attempts.router, prefix="/api/v1")
app.include_router(attempt_status.router, prefix="/api/v1")
