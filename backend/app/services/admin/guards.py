"""管理员保护锁、行锁顺序与操作者重验。

锁顺序固定（主文档 §6.2）：
全局“有效管理员不归零”事务锁 → users 按 id 升序 → auth_sessions 按 UUID 升序。

锁等待有界：超时抛 SQLAlchemy 异常，由全局 500 处理并回滚，不留半成功状态。
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core.errors import unauthorized
from app.core.permissions import ROLE_ADMIN
from app.db.models import Role, User, UserRole

#: 与调度锁、其他业务锁不同的固定整数键；事务提交自动释放。
ADMIN_GUARD_LOCK_KEY = 728_310_442
LOCK_TIMEOUT_MS = 3_000


def set_lock_timeout(db: Session) -> None:
    # SET 语句不支持绑定参数，这里使用常量值。
    db.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))


def lock_admin_guard(db: Session) -> None:
    """串行化所有可能减少 active admin 的操作。"""

    set_lock_timeout(db)
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": ADMIN_GUARD_LOCK_KEY},
    )


def lock_users(db: Session, user_ids: list[int]) -> dict[int, User]:
    """按 id 升序锁定用户行，返回 id → User。"""

    unique_ids = sorted({int(user_id) for user_id in user_ids})
    rows = db.scalars(
        select(User)
        .where(User.id.in_(unique_ids))
        .order_by(User.id)
        .with_for_update()
    ).all()
    return {row.id: row for row in rows}


def lock_sessions(db: Session, session_ids: list) -> list:
    """按 UUID 升序锁定会话行。"""

    from app.db.models_admin import AuthSession

    unique_ids = sorted({session_id for session_id in session_ids}, key=str)
    return list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.id.in_(unique_ids))
            .order_by(AuthSession.id)
            .with_for_update()
        ).all()
    )


def revalidate_actor(actor: CurrentUser, row: User | None) -> User:
    """在锁内重验操作者：仍 active 且认证版本未变，否则按凭据失效处理。"""

    if row is None or row.status != "active":
        raise unauthorized()
    if row.auth_version != actor.auth_version:
        raise unauthorized()
    return row


def count_active_admins(
    db: Session, *, exclude_user_id: int | None = None
) -> int:
    """锁内统计 active 管理员数量；必须在取得保护锁后调用。"""

    stmt = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.role_key == ROLE_ADMIN, User.status == "active")
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return int(db.scalar(stmt) or 0)
