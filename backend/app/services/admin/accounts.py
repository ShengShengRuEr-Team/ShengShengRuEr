"""账户与本人资料服务：事务边界、锁顺序、密码规则与审计（主文档 §4.3/§6.2）。

所有写操作：认证依赖已判完 401/403；这里负责对象读取、业务规则、
同事务审计与失败独立审计。任何失败都不得覆盖原始 400/404。
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import AppError, bad_request, not_found
from app.core.permissions import ROLE_ADMIN
from app.core.security import hash_password, utc_now, verify_password
from app.db.models import Role, User, UserRole
from app.db.models_admin import AuthSession
from app.repositories.admin import users as users_repo
from app.repositories.admin.users import UserRecord
from app.services.admin import audit, events, guards

FAILURE_SELF_FORBIDDEN = "self_forbidden"
FAILURE_LAST_ADMIN = "last_admin"
FAILURE_USER_NOT_FOUND = "user_not_found"
FAILURE_USERNAME_TAKEN = "username_taken"
FAILURE_PASSWORD_EQUALS_USERNAME = "password_equals_username"
FAILURE_PASSWORD_UNCHANGED = "password_unchanged"
FAILURE_OLD_PASSWORD_MISMATCH = "old_password_mismatch"


def _is_admin(db: Session, user_id: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, Role.role_key == ROLE_ADMIN)
    )
    return bool(count)


def _revoke_sessions(db: Session, user_id: int, reason: str) -> int:
    """撤销该用户所有尚未关闭且未过期的会话，返回实际条数。"""

    result = db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utc_now(),
        )
        .values(revoked_at=utc_now(), revoke_reason=reason)
    )
    return int(result.rowcount or 0)


def list_users(
    db: Session,
    *,
    username: str | None,
    nickname: str | None,
    role: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[UserRecord], int]:
    return users_repo.list_users(
        db,
        username=username,
        nickname=nickname,
        role=role,
        status=status,
        page=page,
        page_size=page_size,
    )


def get_user(db: Session, user_id: int) -> UserRecord | None:
    return users_repo.get_user_record(db, user_id)


def create_user(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    username: str,
    password: str,
    nickname: str,
    role: str,
) -> UserRecord:
    event_type = audit.EVENT_USER_CREATED
    if password == username:
        raise events.reject(
            db,
            bad_request("密码不得与用户名相同"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_PASSWORD_EQUALS_USERNAME,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=username,
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        nickname=nickname,
        status="active",
        auth_version=0,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        events.record_failure(
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_USERNAME_TAKEN,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=username,
        )
        raise bad_request("用户名已存在") from None

    role_row = db.scalar(select(Role).where(Role.role_key == role))
    if role_row is None:
        db.rollback()
        raise AppError(500, "服务器内部错误")
    db.add(UserRole(user_id=user.id, role_id=role_row.id))

    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={"username": user.username, "role": role},
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()

    record = users_repo.get_user_record(db, user.id)
    if record is None:  # pragma: no cover - 刚提交的行不可能不存在
        raise AppError(500, "服务器内部错误")
    return record


def update_nickname(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    target_id: int,
    nickname: str,
) -> UserRecord:
    event_type = audit.EVENT_PROFILE_UPDATED
    guards.set_lock_timeout(db)
    rows = guards.lock_users(db, [actor.id, target_id])
    guards.revalidate_actor(actor, rows.get(actor.id))
    target = rows.get(target_id)
    if target is None:
        raise events.reject(
            db,
            not_found("用户不存在"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_USER_NOT_FOUND,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )

    changed = target.nickname != nickname
    if changed:
        target.nickname = nickname

    # 同名昵称也算一次受控操作：不跳过审计。
    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={"changed_fields": ["nickname"] if changed else []},
        target_type="user",
        target_id=str(target_id),
    )
    db.commit()

    record = users_repo.get_user_record(db, target_id)
    if record is None:  # pragma: no cover
        raise not_found("用户不存在")
    return record


def change_status(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    target_id: int,
    status: str,
    reason: str,
) -> dict:
    event_type = audit.EVENT_USER_STATUS_CHANGED

    # 先取全局“有效管理员不归零”锁，再按 id 升序锁操作者/目标。
    guards.lock_admin_guard(db)
    rows = guards.lock_users(db, [actor.id, target_id])
    guards.revalidate_actor(actor, rows.get(actor.id))
    target = rows.get(target_id)
    if target is None:
        raise events.reject(
            db,
            not_found("用户不存在"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_USER_NOT_FOUND,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )

    if target.id == actor.id:
        raise events.reject(
            db,
            bad_request("不能修改自己的账号状态"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_SELF_FORBIDDEN,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )

    from_status = target.status
    if from_status == status:
        # 重复同状态：200 changed=false，不增版本、不撤销会话，但仍记审计。
        events.enqueue_success(
            db,
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            summary_values={
                "from_status": from_status,
                "to_status": status,
                "revoked_session_count": 0,
            },
            target_type="user",
            target_id=str(target_id),
        )
        db.commit()
        return {
            "id": target_id,
            "status": status,
            "changed": False,
            "revoked_session_count": 0,
        }

    if status == "disabled" and _is_admin(db, target.id):
        # 锁内统计，禁止先查后写。
        if guards.count_active_admins(db, exclude_user_id=target.id) == 0:
            raise events.reject(
                db,
                bad_request("不能停用最后一个有效管理员"),
                event_type=event_type,
                actor=actor,
                reason_code=FAILURE_LAST_ADMIN,
                request_id=request_id,
                ip=ip,
                user_agent=user_agent,
                started_at=started_at,
                target_type="user",
                target_id=str(target_id),
            )

    revoked = 0
    if status == "disabled":
        target.auth_version = target.auth_version + 1
        revoked = _revoke_sessions(db, target.id, "account_disabled")
    target.status = status

    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={
            "from_status": from_status,
            "to_status": status,
            "revoked_session_count": revoked,
        },
        target_type="user",
        target_id=str(target_id),
    )
    db.commit()
    return {
        "id": target_id,
        "status": status,
        "changed": True,
        "revoked_session_count": revoked,
    }


def reset_password(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    target_id: int,
    new_password: str,
    reason: str,
) -> dict:
    event_type = audit.EVENT_PASSWORD_RESET
    guards.lock_admin_guard(db)
    rows = guards.lock_users(db, [actor.id, target_id])
    guards.revalidate_actor(actor, rows.get(actor.id))
    target = rows.get(target_id)
    if target is None:
        raise events.reject(
            db,
            not_found("用户不存在"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_USER_NOT_FOUND,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )
    if target.id == actor.id:
        raise events.reject(
            db,
            bad_request("重置本人密码请使用个人中心"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_SELF_FORBIDDEN,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )
    if new_password == target.username:
        raise events.reject(
            db,
            bad_request("密码不得与用户名相同"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_PASSWORD_EQUALS_USERNAME,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )
    if verify_password(new_password, target.password_hash):
        raise events.reject(
            db,
            bad_request("新密码不得与当前密码相同"),
            event_type=event_type,
            actor=actor,
            reason_code=FAILURE_PASSWORD_UNCHANGED,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(target_id),
        )

    target.password_hash = hash_password(new_password)
    target.auth_version = target.auth_version + 1
    revoked = _revoke_sessions(db, target.id, "password_reset")

    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={
            "target_user_id": target.id,
            "revoked_session_count": revoked,
        },
        target_type="user",
        target_id=str(target_id),
    )
    db.commit()
    return {
        "id": target_id,
        "changed": True,
        "revoked_session_count": revoked,
    }


def change_own_password(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    old_password: str,
    new_password: str,
) -> dict:
    event_type = audit.EVENT_SELF_PASSWORD_CHANGED
    guards.set_lock_timeout(db)
    rows = guards.lock_users(db, [actor.id])
    actor_row = rows.get(actor.id)
    guards.revalidate_actor(actor, actor_row)

    def reject(exc: AppError, reason_code: str) -> AppError:
        return events.reject(
            db,
            exc,
            event_type=event_type,
            actor=actor,
            reason_code=reason_code,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            target_type="user",
            target_id=str(actor.id),
        )

    if not verify_password(old_password, actor_row.password_hash):
        raise reject(
            bad_request("旧密码不正确"), FAILURE_OLD_PASSWORD_MISMATCH
        )
    if new_password == actor_row.username:
        raise reject(
            bad_request("密码不得与用户名相同"),
            FAILURE_PASSWORD_EQUALS_USERNAME,
        )
    if verify_password(new_password, actor_row.password_hash):
        raise reject(
            bad_request("新密码不得与当前密码相同"),
            FAILURE_PASSWORD_UNCHANGED,
        )

    actor_row.password_hash = hash_password(new_password)
    actor_row.auth_version = actor_row.auth_version + 1
    revoked = _revoke_sessions(db, actor.id, "password_changed")

    events.enqueue_success(
        db,
        event_type=event_type,
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        summary_values={"revoked_session_count": revoked},
        target_type="user",
        target_id=str(actor.id),
    )
    db.commit()
    return {"changed": True, "reauth_required": True}
