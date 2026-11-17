"""首页汇总 DTO（主文档 §9.5 / 需求 §10.1）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_serializer

from app.schemas_admin.common import to_display_time


class DashboardCacheInfo(BaseModel):
    enabled: bool
    status: Literal["hit", "miss", "not_configured"]
    ttl_seconds: int
    cached_at: datetime | None
    expires_at: datetime | None
    age_seconds: int | None

    @field_serializer("cached_at", "expires_at")
    def _serialize_time(self, value: datetime | None) -> str | None:
        return to_display_time(value) if value is not None else None


class DashboardCards(BaseModel):
    paper_count: int
    awaiting_visibility_count: int
    failed_check_count: int
    active_student_count: int
    disabled_student_count: int
    successful_attempts_7d: int


class DashboardData(BaseModel):
    as_of: datetime
    window_start: datetime
    window_end: datetime
    timezone: str
    cache: DashboardCacheInfo
    cards: DashboardCards

    @field_serializer("as_of", "window_start", "window_end")
    def _serialize_time(self, value: datetime) -> str:
        return to_display_time(value)
