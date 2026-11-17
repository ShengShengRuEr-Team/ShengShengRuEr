"""受限 GET 调试的前置校验与审计（主文档 §8.2）。

只有带 `X-Admin-Docs-Debug: 1` 的 `/api/v1/admin/*` 请求进入本中间件：
- 先按共享认证判定 401/403；
- 再校验 `admin:docs:debug`、GET、白名单模板与目标权限；
- 通过后**仍交给原路由**（不绕过目标路由鉴权），响应完成后写 DOC_GET_DEBUG；
- 无标记请求零改动，直接透传。
"""

import json
import time

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from app.api.deps import resolve_current_user
from app.core.admin_permissions import PERM_DOCS_DEBUG, has_permission
from app.core.config import get_settings
from app.core.docs_debug import (
    DEBUG_HEADER,
    DEBUG_HEADER_VALUE,
    resolve_debug_route,
)
from app.core.errors import AppError, bad_request, forbidden, permission_denied, unauthorized
from app.core.request_context import current_request_id
from app.db.base import SessionLocal
from app.services.admin import audit
from fastapi.security import HTTPAuthorizationCredentials


class DocsDebugMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        claimed = headers.get(DEBUG_HEADER)
        path = scope.get("path", "")
        if claimed is None or not path.startswith("/api/v1/admin"):
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        request_id = current_request_id()
        try:
            user, path_template = await run_in_threadpool(
                self._precheck, scope, headers, claimed
            )
        except AppError as exc:
            await self._send_error(send, exc)
            return

        status_code = 500
        buffered: list[dict] = []

        async def capture(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            buffered.append(message)

        await self.app(scope, receive, capture)

        try:
            await run_in_threadpool(
                self._audit,
                user,
                path_template,
                status_code,
                started_at,
                request_id,
            )
        except Exception:  # noqa: BLE001 - 审计失败不得伪装成功
            await self._send_error(send, AppError(500, "服务器内部错误"))
            return

        for message in buffered:
            await send(message)

    # -- 同步部分（在线程池执行，避免阻塞事件循环） ----------------------

    def _precheck(self, scope, headers: Headers, claimed: str):
        if claimed.strip() != DEBUG_HEADER_VALUE:
            raise bad_request("调试标记非法")

        credentials = _credentials_from_headers(headers)
        user = resolve_current_user(credentials, get_settings())
        if not user.is_admin:
            raise forbidden("管理员")
        if not has_permission(user.roles, PERM_DOCS_DEBUG):
            raise permission_denied()

        method = scope.get("method", "")
        if method.upper() != "GET":
            raise bad_request("调试仅允许 GET 请求")

        # 用 raw_path 保留百分号编码，拒绝 %2F 等歧义绕过。
        raw_path = scope.get("raw_path")
        candidate = (
            raw_path.decode("latin-1")
            if raw_path
            else scope.get("path", "")
        )
        resolved = resolve_debug_route(method, candidate)
        if resolved is None:
            raise bad_request("路径不在调试白名单内")
        path_template, permission = resolved
        if not has_permission(user.roles, permission):
            raise permission_denied()
        return user, path_template

    def _audit(self, user, path_template, status_code, started_at, request_id) -> None:
        event = audit.AuditEvent(
            event_type=audit.EVENT_DOC_GET_DEBUG,
            result=audit.RESULT_SUCCESS if status_code < 400 else audit.RESULT_FAILURE,
            request_id=request_id,
            actor_user_id=user.id,
            actor_name=user.username,
            role_snapshot="admin" if user.is_admin else None,
            target_type="docs",
            target_id=path_template,
            summary_values={
                "method": "GET",
                "path_template": path_template,
                "status_code": status_code,
            },
            duration_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        )
        with SessionLocal() as db:
            db.add(event.audit_row())
            db.commit()

    async def _send_error(self, send, exc: AppError) -> None:
        body = json.dumps(
            {"code": exc.status_code, "msg": exc.msg, "data": None},
            ensure_ascii=False,
        ).encode("utf-8")
        headers = [(b"content-type", b"application/json; charset=utf-8")]
        for key, value in (exc.headers or {}).items():
            headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        await send(
            {
                "type": "http.response.start",
                "status": exc.status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})


def _credentials_from_headers(
    headers: Headers,
) -> HTTPAuthorizationCredentials | None:
    authorization = headers.get("authorization")
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or not parts[1].strip():
        raise unauthorized()
    return HTTPAuthorizationCredentials(scheme=parts[0], credentials=parts[1].strip())
