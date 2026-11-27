"""FastAPI 应用入口与全局装配。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    admin,
    admin_library,
    admin_listening_papers,
    admin_processing,
    admin_processing_workflows,
    attempt_status,
    attempts,
    auth,
    listening_papers,
    skill_error_query,
    wrong_answers,
)
from app.core.errors import AppError
from app.module3.contracts import ProcessingError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    from app.services.processing.uploads import recover_uploads

    async def recover():
        while True:
            try:
                await asyncio.to_thread(recover_uploads)
            except Exception:
                logger.warning("上传恢复扫描暂不可用", exc_info=True)
            await asyncio.sleep(15)

    recovery = asyncio.create_task(recover())
    try:
        yield
    finally:
        recovery.cancel()
        try:
            await recovery
        except asyncio.CancelledError:
            pass


app = FastAPI(
    lifespan=lifespan,
    title="英语四六级听力错题与推荐系统 - 模块一",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def notebook_cache_control(request: Request, call_next):
    response = await call_next(request)
    if wrong_answers.is_notebook_path(request.url.path):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "msg": exc.msg,
            "data": None,
            **({"error_code": exc.error_code} if exc.error_code else {}),
            **({"context": exc.context} if exc.context else {}),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # 不回显请求值，避免 422 错误信息泄露敏感字段。
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": "请求参数校验失败", "data": None},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": detail, "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s", exc)
    headers = (
        {"Cache-Control": "no-store"}
        if wrong_answers.is_notebook_path(request.url.path)
        else None
    )
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误", "data": None},
        headers=headers,
    )


app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(listening_papers.router, prefix="/api/v1")
app.include_router(admin_listening_papers.router, prefix="/api/v1")
app.include_router(admin_library.router, prefix="/api/v1")
app.include_router(attempts.router, prefix="/api/v1")
app.include_router(attempt_status.router, prefix="/api/v1")
app.include_router(wrong_answers.router, prefix="/api/v1")
app.include_router(admin_processing.router, prefix="/api/v1")
app.include_router(admin_processing_workflows.router, prefix="/api/v1")
app.include_router(skill_error_query.router, prefix="/api/v1")


@app.exception_handler(ProcessingError)
async def processing_error_handler(request: Request, exc: ProcessingError):
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "msg": str(exc),
            "data": {"issue_code": exc.code},
        },
    )


@app.exception_handler(OperationalError)
async def database_error_handler(request: Request, exc: OperationalError):
    return JSONResponse(
        status_code=503,
        content={
            "code": 503,
            "msg": "数据库暂不可用",
            "data": None,
        },
    )
