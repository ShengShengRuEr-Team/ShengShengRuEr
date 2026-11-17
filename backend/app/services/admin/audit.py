"""管理端审计服务。

三类失败通道，任何一级都不得把失败写成成功：

1. 数据库：成功事件与业务同 Session 同事务；失败事件用独立 Session 提交。
2. 本地降级文件：DB 写不了时写 `<fallback>/<instance_id>/*.jsonl`，
   单文件 10MiB、最多 10 份、总上限 100MiB，每进程独立子目录。
3. stderr + critical：DB 与文件都失败时只输出固定错误码与 request_id，
   并把审计存储健康状态标为 critical，绝不声称已有持久证据。

summary 只按事件白名单取字段，序列化 UTF-8 ≤2KiB，不做 payload 整体序列化。
"""

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from app.core.config import get_settings
from app.core.request_context import current_request_id
from app.core.security import utc_now
from app.db.base import SessionLocal
from app.db.models_admin import AdminAuditEvent, AdminLoginEvent

logger = logging.getLogger(__name__)

SUMMARY_MAX_BYTES = 2048
MAX_EVENT_TYPE_LENGTH = 64
MAX_ACTOR_NAME_LENGTH = 50
MAX_USER_AGENT_LENGTH = 256
MAX_TEXT_FIELD_LENGTH = 200

FALLBACK_FILE_MAX_BYTES = 10 * 1024 * 1024
FALLBACK_MAX_FILES = 10
FALLBACK_MAX_TOTAL_BYTES = 100 * 1024 * 1024

INSTANCE_ID = uuid.uuid4()

# 事件类型（主文档 §7.1）。T02 接入登录/退出，其余由后续卡片使用同一通道。
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

FAILURE_UNKNOWN_ACCOUNT = "UNKNOWN_ACCOUNT"
FAILURE_BAD_PASSWORD = "BAD_PASSWORD"
FAILURE_DISABLED = "DISABLED"

RESULT_SUCCESS = "SUCCESS"
RESULT_FAILURE = "FAILURE"

#: 每种事件的 summary 白名单；未登记的事件类型拒绝写入。
SUMMARY_WHITELIST: dict[str, frozenset[str]] = {
    EVENT_LOGIN_SUCCEEDED: frozenset({"session_id", "auth_version"}),
    EVENT_LOGIN_FAILED: frozenset({"failure_type"}),
    EVENT_LOGOUT: frozenset({"session_id"}),
    EVENT_USER_CREATED: frozenset({"username", "role"}),
    EVENT_PROFILE_UPDATED: frozenset({"changed_fields"}),
    EVENT_USER_STATUS_CHANGED: frozenset(
        {"from_status", "to_status", "revoked_session_count"}
    ),
    EVENT_PASSWORD_RESET: frozenset({"target_user_id", "revoked_session_count"}),
    EVENT_SELF_PASSWORD_CHANGED: frozenset({"revoked_session_count"}),
    EVENT_SESSION_REVOKED: frozenset({"session_id", "target_user_id"}),
    EVENT_JOB_PAUSED: frozenset({"enabled"}),
    EVENT_JOB_RESUMED: frozenset({"enabled"}),
    EVENT_JOB_TRIGGERED: frozenset({"run_id"}),
    EVENT_JOB_FINISHED: frozenset({"run_id", "state", "counts_complete"}),
    EVENT_CACHE_CLEAR_STARTED: frozenset({"domain", "instance_id"}),
    EVENT_CACHE_CLEARED: frozenset({"domain", "instance_id", "deleted_count"}),
    EVENT_EXPORT_COMPLETED: frozenset(
        {"export_type", "row_count", "byte_size"}
    ),
    EVENT_EXPORT_FAILED: frozenset({"export_type", "stage"}),
    EVENT_DOC_GET_DEBUG: frozenset({"method", "path_template", "status_code"}),
}

#: 无论是否出现在白名单里都拒绝写入的字段名（防御性兜底）。
FORBIDDEN_SUMMARY_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "jti",
        "secret",
        "jwt",
    }
)


class AuditStorageHealth:
    """进程内审计存储健康状态（T08 采样页读取）。"""

    def __init__(self) -> None:
        self.state = "unknown"
        self.last_error_code: str | None = None
        self.last_error_at: datetime | None = None
        self.last_db_success_at: datetime | None = None
        self.last_fallback_at: datetime | None = None
        self._lock = threading.Lock()

    def mark_db_success(self) -> None:
        with self._lock:
            self.state = "ok"
            self.last_db_success_at = utc_now()
            self.last_error_code = None
            self.last_error_at = None

    def mark_db_failure(self, code: str) -> None:
        with self._lock:
            self.state = "warning"
            self.last_error_code = code
            self.last_error_at = utc_now()

    def mark_fallback_success(self) -> None:
        with self._lock:
            self.last_fallback_at = utc_now()

    def mark_critical(self, code: str) -> None:
        with self._lock:
            self.state = "critical"
            self.last_error_code = code
            self.last_error_at = utc_now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "last_error_code": self.last_error_code,
                "last_error_at": self.last_error_at,
                "last_db_success_at": self.last_db_success_at,
                "last_fallback_at": self.last_fallback_at,
            }


HEALTH = AuditStorageHealth()


def _coerce_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) < 2**53 else str(value)
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (list, tuple)):
        return [_coerce_value(item) for item in list(value)[:20]]
    text = str(value)
    return text[:MAX_TEXT_FIELD_LENGTH]


def _summary_size(summary: Mapping[str, Any]) -> int:
    return len(
        json.dumps(summary, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _shrink_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """把 summary 压到 ≤2KiB：先截断最长的字符串，再丢弃末尾字段。"""

    while _summary_size(summary) > SUMMARY_MAX_BYTES:
        longest_key = None
        longest_length = 0
        for key, value in summary.items():
            if isinstance(value, str) and len(value) > longest_length:
                longest_key = key
                longest_length = len(value)
        if longest_key is not None and longest_length > 0:
            summary[longest_key] = summary[longest_key][: longest_length // 2]
            continue
        if not summary:
            break
        summary.pop(next(reversed(summary)))
    return summary


def build_summary(
    event_type: str, values: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """按白名单构造 summary；未登记事件直接拒绝，避免整包序列化。"""

    allowed = SUMMARY_WHITELIST.get(event_type)
    if allowed is None:
        raise ValueError(f"未登记的事件类型：{event_type}")
    summary: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if key not in allowed:
            continue
        if key.lower() in FORBIDDEN_SUMMARY_KEYS:
            continue
        coerced = _coerce_value(value)
        if coerced is None:
            continue
        summary[key] = coerced
    return _shrink_summary(summary)


@dataclass(frozen=True)
class AuditEvent:
    """一次业务事件的审计事实；event_id 由调用方生成并可跨失败路径复用。"""

    event_type: str
    result: str
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    request_id: uuid.UUID = field(default_factory=current_request_id)
    actor_user_id: int | None = None
    actor_name: str = ""
    role_snapshot: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    reason_code: str | None = None
    summary_values: Mapping[str, Any] = field(default_factory=dict)
    ip: str | None = None
    user_agent: str = ""
    duration_ms: int = 0
    occurred_at: datetime = field(default_factory=utc_now)
    username_attempted: str = ""
    run_id: uuid.UUID | None = None

    def summary(self) -> dict[str, Any]:
        return build_summary(self.event_type, self.summary_values)

    def login_row(self) -> AdminLoginEvent:
        return AdminLoginEvent(
            event_id=self.event_id,
            request_id=self.request_id,
            event_type=self.event_type,
            actor_user_id=self.actor_user_id,
            actor_name=self.actor_name[:MAX_ACTOR_NAME_LENGTH],
            role_snapshot=self.role_snapshot,
            target_type=self.target_type,
            target_id=self.target_id,
            result=self.result,
            reason_code=self.reason_code,
            summary=self.summary(),
            ip=self.ip,
            user_agent=self.user_agent[:MAX_USER_AGENT_LENGTH],
            duration_ms=max(0, int(self.duration_ms)),
            occurred_at=self.occurred_at,
            username_attempted=self.username_attempted[:50],
        )

    def audit_row(self) -> AdminAuditEvent:
        return AdminAuditEvent(
            event_id=self.event_id,
            request_id=self.request_id,
            event_type=self.event_type,
            actor_user_id=self.actor_user_id,
            actor_name=self.actor_name[:MAX_ACTOR_NAME_LENGTH],
            role_snapshot=self.role_snapshot,
            target_type=self.target_type,
            target_id=self.target_id,
            result=self.result,
            reason_code=self.reason_code,
            summary=self.summary(),
            ip=self.ip,
            user_agent=self.user_agent[:MAX_USER_AGENT_LENGTH],
            duration_ms=max(0, int(self.duration_ms)),
            occurred_at=self.occurred_at,
            run_id=self.run_id,
        )

    def fallback_record(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "request_id": str(self.request_id),
            "event_type": self.event_type,
            "result": self.result,
            "actor_user_id": self.actor_user_id,
            "actor_name": self.actor_name[:MAX_ACTOR_NAME_LENGTH],
            "role_snapshot": self.role_snapshot,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason_code": self.reason_code,
            "summary": self.summary(),
            "ip": self.ip,
            "user_agent": self.user_agent[:MAX_USER_AGENT_LENGTH],
            "duration_ms": max(0, int(self.duration_ms)),
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat(),
            "username_attempted": self.username_attempted[:50],
            "run_id": str(self.run_id) if self.run_id else None,
        }


class AuditFallbackWriter:
    """按实例隔离的 JSONL 降级写入器（单文件 10MiB、10 份、总 100MiB）。"""

    def __init__(
        self,
        base_dir: Path,
        instance_id: uuid.UUID,
        *,
        max_file_bytes: int = FALLBACK_FILE_MAX_BYTES,
        max_files: int = FALLBACK_MAX_FILES,
        max_total_bytes: int = FALLBACK_MAX_TOTAL_BYTES,
    ) -> None:
        self._dir = base_dir / str(instance_id)
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes
        self._lock = threading.Lock()
        self._current_name = "audit-current.jsonl"

    @property
    def directory(self) -> Path:
        return self._dir

    def write(self, record: Mapping[str, Any]) -> bool:
        try:
            payload = (
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            logger.error(
                "AUDIT_FALLBACK_SERIALIZE_FAILED error_type=%s",
                type(exc).__name__,
            )
            return False
        with self._lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                current = self._dir / self._current_name
                if (
                    current.exists()
                    and current.stat().st_size + len(payload)
                    > self._max_file_bytes
                ):
                    rotated = self._dir / (
                        "audit-"
                        + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                        + "-"
                        + uuid.uuid4().hex[:6]
                        + ".jsonl"
                    )
                    os.replace(current, rotated)
                with current.open("ab") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._prune()
                return True
            except OSError as exc:
                logger.error(
                    "AUDIT_FALLBACK_WRITE_FAILED error_type=%s",
                    type(exc).__name__,
                )
                return False

    def _prune(self) -> None:
        files = sorted(
            (
                path
                for path in self._dir.glob("*.jsonl")
                if path.is_file()
            ),
            key=lambda path: path.stat().st_mtime,
        )
        while len(files) > self._max_files:
            files.pop(0).unlink(missing_ok=True)
        total = sum(path.stat().st_size for path in files)
        while files and total > self._max_total_bytes:
            removed = files.pop(0)
            total -= removed.stat().st_size
            removed.unlink(missing_ok=True)


_writer: AuditFallbackWriter | None = None
_writer_lock = threading.Lock()


def fallback_writer() -> AuditFallbackWriter:
    global _writer
    with _writer_lock:
        if _writer is None:
            _writer = AuditFallbackWriter(
                get_settings().admin_audit_fallback_path, INSTANCE_ID
            )
        return _writer


def reset_fallback_writer() -> None:
    """测试用：重建降级写入器（读取当前配置）。"""

    global _writer
    with _writer_lock:
        _writer = None


def _persist_independent(event: AuditEvent) -> None:
    """失败事件用独立 Session 提交；DB 失败转降级文件，再失败转 critical。"""

    try:
        row = event.login_row()
        with SessionLocal() as db:
            db.add(row)
            db.commit()
        HEALTH.mark_db_success()
        return
    except Exception as exc:  # noqa: BLE001 - 失败通道必须接住所有异常
        logger.warning(
            "AUDIT_DB_WRITE_FAILED event_id=%s request_id=%s error_type=%s",
            event.event_id,
            event.request_id,
            type(exc).__name__,
        )
        HEALTH.mark_db_failure("AUDIT_DB_WRITE_FAILED")

    try:
        record = event.fallback_record()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "AUDIT_FALLBACK_SERIALIZE_FAILED event_id=%s error_type=%s",
            event.event_id,
            type(exc).__name__,
        )
        HEALTH.mark_critical("AUDIT_FALLBACK_SERIALIZE_FAILED")
        return

    if fallback_writer().write(record):
        HEALTH.mark_fallback_success()
        return

    HEALTH.mark_critical("AUDIT_STORAGE_UNAVAILABLE")
    # 固定错误码 + request_id，不输出业务内容。
    logger.error(
        "AUDIT_STORAGE_CRITICAL request_id=%s event_id=%s",
        event.request_id,
        event.event_id,
    )


def enqueue_login_event(db: Any, event: AuditEvent) -> None:
    """成功事件：加入调用方 Session，由调用方与业务变更一同提交。"""

    db.add(event.login_row())


def enqueue_audit_event(db: Any, event: AuditEvent) -> None:
    """操作成功事件：加入调用方 Session，与业务变更同事务。"""

    db.add(event.audit_row())


def persist_login_failure(event: AuditEvent) -> None:
    """登录失败事件：独立事务，失败不覆盖原始 401。"""

    _persist_independent(event)


def persist_audit_failure(event: AuditEvent) -> None:
    """业务拒绝/操作失败事件：独立事务，失败不覆盖原始错误码。"""

    _persist_independent(event)


def audit_storage_health() -> dict[str, Any]:
    return HEALTH.snapshot()
