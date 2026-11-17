"""认证接口：登录、退出、获取当前用户信息。

审计接入（T02）：
- LOGIN_SUCCEEDED 与登录成功同一事务提交，审计写不了就不发 token、不留 session；
- UNKNOWN_ACCOUNT / BAD_PASSWORD / DISABLED 用独立 Session 记录，失败审计
  不覆盖原始 401；LOGOUT 与退出撤销同事务。

存量 token 失效说明：JWT 新增 `auth_version` 与 `session_id` 两个必需声明，
旧 token 缺少它们，解码即判无效（401）。部署后所有在线用户需重新登录，
这是本期预期行为，不是故障。
"""

import ipaddress
import logging
import uuid
from typing import Any, NoReturn

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
from app.core.request_context import (
    current_request_id,
    elapsed_ms,
    monotonic_ms,
    new_event_id,
)
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    utc_now,
    verify_password,
)
from app.db.base import get_db
from app.db.models import Role, TokenRevocation, User, UserRole
from app.db.models_admin import AuthSession
from app.schemas import (
    ApiResponse,
    GetInfoData,
    LoginData,
    LoginRequest,
    UserInfo,
)
from app.services.admin import audit

logger = logging.getLogger(__name__)

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


def _role_snapshot(roles: tuple[str, ...] | list[str]) -> str | None:
    role_set = set(roles)
    if "admin" in role_set:
        return "admin"
    if "student" in role_set:
        return "student"
    return None


def _load_roles(db: Session, user_id: int) -> tuple[str, ...]:
    role_keys = db.scalars(
        select(Role.role_key)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.role_key)
    ).all()
    return tuple(role_keys)


def _raise_login_failure(
    *,
    db: Session,
    failure_type: str,
    event_id: uuid.UUID,
    request_id: uuid.UUID,
    username_attempted: str,
    actor_user_id: int | None,
    actor_name: str,
    role_snapshot: str | None,
    ip: str | None,
    user_agent: str,
    started_at: float,
) -> NoReturn:
    """独立事务记录失败事件，然后抛统一 401；审计异常不覆盖原错误。

    先回滚业务 Session：失败路径不再需要它的读快照，否则持锁的 users 行
    会阻塞独立审计事务对同一行的外键检查（自死锁）。
    """

    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        logger.warning("登录失败前回滚业务事务异常", exc_info=True)

    event = audit.AuditEvent(
        event_type=audit.EVENT_LOGIN_FAILED,
        result=audit.RESULT_FAILURE,
        event_id=event_id,
        request_id=request_id,
        actor_user_id=actor_user_id,
        actor_name=actor_name,
        role_snapshot=role_snapshot,
        reason_code=failure_type,
        summary_values={"failure_type": failure_type},
        ip=ip,
        user_agent=user_agent,
        duration_ms=elapsed_ms(started_at),
        username_attempted=username_attempted,
    )
    try:
        audit.persist_login_failure(event)
    except Exception:  # noqa: BLE001 - 失败审计不得覆盖原始 401
        logger.exception(
            "登录失败审计写入异常 event_id=%s request_id=%s",
            event_id,
            request_id,
        )
    raise unauthorized("用户名或密码错误")


@router.post("/login", response_model=ApiResponse[LoginData])
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    started_at = monotonic_ms()
    request_id = current_request_id()
    event_id = new_event_id()
    client_ip = _client_ip(request)
    user_agent = _user_agent(request)
    username = payload.username.strip()

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        # 用户不存在时也跑一次 bcrypt，抹平与"密码错误"的响应时间差。
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        _raise_login_failure(
            db=db,
            failure_type=audit.FAILURE_UNKNOWN_ACCOUNT,
            event_id=event_id,
            request_id=request_id,
            username_attempted=username,
            actor_user_id=None,
            actor_name="",
            role_snapshot=None,
            ip=client_ip,
            user_agent=user_agent,
            started_at=started_at,
        )

    roles = _load_roles(db, user.id)

    # 锁外先算一次 bcrypt，缩短持锁时间；锁内必须按最新行重新校验。
    if not verify_password(payload.password, user.password_hash):
        _raise_login_failure(
            db=db,
            failure_type=audit.FAILURE_BAD_PASSWORD,
            event_id=event_id,
            request_id=request_id,
            username_attempted=username,
            actor_user_id=user.id,
            actor_name=user.username,
            role_snapshot=_role_snapshot(roles),
            ip=client_ip,
            user_agent=user_agent,
            started_at=started_at,
        )

    locked = db.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if locked is None or locked.status != "active":
        _raise_login_failure(
            db=db,
            failure_type=audit.FAILURE_DISABLED,
            event_id=event_id,
            request_id=request_id,
            username_attempted=username,
            actor_user_id=user.id,
            actor_name=user.username,
            role_snapshot=_role_snapshot(roles),
            ip=client_ip,
            user_agent=user_agent,
            started_at=started_at,
        )
    if not verify_password(payload.password, locked.password_hash):
        _raise_login_failure(
            db=db,
            failure_type=audit.FAILURE_BAD_PASSWORD,
            event_id=event_id,
            request_id=request_id,
            username_attempted=username,
            actor_user_id=locked.id,
            actor_name=locked.username,
            role_snapshot=_role_snapshot(roles),
            ip=client_ip,
            user_agent=user_agent,
            started_at=started_at,
        )

    issued_at = utc_now()
    session_id = uuid.uuid4()
    token, claims = create_access_token(
        user_id=locked.id,
        username=locked.username,
        auth_version=locked.auth_version,
        session_id=session_id,
        settings=settings,
    )

    # 会话与 LOGIN_SUCCEEDED 同一事务：commit 成功才返回 token。
    db.add(
        AuthSession(
            id=session_id,
            user_id=locked.id,
            jti_hash=session_fingerprint(claims.jti),
            auth_version=locked.auth_version,
            issued_at=issued_at,
            expires_at=claims.expires_at,
            last_activity_at=issued_at,
            ip=client_ip,
            user_agent=user_agent,
        )
    )
    audit.enqueue_login_event(
        db,
        audit.AuditEvent(
            event_type=audit.EVENT_LOGIN_SUCCEEDED,
            result=audit.RESULT_SUCCESS,
            event_id=event_id,
            request_id=request_id,
            actor_user_id=locked.id,
            actor_name=locked.username,
            role_snapshot=_role_snapshot(roles),
            summary_values={
                "session_id": str(session_id),
                "auth_version": locked.auth_version,
            },
            ip=client_ip,
            user_agent=user_agent,
            duration_ms=elapsed_ms(started_at),
            username_attempted=locked.username,
        ),
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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    started_at = monotonic_ms()

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

    # 3) LOGOUT 与撤销同事务；审计写不了则整体回滚并 500。
    audit.enqueue_audit_event(
        db,
        audit.AuditEvent(
            event_type=audit.EVENT_LOGOUT,
            result=audit.RESULT_SUCCESS,
            event_id=new_event_id(),
            request_id=current_request_id(),
            actor_user_id=current_user.id,
            actor_name=current_user.username,
            role_snapshot=_role_snapshot(current_user.roles),
            summary_values={"session_id": str(current_user.session_id)},
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            duration_ms=elapsed_ms(started_at),
        ),
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
