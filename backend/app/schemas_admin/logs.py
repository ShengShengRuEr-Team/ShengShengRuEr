"""管理端日志 DTO（主文档 §5.2/§7.3）。

只输出白名单字段：不含密码/哈希、token、jti、jti_hash、UA 原文与 summary 之外的 payload。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer

from app.schemas_admin.common import PageData, to_display_time


class LoginLogOut(BaseModel):
    event_id: uuid.UUID
    request_id: uuid.UUID
    occurred_at: datetime
    event_type: str
    username_attempted: str
    actor_user_id: int | None
    actor_name: str
    role_snapshot: str | None
    result: str
    reason_code: str | None
    ip: str | None
    user_agent_summary: str
    duration_ms: int

    @field_serializer("occurred_at")
    def _serialize_time(self, value: datetime) -> str:
        return to_display_time(value)


class OperationLogOut(BaseModel):
    event_id: uuid.UUID
    request_id: uuid.UUID
    occurred_at: datetime
    event_type: str
    actor_user_id: int | None
    actor_name: str
    role_snapshot: str | None
    target_type: str | None
    target_id: str | None
    result: str
    reason_code: str | None
    summary: dict[str, Any]
    ip: str | None
    user_agent_summary: str
    duration_ms: int
    run_id: uuid.UUID | None

    @field_serializer("occurred_at")
    def _serialize_time(self, value: datetime) -> str:
        return to_display_time(value)


class LoginLogPage(PageData[LoginLogOut]):
    """登录日志分页。"""


class OperationLogPage(PageData[OperationLogOut]):
    """操作日志分页。"""
