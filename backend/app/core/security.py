"""密码哈希与 JWT 工具。"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings


class TokenValidationError(Exception):
    """JWT 缺失、篡改、过期或 claims 不完整。"""


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    username: str
    jti: str
    expires_at: datetime


def hash_password(plain_password: str) -> str:
    """使用 bcrypt 生成口令哈希。"""

    return bcrypt.hashpw(
        plain_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验口令；哈希损坏时返回 False，不抛 500。"""

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# 用户不存在时也执行一次 bcrypt 校验，避免通过响应时间差枚举用户名。
# 该哈希不参与任何账号认证，只用于消耗与真实校验一致的计算时间。
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-only")


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    user_id: int,
    username: str,
    settings: Settings,
) -> tuple[str, TokenClaims]:
    """签发 HS256 access token，返回 token 与解析后的 claims。"""

    issued_at = utc_now()
    expires_at = issued_at + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    claims = TokenClaims(
        user_id=user_id,
        username=username,
        jti=uuid.uuid4().hex,
        expires_at=expires_at,
    )
    payload = {
        "sub": str(user_id),
        "username": username,
        "jti": claims.jti,
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, claims


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    """校验签名、时效与全部必需 claims。"""

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "username", "jti", "type", "iat", "exp"],
            },
        )
    except jwt.InvalidTokenError as exc:
        raise TokenValidationError("token 无效或已过期") from exc

    subject = payload.get("sub")
    username = payload.get("username")
    jti = payload.get("jti")
    token_type = payload.get("type")
    expires_at = payload.get("exp")

    if not isinstance(subject, str) or not subject.strip():
        raise TokenValidationError("token 缺少 sub")
    if not isinstance(username, str) or not username.strip():
        raise TokenValidationError("token 缺少 username")
    if not isinstance(jti, str) or not jti.strip():
        raise TokenValidationError("token 缺少 jti")
    if token_type != "access":
        raise TokenValidationError("token 类型错误")
    if not isinstance(expires_at, (int, float)):
        raise TokenValidationError("token 缺少 exp")

    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise TokenValidationError("token 的 sub 不是合法用户 ID") from exc

    return TokenClaims(
        user_id=user_id,
        username=username,
        jti=jti,
        expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
    )
