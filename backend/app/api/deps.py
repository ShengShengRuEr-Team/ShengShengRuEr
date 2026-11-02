"""认证与鉴权依赖。

- `get_current_user`：解析 token，任一环节失败返回 401
- `require_admin`：在 401 判定通过后判断角色，不含管理员则返回 403
"""

from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import forbidden, unauthorized
from app.core.permissions import ROLE_ADMIN
from app.core.security import (
    TokenClaims,
    TokenValidationError,
    decode_access_token,
)
from app.db.base import get_db
from app.db.models import Role, TokenRevocation, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    nickname: str
    roles: tuple[str, ...]
    jti: str
    expires_at: datetime

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles


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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """解析 token 并确认账号有效；任一环节失败返回 401。"""

    claims = _claims_from_credentials(credentials, settings)

    revoked = db.scalar(
        select(TokenRevocation.id).where(TokenRevocation.jti == claims.jti)
    )
    if revoked is not None:
        raise unauthorized()

    user = db.get(User, claims.user_id)
    if user is None or user.status != "active":
        raise unauthorized()
    if user.username != claims.username:
        raise unauthorized()

    roles = _load_roles(db, user.id)
    return CurrentUser(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        roles=roles,
        jti=claims.jti,
        expires_at=claims.expires_at,
    )


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """先完成 401 判定，再判定角色；不含管理员则返回 403。"""

    if not current_user.is_admin:
        raise forbidden("管理员")
    return current_user
