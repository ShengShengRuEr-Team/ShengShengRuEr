"""认证接口：登录、退出、获取当前用户信息。

本期登录只创建持久会话（auth_sessions），不写审计事件；
LOGIN_SUCCEEDED / UNKNOWN_ACCOUNT / BAD_PASSWORD / DISABLED 四类
事件在 T02 建表后接入本文件。

存量 token 失效说明：JWT 新增 `auth_version` 与 `session_id` 两个必需声明，
旧 token 缺少它们，解码即判无效（401）。部署后所有在线用户需重新登录，
这是本期预期行为，不是故障。
"""

import ipaddress
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_current_user,
    session_fingerprint,
)
from app.core.admin_permissions import permission_codes
from app.core.config import Settings, get_settings
from app.core.errors import ok, unauthorized
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    utc_now,
    verify_password,
)
from app.db.base import get_db
from app.db.models import TokenRevocation, User
from app.db.models_admin import AuthSession
from app.schemas import (
    ApiResponse,
    GetInfoData,
    LoginData,
    LoginRequest,
    UserInfo,
)

router = APIRouter(tags=["认证"])

MAX_USER_AGENT_LENGTH = 256


def _client_ip(request: Request) -> str | None:
    """取原始 TCP 对端地址；不可解析时不写库，绝不用头推断。

    代理信任链与审计用 IP 属 T08/T09，本期只记录直连事实。
    """

    client = request.client
    if client is None or not client.host:
        return None
    try:
        return str(ipaddress.ip_address(client.host))
    except ValueError:
        return None


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:MAX_USER_AGENT_LENGTH]


@router.post("/login", response_model=ApiResponse[LoginData])
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    username = payload.username.strip()
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        # 用户不存在时也跑一次 bcrypt，抹平与"密码错误"的响应时间差。
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise unauthorized("用户名或密码错误")

    # 锁外先算一次 bcrypt，缩短持锁时间；锁内必须按最新行重新校验。
    if not verify_password(payload.password, user.password_hash):
        raise unauthorized("用户名或密码错误")

    locked = db.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if locked is None or locked.status != "active":
        raise unauthorized("用户名或密码错误")
    if not verify_password(payload.password, locked.password_hash):
        raise unauthorized("用户名或密码错误")

    issued_at = utc_now()
    session_id = uuid.uuid4()
    token, claims = create_access_token(
        user_id=locked.id,
        username=locked.username,
        auth_version=locked.auth_version,
        session_id=session_id,
        settings=settings,
    )

    # 会话与 token 同批落库：commit 成功才返回 token。
    db.add(
        AuthSession(
            id=session_id,
            user_id=locked.id,
            jti_hash=session_fingerprint(claims.jti),
            auth_version=locked.auth_version,
            issued_at=issued_at,
            expires_at=claims.expires_at,
            last_activity_at=issued_at,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
    )
    db.commit()

    return ok(
        LoginData(
            token=token,
            token_type="Bearer",
            expires_in=settings.access_token_expire_seconds,
        ),
        "登录成功",
    )


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # 顺带清理已过期记录，避免失效表无限增长。
    db.execute(
        delete(TokenRevocation).where(TokenRevocation.expires_at < utc_now())
    )

    # 1) 撤销当前持久会话：只改这一条，不增 auth_version。
    session = db.get(AuthSession, current_user.session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = utc_now()
        session.revoke_reason = "logout"

    # 2) 幂等写旧撤销表，保持既有 token 失效语义。
    already_revoked = db.scalar(
        select(TokenRevocation.id).where(TokenRevocation.jti == current_user.jti)
    )
    if already_revoked is None:
        db.add(
            TokenRevocation(
                jti=current_user.jti,
                user_id=current_user.id,
                expires_at=current_user.expires_at,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # 只有确认冲突确实来自同一 jti 的并发撤销时才按幂等成功处理。
        confirmed = db.scalar(
            select(TokenRevocation.id).where(
                TokenRevocation.jti == current_user.jti
            )
        )
        if confirmed is None:
            raise
    return ok(None, "退出成功")


@router.get("/getInfo", response_model=ApiResponse[GetInfoData])
def get_info(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return ok(
        GetInfoData(
            user=UserInfo(
                user_id=current_user.id,
                username=current_user.username,
                nickname=current_user.nickname,
            ),
            roles=list(current_user.roles),
            is_admin=current_user.is_admin,
            permissions=list(permission_codes(current_user.roles)),
        )
    )
