"""认证与鉴权依赖。

- `get_current_user`：解析 token 并核对旧撤销表、用户状态/版本、会话状态，
  任一环节失败返回 401；数据库异常不包装成 401，交给全局 500 处理。
- `require_admin`：在 401 判定通过后判断角色，不含管理员则返回 403。
- `require_student`：在 401 判定通过后判断角色；管理员优先 403，无学生角色 403。
- `require_permission(code)`：401 → 403 角色 → 固定权限码集合检查。

认证使用独立短 Session：只读校验完成后立即关闭，不提交业务 Session。
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.admin_permissions import has_permission
from app.core.config import Settings, get_settings
from app.core.errors import forbidden, permission_denied, unauthorized
from app.core.permissions import ROLE_ADMIN, ROLE_STUDENT
from app.core.security import (
    TokenClaims,
    TokenValidationError,
    decode_access_token,
    utc_now,
)
from app.db.base import SessionLocal
from app.db.models import Role, TokenRevocation, User, UserRole
from app.db.models_admin import AuthSession

bearer_scheme = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)

#: 活动节流：最近活动时间最多每 30 秒刷新一次，且绝不延长 expires_at。
ACTIVITY_MIN_INTERVAL_SECONDS = 30
ACTIVITY_EXPLICIT_HEADER = "x-admin-activity"

#: 监控、首页、日志、私有 schema 与探针不计入活动（主文档 §6.3）。
EXCLUDED_ACTIVITY_PREFIXES: tuple[str, ...] = (
    "/api/v1/admin/monitor",
    "/api/v1/admin/dashboard",
    "/api/v1/admin/logs",
    "/api/v1/admin/openapi.json",
    "/health",
)

#: 管理列表页的自动刷新默认不保活，只有显式标记才刷新活动时间。
EXPLICIT_ONLY_ACTIVITY_PREFIXES: tuple[str, ...] = ("/api/v1/admin/users",)


def _activity_allowed(request: Request) -> bool:
    path = request.url.path
    if any(path.startswith(prefix) for prefix in EXCLUDED_ACTIVITY_PREFIXES):
        return False
    explicit = (
        request.headers.get(ACTIVITY_EXPLICIT_HEADER, "").strip().lower()
        == "explicit"
    )
    if request.method == "GET" and any(
        path.startswith(prefix) for prefix in EXPLICIT_ONLY_ACTIVITY_PREFIXES
    ):
        return explicit
    return True


def _touch_activity(session_id: uuid.UUID) -> None:
    """独立短事务做条件更新；失败只记 warning，不影响请求。"""

    now = utc_now()
    activity_db = None
    try:
        activity_db = SessionLocal()
        activity_db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.last_activity_at
                <= now - timedelta(seconds=ACTIVITY_MIN_INTERVAL_SECONDS),
            )
            .values(last_activity_at=now)
        )
        activity_db.commit()
    except Exception as exc:  # noqa: BLE001 - 活动写失败不得阻塞请求
        # 不输出异常正文：数据库错误可能带业务内容，日志只留固定文案与类型。
        logger.warning(
            "会话活动时间更新失败 error_type=%s", type(exc).__name__
        )
        if activity_db is not None:
            activity_db.rollback()
    finally:
        if activity_db is not None:
            activity_db.close()


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    nickname: str
    roles: tuple[str, ...]
    jti: str
    expires_at: datetime
    auth_version: int
    session_id: uuid.UUID

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles


def session_fingerprint(jti: str) -> str:
    """会话表只存 jti 的 SHA-256 指纹，小写十六进制。"""

    return sha256(jti.encode("utf-8")).hexdigest()


def _load_roles(db: Session, user_id: int) -> tuple[str, ...]:
    role_keys = db.scalars(
        select(Role.role_key)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.role_key)
    ).all()
    return tuple(role_keys)


def _claims_from_credentials(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> TokenClaims:
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    if credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        return decode_access_token(credentials.credentials, settings)
    except TokenValidationError as exc:
        raise unauthorized() from exc


def resolve_current_user(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> CurrentUser:
    """解析 token 并确认账号与会话有效；任一环节失败返回 401。

    供路由依赖与文档调试中间件共用，保证两处鉴权语义完全一致。
    """

    claims = _claims_from_credentials(credentials, settings)

    # 独立短事务：只读校验，不参与业务事务，也不提交业务 Session。
    auth_db = SessionLocal()
    try:
        revoked = auth_db.scalar(
            select(TokenRevocation.id).where(TokenRevocation.jti == claims.jti)
        )
        if revoked is not None:
            raise unauthorized()

        # 账号行 FOR SHARE：确认状态/用户名/版本时不被并发改密或停用插队。
        user = auth_db.scalar(
            select(User).where(User.id == claims.user_id).with_for_update(read=True)
        )
        if user is None or user.status != "active":
            raise unauthorized()
        if user.username != claims.username:
            raise unauthorized()
        if user.auth_version != claims.auth_version:
            raise unauthorized()

        session = auth_db.get(AuthSession, claims.session_id)
        if session is None or session.user_id != user.id:
            raise unauthorized()
        if session.jti_hash != session_fingerprint(claims.jti):
            raise unauthorized()
        if session.auth_version != claims.auth_version:
            raise unauthorized()
        if session.revoked_at is not None:
            raise unauthorized()
        if session.expires_at <= utc_now():
            raise unauthorized()

        roles = _load_roles(auth_db, user.id)
    finally:
        auth_db.close()

    return CurrentUser(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        roles=roles,
        jti=claims.jti,
        expires_at=claims.expires_at,
        auth_version=claims.auth_version,
        session_id=claims.session_id,
    )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """路由依赖：鉴权通过后按 §6.3 节流刷新活动时间。"""

    current_user = resolve_current_user(credentials, settings)
    if _activity_allowed(request):
        _touch_activity(current_user.session_id)
    return current_user


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """先完成 401 判定，再判定角色；不含管理员则返回 403。"""

    if not current_user.is_admin:
        raise forbidden("管理员")
    return current_user


def require_student(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """先完成 401 判定，再判定角色：管理员优先 403，无学生角色 403。"""

    if current_user.is_admin:
        raise forbidden("学生")
    if ROLE_STUDENT not in current_user.roles:
        raise forbidden("学生")
    return current_user


def require_permission(code: str):
    """构造依赖：401 判定 → 管理员 403 判定 → 固定权限码检查。

    返回值与 `require_admin` 相同，均为同一个 `CurrentUser`。
    """

    def dependency(
        current_user: CurrentUser = Depends(require_admin),
    ) -> CurrentUser:
        if not has_permission(current_user.roles, code):
            raise permission_denied()
        return current_user

    return dependency


def require_permissions(*codes: str):
    """同时校验多个固定权限码；缺少任一即 403（顺序仍是 401 → 403 角色 → 403 权限）。"""

    def dependency(
        current_user: CurrentUser = Depends(require_admin),
    ) -> CurrentUser:
        for code in codes:
            if not has_permission(current_user.roles, code):
                raise permission_denied()
        return current_user

    return dependency
