"""管理端在线会话模型（主文档 §6.3）。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.schemas_admin.common import PageData, to_display_time
from app.schemas_admin.users import validate_reason


class SessionOut(BaseModel):
    """对外只给会话标识与摘要，不含 jti / jti_hash / token。"""

    session_id: uuid.UUID
    user_id: int
    username: str
    role: str | None
    ip: str | None
    user_agent_summary: str
    issued_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    is_current: bool

    @field_serializer("issued_at", "last_activity_at", "expires_at")
    def _serialize_time(self, value: datetime) -> str:
        return to_display_time(value)


class SessionPage(PageData[SessionOut]):
    as_of: datetime
    active_account_count: int
    active_session_count: int

    @field_serializer("as_of")
    def _serialize_as_of(self, value: datetime) -> str:
        return to_display_time(value)


class SessionRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


class SessionRevokeResult(BaseModel):
    session_id: uuid.UUID
    changed: bool
