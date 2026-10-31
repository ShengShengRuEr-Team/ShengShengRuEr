"""角色定义与角色判断的唯一来源。

模块一只有两个角色，身份由后端角色决定，前端只做展示层判断。
"""

from collections.abc import Iterable

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"

ALL_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_STUDENT)

ROLE_NAMES: dict[str, str] = {
    ROLE_ADMIN: "管理员",
    ROLE_STUDENT: "学生",
}


def is_admin(roles: Iterable[str]) -> bool:
    """判断角色集合中是否包含管理员。"""

    return ROLE_ADMIN in set(roles)
