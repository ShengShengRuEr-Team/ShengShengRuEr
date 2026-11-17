"""管理端枚举与标签的唯一来源（主文档 §11.4）。

- 运行期代码与前端生成物都从这里取枚举值与中文标签；
- 只登记本项目真实使用的值；题库枚举逐字引用既有模型约束与真实数据，
  不在这里另造新值；
- 未知服务端值在界面上保留原值并显示「未知（原值）」，由前端生成物约定。
"""

from app.core.permissions import ROLE_ADMIN, ROLE_STUDENT

# --------------------------------------------------------------------------- #
# 事件类型（主文档 §7.1）
# --------------------------------------------------------------------------- #

EVENT_LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
EVENT_LOGIN_FAILED = "LOGIN_FAILED"
EVENT_LOGOUT = "LOGOUT"
EVENT_USER_CREATED = "USER_CREATED"
EVENT_PROFILE_UPDATED = "PROFILE_UPDATED"
EVENT_USER_STATUS_CHANGED = "USER_STATUS_CHANGED"
EVENT_PASSWORD_RESET = "PASSWORD_RESET"
EVENT_SELF_PASSWORD_CHANGED = "SELF_PASSWORD_CHANGED"
EVENT_SESSION_REVOKED = "SESSION_REVOKED"
EVENT_JOB_PAUSED = "JOB_PAUSED"
EVENT_JOB_RESUMED = "JOB_RESUMED"
EVENT_JOB_TRIGGERED = "JOB_TRIGGERED"
EVENT_JOB_FINISHED = "JOB_FINISHED"
EVENT_CACHE_CLEAR_STARTED = "CACHE_CLEAR_STARTED"
EVENT_CACHE_CLEARED = "CACHE_CLEARED"
EVENT_EXPORT_COMPLETED = "EXPORT_COMPLETED"
EVENT_EXPORT_FAILED = "EXPORT_FAILED"
EVENT_DOC_GET_DEBUG = "DOC_GET_DEBUG"

EVENT_TYPES: tuple[str, ...] = (
    EVENT_LOGIN_SUCCEEDED,
    EVENT_LOGIN_FAILED,
    EVENT_LOGOUT,
    EVENT_USER_CREATED,
    EVENT_PROFILE_UPDATED,
    EVENT_USER_STATUS_CHANGED,
    EVENT_PASSWORD_RESET,
    EVENT_SELF_PASSWORD_CHANGED,
    EVENT_SESSION_REVOKED,
    EVENT_JOB_PAUSED,
    EVENT_JOB_RESUMED,
    EVENT_JOB_TRIGGERED,
    EVENT_JOB_FINISHED,
    EVENT_CACHE_CLEAR_STARTED,
    EVENT_CACHE_CLEARED,
    EVENT_EXPORT_COMPLETED,
    EVENT_EXPORT_FAILED,
    EVENT_DOC_GET_DEBUG,
)

EVENT_TYPE_LABELS: dict[str, str] = {
    EVENT_LOGIN_SUCCEEDED: "登录成功",
    EVENT_LOGIN_FAILED: "登录失败",
    EVENT_LOGOUT: "退出登录",
    EVENT_USER_CREATED: "创建用户",
    EVENT_PROFILE_UPDATED: "更新资料",
    EVENT_USER_STATUS_CHANGED: "启停账号",
    EVENT_PASSWORD_RESET: "重置密码",
    EVENT_SELF_PASSWORD_CHANGED: "本人改密",
    EVENT_SESSION_REVOKED: "强制下线",
    EVENT_JOB_PAUSED: "任务暂停",
    EVENT_JOB_RESUMED: "任务恢复",
    EVENT_JOB_TRIGGERED: "任务触发",
    EVENT_JOB_FINISHED: "任务结束",
    EVENT_CACHE_CLEAR_STARTED: "缓存清理开始",
    EVENT_CACHE_CLEARED: "缓存清理完成",
    EVENT_EXPORT_COMPLETED: "导出生成完成",
    EVENT_EXPORT_FAILED: "导出失败",
    EVENT_DOC_GET_DEBUG: "文档调试请求",
}

# --------------------------------------------------------------------------- #
# 结果与登录失败类型
# --------------------------------------------------------------------------- #

RESULT_SUCCESS = "SUCCESS"
RESULT_FAILURE = "FAILURE"

LOG_RESULTS: tuple[str, ...] = (RESULT_SUCCESS, RESULT_FAILURE)
LOG_RESULT_LABELS: dict[str, str] = {
    RESULT_SUCCESS: "成功",
    RESULT_FAILURE: "失败",
}

FAILURE_UNKNOWN_ACCOUNT = "UNKNOWN_ACCOUNT"
FAILURE_BAD_PASSWORD = "BAD_PASSWORD"
FAILURE_DISABLED = "DISABLED"

LOGIN_FAILURE_TYPES: tuple[str, ...] = (
    FAILURE_UNKNOWN_ACCOUNT,
    FAILURE_BAD_PASSWORD,
    FAILURE_DISABLED,
)
LOGIN_FAILURE_LABELS: dict[str, str] = {
    FAILURE_UNKNOWN_ACCOUNT: "账号不存在",
    FAILURE_BAD_PASSWORD: "密码错误",
    FAILURE_DISABLED: "账号停用",
}

# --------------------------------------------------------------------------- #
# 账号、角色与撤销原因
# --------------------------------------------------------------------------- #

ACCOUNT_STATUSES: tuple[str, ...] = ("active", "disabled")
ACCOUNT_STATUS_LABELS: dict[str, str] = {
    "active": "启用",
    "disabled": "停用",
}

ROLE_KEYS: tuple[str, ...] = (ROLE_ADMIN, ROLE_STUDENT)
ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "管理员",
    ROLE_STUDENT: "学生",
}

REVOKE_REASONS: tuple[str, ...] = (
    "account_disabled",
    "password_changed",
    "password_reset",
    "kicked",
    "logout",
)
REVOKE_REASON_LABELS: dict[str, str] = {
    "account_disabled": "账号停用",
    "password_changed": "本人改密",
    "password_reset": "管理员重置密码",
    "kicked": "管理员强制下线",
    "logout": "主动退出",
}

# --------------------------------------------------------------------------- #
# 审计目标类型
# --------------------------------------------------------------------------- #

TARGET_TYPES: tuple[str, ...] = (
    "user",
    "session",
    "job",
    "cache",
    "export",
    "docs",
)
TARGET_TYPE_LABELS: dict[str, str] = {
    "user": "用户",
    "session": "会话",
    "job": "任务",
    "cache": "缓存",
    "export": "导出",
    "docs": "接口文档",
}

# --------------------------------------------------------------------------- #
# 监控与任务状态（T08/T07 使用，先登记值）
# --------------------------------------------------------------------------- #

MONITOR_STATES: tuple[str, ...] = (
    "ok",
    "error",
    "unknown",
    "stale",
    "not_configured",
    "not_applicable",
)
MONITOR_STATE_LABELS: dict[str, str] = {
    "ok": "正常",
    "error": "错误",
    "unknown": "未知",
    "stale": "过期",
    "not_configured": "未配置",
    "not_applicable": "不适用",
}

SEVERITIES: tuple[str, ...] = ("normal", "warning", "critical", "none")
SEVERITY_LABELS: dict[str, str] = {
    "normal": "正常",
    "warning": "告警",
    "critical": "严重",
    "none": "无",
}

RUN_STATES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "PARTIAL",
    "FAILED",
    "INTERRUPTED",
)
RUN_STATE_LABELS: dict[str, str] = {
    "QUEUED": "排队中",
    "RUNNING": "运行中",
    "SUCCEEDED": "成功",
    "PARTIAL": "部分完成",
    "FAILED": "失败",
    "INTERRUPTED": "已中断",
}

# --------------------------------------------------------------------------- #
# 题库既有枚举（逐字引用真实值，不新造）
# --------------------------------------------------------------------------- #

MODULE2_SEGMENT_TYPES: tuple[str, ...] = ("body", "question")
MODULE2_SEGMENT_TYPE_LABELS: dict[str, str] = {
    "body": "正文",
    "question": "题目",
}

MODULE2_VISIBILITY_ACTIONS: tuple[str, ...] = ("confirm", "cancel")
MODULE2_VISIBILITY_ACTION_LABELS: dict[str, str] = {
    "confirm": "开放",
    "cancel": "取消开放",
}

# 现有题库数据与测试的唯一真实取值；其它值按「未知（原值）」处理。
MODULE2_EXAM_LEVELS: tuple[str, ...] = ("CET4",)
MODULE2_EXAM_LEVEL_LABELS: dict[str, str] = {"CET4": "四级"}

#: 供生成器按稳定键顺序导出的映射集合。
LABEL_REGISTRY: dict[str, dict[str, str]] = {
    "eventTypeLabels": EVENT_TYPE_LABELS,
    "loginFailureLabels": LOGIN_FAILURE_LABELS,
    "logResultLabels": LOG_RESULT_LABELS,
    "accountStatusLabels": ACCOUNT_STATUS_LABELS,
    "roleLabels": ROLE_LABELS,
    "revokeReasonLabels": REVOKE_REASON_LABELS,
    "targetTypeLabels": TARGET_TYPE_LABELS,
    "monitorStateLabels": MONITOR_STATE_LABELS,
    "severityLabels": SEVERITY_LABELS,
    "runStateLabels": RUN_STATE_LABELS,
    "segmentTypeLabels": MODULE2_SEGMENT_TYPE_LABELS,
    "visibilityActionLabels": MODULE2_VISIBILITY_ACTION_LABELS,
    "examLevelLabels": MODULE2_EXAM_LEVEL_LABELS,
}
