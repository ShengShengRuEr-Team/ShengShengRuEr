"""开发/测试环境种子数据。

用法（在 backend 目录）：
    python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import ROLE_ADMIN, ROLE_NAMES, ROLE_STUDENT
from app.core.security import hash_password
from app.db.base import SessionLocal
from app.db.models import Role, User, UserRole

SEED_USERS = (
    {
        "username": "admin",
        "password": "admin123",
        "nickname": "管理员",
        "role_key": ROLE_ADMIN,
    },
    {
        "username": "student",
        "password": "student123",
        "nickname": "学生",
        "role_key": ROLE_STUDENT,
    },
)


def _seed_roles(db: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for role_key in (ROLE_ADMIN, ROLE_STUDENT):
        role = db.scalar(select(Role).where(Role.role_key == role_key))
        if role is None:
            role = Role(role_key=role_key, role_name=ROLE_NAMES[role_key])
            db.add(role)
            db.flush()
        roles[role_key] = role
    return roles


def _seed_users(db: Session, roles: dict[str, Role]) -> None:
    for item in SEED_USERS:
        user = db.scalar(select(User).where(User.username == item["username"]))
        if user is None:
            user = User(
                username=item["username"],
                password_hash=hash_password(item["password"]),
                nickname=item["nickname"],
                status="active",
            )
            db.add(user)
            db.flush()

        role = roles[item["role_key"]]
        user_role = db.get(UserRole, (user.id, role.id))
        if user_role is None:
            db.add(UserRole(user_id=user.id, role_id=role.id))


def seed() -> dict[str, int]:
    """写入两个角色与两个账号；可重复执行。"""

    settings = get_settings()
    if settings.app_env not in ("development", "test"):
        raise RuntimeError("种子数据只允许在 development/test 环境写入默认口令")

    with SessionLocal() as db:
        roles = _seed_roles(db)
        _seed_users(db, roles)
        db.commit()
        return {"roles": len(roles), "users": len(SEED_USERS)}


def main() -> None:
    summary = seed()
    print(
        "种子数据完成："
        f"roles={summary['roles']}, users={summary['users']}"
    )


if __name__ == "__main__":
    main()
