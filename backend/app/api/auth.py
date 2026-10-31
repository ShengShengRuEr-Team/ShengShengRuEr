"""认证接口：登录、退出、获取当前用户信息。"""

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
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
from app.schemas import (
    ApiResponse,
    GetInfoData,
    LoginData,
    LoginRequest,
    UserInfo,
)

router = APIRouter(tags=["认证"])


@router.post("/login", response_model=ApiResponse[LoginData])
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None:
        # 用户不存在时也跑一次 bcrypt，抹平与"密码错误"的响应时间差。
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise unauthorized("用户名或密码错误")

    if not verify_password(payload.password, user.password_hash):
        raise unauthorized("用户名或密码错误")
    if user.status != "active":
        raise unauthorized("用户名或密码错误")

    token, _ = create_access_token(
        user_id=user.id,
        username=user.username,
        settings=settings,
    )
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
) -> dict:
    # 顺带清理已过期记录，避免失效表无限增长。
    db.execute(delete(TokenRevocation).where(TokenRevocation.expires_at < utc_now()))
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
        # 重复或并发退出按幂等处理。
        db.rollback()
    return ok(None, "退出成功")


@router.get("/getInfo", response_model=ApiResponse[GetInfoData])
def get_info(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    return ok(
        GetInfoData(
            user=UserInfo(
                user_id=current_user.id,
                username=current_user.username,
                nickname=current_user.nickname,
            ),
            roles=list(current_user.roles),
            is_admin=current_user.is_admin,
        )
    )
