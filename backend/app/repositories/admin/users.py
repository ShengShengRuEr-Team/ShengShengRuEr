"""用户查询仓储：固定筛选、DD-05 角色投影、集合计数。

只做查询与条件构造，不在这里提交事务或写审计。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, case, func, select
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_ADMIN, ROLE_STUDENT
from app.db.models import Role, User, UserRole


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    nickname: str
    role: str | None
    status: str
    created_at: datetime
    updated_at: datetime


def role_projection():
    """返回 (角色子查询, 单值角色表达式)。

    DD-05：既有 roles 关系保留；单值角色按 admin 优先、否则 student，
    无已知角色为 NULL。混合角色投影为 admin，因此不会落进 student 筛选。
    """

    role_sq = (
        select(
            UserRole.user_id.label("user_id"),
            func.bool_or(Role.role_key == ROLE_ADMIN).label("is_admin"),
            func.bool_or(Role.role_key == ROLE_STUDENT).label("is_student"),
        )
        .join(Role, Role.id == UserRole.role_id)
        .group_by(UserRole.user_id)
        .subquery()
    )
    role_expr = case(
        (role_sq.c.is_admin.is_(True), ROLE_ADMIN),
        (role_sq.c.is_student.is_(True), ROLE_STUDENT),
        else_=None,
    ).cast(String(16))
    return role_sq, role_expr


def build_user_select():
    role_sq, role_expr = role_projection()
    return (
        select(
            User.id,
            User.username,
            User.nickname,
            role_expr.label("role"),
            User.status,
            User.created_at,
            User.updated_at,
        ).outerjoin(role_sq, role_sq.c.user_id == User.id),
        role_sq,
        role_expr,
    )


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
    stmt, role_sq, role_expr = build_user_select()

    if username:
        stmt = stmt.where(User.username.contains(username, autoescape=True))
    if nickname:
        stmt = stmt.where(User.nickname.contains(nickname, autoescape=True))
    if role == ROLE_ADMIN:
        stmt = stmt.where(role_expr == ROLE_ADMIN)
    elif role == ROLE_STUDENT:
        # 混合角色投影为 admin，不落学生列表。
        stmt = stmt.where(
            role_sq.c.is_student.is_(True), role_sq.c.is_admin.is_not(True)
        )
    if status:
        stmt = stmt.where(User.status == status)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [UserRecord(**row._mapping) for row in rows], int(total or 0)


def get_user_record(db: Session, user_id: int) -> UserRecord | None:
    stmt, _, _ = build_user_select()
    row = db.execute(stmt.where(User.id == user_id)).first()
    return UserRecord(**row._mapping) if row is not None else None
