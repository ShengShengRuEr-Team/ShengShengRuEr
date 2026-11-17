"""三类 CSV 导出服务（主文档 §11.1）。

要点：
- 复用列表筛选与排序，忽略分页；单只读快照导出全部匹配行；
- 分批读取（键集分页），每批前检查 15 秒 deadline，超时不截断、返回 500；
- 上限 5000 行 / 5MiB；超限 400；0 行只返回表头；
- 内存生成后关闭读事务，再以独立事务写 EXPORT_COMPLETED；审计失败 → 500 且不发 CSV；
- 失败写 EXPORT_FAILED（独立事务），stage 区分 read/limit_rows/limit_bytes/timeout/generate/audit。
"""

import csv
import io
import json
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.core import admin_enums as enums
from app.core.admin_permissions import role_snapshot
from app.core.errors import AppError
from app.core.request_context import elapsed_ms, new_event_id
from app.db.base import SessionLocal
from app.repositories.admin import exports as exports_repo
from app.repositories.admin.users import UserRecord
from app.services.admin import audit

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024
DEADLINE_SECONDS = 15.0
BATCH_SIZE = exports_repo.EXPORT_BATCH_SIZE
UA_SUMMARY_LENGTH = 80

#: 可在测试中替换的单调时钟。
_monotonic = time.monotonic


class _ExportTimeout(Exception):
    """超出 15 秒预算。"""


class _TooManyRows(Exception):
    """超过 5000 行。"""


class _TooManyBytes(Exception):
    """编码后超过 5MiB。"""


def _check_deadline(started_at: float) -> None:
    if _monotonic() - started_at > DEADLINE_SECONDS:
        raise _ExportTimeout


def _time_text(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        return value.isoformat()
    return value.astimezone(DISPLAY_TZ).isoformat()


def _sanitize_cell(value) -> str:
    text = "" if value is None else str(value)
    stripped = text.lstrip()
    if stripped[:1] in ("=", "+", "-", "@") or text[:1] in ("\t", "\r", "\n"):
        return "'" + text
    return text


def _label(mapping: dict[str, str], value) -> str:
    if value is None:
        return ""
    return mapping.get(str(value), str(value))


def _summary_text(value) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _build_csv(header: list[str], rows: list[list[object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_sanitize_cell(cell) for cell in row])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def _filename(export_type: str) -> str:
    stamp = datetime.now(DISPLAY_TZ).strftime("%Y%m%d-%H%M%S")
    return f"admin-{export_type.replace('_', '-')}-{stamp}.csv"


def _write_success_event(
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    export_type: str,
    row_count: int,
    byte_size: int,
) -> None:
    event = audit.AuditEvent(
        event_type=audit.EVENT_EXPORT_COMPLETED,
        result=audit.RESULT_SUCCESS,
        event_id=new_event_id(),
        request_id=request_id,
        actor_user_id=actor.id,
        actor_name=actor.username,
        role_snapshot=role_snapshot(actor.roles),
        target_type="export",
        target_id=export_type,
        summary_values={
            "export_type": export_type,
            "row_count": row_count,
            "byte_size": byte_size,
        },
        ip=ip,
        user_agent=user_agent,
        duration_ms=elapsed_ms(started_at),
    )
    with SessionLocal() as db:
        db.add(event.audit_row())
        db.commit()


def _write_failure_event(
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    export_type: str,
    stage: str,
) -> None:
    event = audit.AuditEvent(
        event_type=audit.EVENT_EXPORT_FAILED,
        result=audit.RESULT_FAILURE,
        event_id=new_event_id(),
        request_id=request_id,
        actor_user_id=actor.id,
        actor_name=actor.username,
        role_snapshot=role_snapshot(actor.roles),
        target_type="export",
        target_id=export_type,
        reason_code=stage,
        summary_values={"export_type": export_type, "stage": stage},
        ip=ip,
        user_agent=user_agent,
        duration_ms=elapsed_ms(started_at),
    )
    try:
        audit.persist_audit_failure(event)
    except Exception:  # noqa: BLE001 - 失败事件绝不覆盖原错误
        pass


def _collect_users(
    db: Session,
    *,
    started_at: float,
    username: str | None,
    nickname: str | None,
    role: str | None,
    status: str | None,
) -> list[UserRecord]:
    rows: list[UserRecord] = []
    after: tuple[datetime, int] | None = None
    while True:
        _check_deadline(started_at)
        batch = exports_repo.user_batch(
            db,
            username=username,
            nickname=nickname,
            role=role,
            status=status,
            after=after,
            limit=BATCH_SIZE,
        )
        rows.extend(batch)
        if len(rows) > MAX_ROWS:
            raise _TooManyRows
        if len(batch) < BATCH_SIZE:
            return rows
        last = batch[-1]
        after = (last.created_at, last.id)


def _collect_login(
    db: Session,
    *,
    started_at: float,
    start: datetime,
    end: datetime,
    username: str | None,
    result: str | None,
    failure_type: str | None,
    ip: str | None,
) -> list:
    rows: list = []
    after: tuple[datetime, uuid.UUID] | None = None
    while True:
        _check_deadline(started_at)
        batch = exports_repo.login_batch(
            db,
            start=start,
            end=end,
            username=username,
            result=result,
            failure_type=failure_type,
            ip=ip,
            after=after,
            limit=BATCH_SIZE,
        )
        rows.extend(batch)
        if len(rows) > MAX_ROWS:
            raise _TooManyRows
        if len(batch) < BATCH_SIZE:
            return rows
        last = batch[-1]
        after = (last.occurred_at, last.event_id)


def _collect_operation(
    db: Session,
    *,
    started_at: float,
    start: datetime,
    end: datetime,
    actor_username: str | None,
    event_type: str | None,
    result: str | None,
    target_type: str | None,
) -> list:
    rows: list = []
    after: tuple[datetime, uuid.UUID] | None = None
    while True:
        _check_deadline(started_at)
        batch = exports_repo.operation_batch(
            db,
            start=start,
            end=end,
            actor_username=actor_username,
            event_type=event_type,
            result=result,
            target_type=target_type,
            after=after,
            limit=BATCH_SIZE,
        )
        rows.extend(batch)
        if len(rows) > MAX_ROWS:
            raise _TooManyRows
        if len(batch) < BATCH_SIZE:
            return rows
        last = batch[-1]
        after = (last.occurred_at, last.event_id)


def _finalize(
    db: Session,
    *,
    payload: bytes,
    export_type: str,
    row_count: int,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
) -> tuple[bytes, str, int]:
    if len(payload) > MAX_BYTES:
        raise _TooManyBytes
    # 关闭只读事务，再写独立审计事务。
    db.rollback()
    try:
        _write_success_event(
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            export_type=export_type,
            row_count=row_count,
            byte_size=len(payload),
        )
    except Exception as exc:  # noqa: BLE001
        _write_failure_event(
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
            export_type=export_type,
            stage="audit",
        )
        raise AppError(500, "服务器内部错误") from exc
    return payload, _filename(export_type), row_count


def _translate_failure(
    db: Session,
    exc: Exception,
    *,
    export_type: str,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
) -> AppError:
    db.rollback()
    if isinstance(exc, _TooManyRows):
        stage, error = "limit_rows", AppError(400, "导出行数超过 5000 行上限")
    elif isinstance(exc, _TooManyBytes):
        stage, error = "limit_bytes", AppError(400, "导出文件超过 5MiB 上限")
    elif isinstance(exc, _ExportTimeout):
        stage, error = "timeout", AppError(500, "服务器内部错误")
    else:
        stage, error = "read", AppError(500, "服务器内部错误")
    _write_failure_event(
        actor=actor,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        started_at=started_at,
        export_type=export_type,
        stage=stage,
    )
    return error


def export_users(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    username: str | None,
    nickname: str | None,
    role: str | None,
    status: str | None,
) -> tuple[bytes, str, int]:
    header = ["用户ID", "用户名", "昵称", "角色", "状态", "创建时间", "更新时间"]
    export_type = "users"
    try:
        records = _collect_users(
            db,
            started_at=started_at,
            username=username,
            nickname=nickname,
            role=role,
            status=status,
        )
        rows = [
            [
                record.id,
                record.username,
                record.nickname,
                _label(enums.ROLE_LABELS, record.role),
                _label(enums.ACCOUNT_STATUS_LABELS, record.status),
                _time_text(record.created_at),
                _time_text(record.updated_at),
            ]
            for record in records
        ]
        payload = _build_csv(header, rows)
        return _finalize(
            db,
            payload=payload,
            export_type=export_type,
            row_count=len(records),
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, AppError):
            raise
        raise _translate_failure(
            db,
            exc,
            export_type=export_type,
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        ) from exc


def export_login_logs(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    start: datetime,
    end: datetime,
    username: str | None,
    result: str | None,
    failure_type: str | None,
    filter_ip: str | None,
) -> tuple[bytes, str, int]:
    header = [
        "事件ID",
        "时间",
        "声明用户名",
        "识别ID",
        "操作者名称",
        "角色快照",
        "结果",
        "原因",
        "IP",
        "UA摘要",
    ]
    export_type = "login_logs"
    try:
        records = _collect_login(
            db,
            started_at=started_at,
            start=start,
            end=end,
            username=username,
            result=result,
            failure_type=failure_type,
            ip=filter_ip,
        )
        rows = [
            [
                str(record.event_id),
                _time_text(record.occurred_at),
                record.username_attempted,
                record.actor_user_id if record.actor_user_id is not None else "",
                record.actor_name,
                _label(enums.ROLE_LABELS, record.role_snapshot),
                _label(enums.LOG_RESULT_LABELS, record.result),
                _label(enums.LOGIN_FAILURE_LABELS, record.reason_code),
                "" if record.ip is None else str(record.ip),
                (record.user_agent or "")[:UA_SUMMARY_LENGTH],
            ]
            for record in records
        ]
        payload = _build_csv(header, rows)
        return _finalize(
            db,
            payload=payload,
            export_type=export_type,
            row_count=len(records),
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, AppError):
            raise
        raise _translate_failure(
            db,
            exc,
            export_type=export_type,
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        ) from exc


def export_operation_logs(
    db: Session,
    *,
    actor: CurrentUser,
    request_id: uuid.UUID,
    ip: str | None,
    user_agent: str,
    started_at: float,
    start: datetime,
    end: datetime,
    actor_username: str | None,
    event_type: str | None,
    result: str | None,
    target_type: str | None,
) -> tuple[bytes, str, int]:
    header = [
        "事件ID",
        "时间",
        "操作者名称",
        "操作者ID",
        "事件类型",
        "目标类型",
        "目标ID",
        "结果",
        "原因",
        "摘要",
        "请求ID",
        "run_id",
    ]
    export_type = "operation_logs"
    try:
        records = _collect_operation(
            db,
            started_at=started_at,
            start=start,
            end=end,
            actor_username=actor_username,
            event_type=event_type,
            result=result,
            target_type=target_type,
        )
        rows = []
        for record in records:
            summary = audit.filter_summary(record.event_type, record.summary)
            rows.append(
                [
                    str(record.event_id),
                    _time_text(record.occurred_at),
                    record.actor_name,
                    record.actor_user_id
                    if record.actor_user_id is not None
                    else "",
                    _label(enums.EVENT_TYPE_LABELS, record.event_type),
                    _label(enums.TARGET_TYPE_LABELS, record.target_type),
                    record.target_id or "",
                    _label(enums.LOG_RESULT_LABELS, record.result),
                    _label(enums.LOGIN_FAILURE_LABELS, record.reason_code),
                    _summary_text(summary),
                    str(record.request_id),
                    str(record.run_id) if record.run_id else "",
                ]
            )
        payload = _build_csv(header, rows)
        return _finalize(
            db,
            payload=payload,
            export_type=export_type,
            row_count=len(records),
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, AppError):
            raise
        raise _translate_failure(
            db,
            exc,
            export_type=export_type,
            actor=actor,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            started_at=started_at,
        ) from exc
