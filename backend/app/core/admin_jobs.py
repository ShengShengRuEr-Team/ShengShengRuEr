"""留存调度常量与状态机（主文档 §5.3/§10）。"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

JOB_ID = "admin.retention_cleanup"
TIMEZONE = ZoneInfo("Asia/Shanghai")
SCHEDULE_TIME = time(3, 10)

HEARTBEAT_INTERVAL_SECONDS = 15
HEARTBEAT_STALE_SECONDS = 60
RUNNING_STALE_SECONDS = 120
RETRY_DELAY_SECONDS = 60

BATCH_SIZE = 1_000
MAX_ROWS_PER_ATTEMPT = 50_000
MAX_SECONDS_PER_ATTEMPT = 60

#: 与管理员保护锁 728310442、其它业务锁不同的固定键。
ADVISORY_LOCK_KEY = 918_273_645

STATE_QUEUED = "QUEUED"
STATE_RUNNING = "RUNNING"
STATE_SUCCEEDED = "SUCCEEDED"
STATE_PARTIAL = "PARTIAL"
STATE_FAILED = "FAILED"
STATE_INTERRUPTED = "INTERRUPTED"
RUN_STATES: tuple[str, ...] = (
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_SUCCEEDED,
    STATE_PARTIAL,
    STATE_FAILED,
    STATE_INTERRUPTED,
)
ACTIVE_STATES: tuple[str, ...] = (STATE_QUEUED, STATE_RUNNING)
TERMINAL_STATES: tuple[str, ...] = (
    STATE_SUCCEEDED,
    STATE_PARTIAL,
    STATE_FAILED,
    STATE_INTERRUPTED,
)

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"
TRIGGERS: tuple[str, ...] = (TRIGGER_SCHEDULED, TRIGGER_MANUAL)

#: 留存期限（固定规则，不提供在线修改）。
LOGIN_RETENTION_DAYS = 90
AUDIT_RETENTION_DAYS = 180
JOB_RUN_RETENTION_DAYS = 180
SESSION_RETENTION_DAYS = 7

#: 删除白名单：只允许这些表，不接受任意表名。
DELETION_TABLES: tuple[str, ...] = (
    "admin_login_events",
    "admin_audit_events",
    "admin_job_runs",
    "auth_sessions",
    "token_revocations",
)


def next_run_after(moment: datetime) -> datetime:
    """严格晚于给定时刻的下一个北京时间 03:10。"""

    local = moment.astimezone(TIMEZONE)
    candidate = datetime.combine(local.date(), SCHEDULE_TIME, tzinfo=TIMEZONE)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def latest_slot_before(moment: datetime) -> datetime:
    """不晚于给定时刻的最近一个北京时间 03:10。"""

    local = moment.astimezone(TIMEZONE)
    candidate = datetime.combine(local.date(), SCHEDULE_TIME, tzinfo=TIMEZONE)
    if candidate > local:
        candidate -= timedelta(days=1)
    return candidate


def slot_key_for(moment: datetime) -> date:
    return moment.astimezone(TIMEZONE).date()
