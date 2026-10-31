"""权限码与角色映射的唯一来源。"""

from collections.abc import Iterable

# 权限码：两段式 <资源>:<操作>，共 5 个，已冻结。
PAPER_READ = "paper:read"
QUESTION_READ = "question:read"
QUESTION_READ_SENSITIVE = "question:read_sensitive"
TASK_START = "task:start"
TASK_READ = "task:read"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        PAPER_READ,
        QUESTION_READ,
        QUESTION_READ_SENSITIVE,
        TASK_START,
        TASK_READ,
    }
)

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_STUDENT: frozenset({PAPER_READ, QUESTION_READ}),
}

ROLE_NAMES: dict[str, str] = {
    ROLE_ADMIN: "管理员",
    ROLE_STUDENT: "学生",
}


def permissions_for_roles(roles: Iterable[str]) -> set[str]:
    """按角色集合合并权限码。"""

    permissions: set[str] = set()
    for role_key in roles:
        permissions.update(ROLE_PERMISSIONS.get(role_key, frozenset()))
    return permissions


def has_permission(roles: Iterable[str], permission_code: str) -> bool:
    return permission_code in permissions_for_roles(roles)
