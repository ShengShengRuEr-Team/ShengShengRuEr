"""管理端固定权限目录与角色映射。

权限码逐字沿用《若依管理端引入》正式需求规格 V1.0 §4.2，共 21 个；
大小写（`resetPassword`/`loginLogs`/`operationLogs`）与冒号分段不改，
不提供 `*:*:*` 之类的通配符绕过。角色到权限的映射是唯一来源，
不在数据库建权限表，也不提供在线编辑。

本模块只做纯函数映射，不依赖 FastAPI，便于生成器与静态检查复用。
"""

from collections.abc import Iterable

from app.core.permissions import ROLE_ADMIN, ROLE_STUDENT

# 用户
PERM_USER_READ = "admin:user:read"
PERM_USER_CREATE = "admin:user:create"
PERM_USER_UPDATE = "admin:user:update"
PERM_USER_STATUS = "admin:user:status"
PERM_USER_RESET_PASSWORD = "admin:user:resetPassword"

# 本人
PERM_SELF_READ = "admin:self:read"
PERM_SELF_UPDATE = "admin:self:update"
PERM_SELF_PASSWORD = "admin:self:password"

# 会话
PERM_SESSION_READ = "admin:session:read"
PERM_SESSION_REVOKE = "admin:session:revoke"

# 日志
PERM_LOG_READ = "admin:log:read"

# 文档
PERM_DOCS_READ = "admin:docs:read"
PERM_DOCS_DEBUG = "admin:docs:debug"

# 监控
PERM_MONITOR_READ = "admin:monitor:read"

# 任务
PERM_JOB_READ = "admin:job:read"
PERM_JOB_CONTROL = "admin:job:control"

# 缓存
PERM_CACHE_CLEAR = "admin:cache:clear"

# 首页
PERM_DASHBOARD_READ = "admin:dashboard:read"

# 导出
PERM_EXPORT_USERS = "admin:export:users"
PERM_EXPORT_LOGIN_LOGS = "admin:export:loginLogs"
PERM_EXPORT_OPERATION_LOGS = "admin:export:operationLogs"


#: 固定权限目录。顺序即 getInfo 返回顺序，新增必须逐字取自正式规格。
ADMIN_PERMISSIONS: tuple[str, ...] = (
    PERM_USER_READ,
    PERM_USER_CREATE,
    PERM_USER_UPDATE,
    PERM_USER_STATUS,
    PERM_USER_RESET_PASSWORD,
    PERM_SELF_READ,
    PERM_SELF_UPDATE,
    PERM_SELF_PASSWORD,
    PERM_SESSION_READ,
    PERM_SESSION_REVOKE,
    PERM_LOG_READ,
    PERM_DOCS_READ,
    PERM_DOCS_DEBUG,
    PERM_MONITOR_READ,
    PERM_JOB_READ,
    PERM_JOB_CONTROL,
    PERM_CACHE_CLEAR,
    PERM_DASHBOARD_READ,
    PERM_EXPORT_USERS,
    PERM_EXPORT_LOGIN_LOGS,
    PERM_EXPORT_OPERATION_LOGS,
)

#: 角色到权限集合的映射：admin 拥有全部固定码，student 为空集。
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: frozenset(ADMIN_PERMISSIONS),
    ROLE_STUDENT: frozenset(),
}

#: 接口文档调试白名单：(method, path_template, permission)。
#: T06 逐项登记无副作用 JSON GET；本轮为空，不启用任何调试路径。
DOC_DEBUG_ALLOWLIST: tuple[tuple[str, str, str], ...] = ()


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    """按角色求权限并集；未知角色不授予任何权限。"""

    granted: set[str] = set()
    for role in set(roles):
        granted.update(ROLE_PERMISSIONS.get(role, frozenset()))
    return frozenset(granted)


def permission_codes(roles: Iterable[str]) -> tuple[str, ...]:
    """按固定目录顺序返回权限码，供 getInfo 稳定输出。"""

    granted = permissions_for_roles(roles)
    return tuple(code for code in ADMIN_PERMISSIONS if code in granted)


def has_permission(roles: Iterable[str], code: str) -> bool:
    """判断角色集合是否拥有指定权限码。"""

    return code in permissions_for_roles(roles)
