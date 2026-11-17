"""留存任务控制与监控 DTO（主文档 §10.1）。"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.schemas_admin.common import PageData, to_display_time
from app.schemas_admin.users import validate_reason


class SchedulerInstanceOut(BaseModel):
    instance_id: uuid.UUID
    booted_at: datetime
    heartbeat_at: datetime
    last_error_code: str | None
    state: str | None
    version: int

    @field_serializer("booted_at", "heartbeat_at")
    def _time(self, value: datetime) -> str:
        return to_display_time(value)


class JobDefinitionOut(BaseModel):
    job_id: str
    enabled: bool
    timezone: str
    next_scheduled_at: datetime | None
    last_scheduled_slot: date | None
    last_run_id: uuid.UUID | None
    active_run_id: uuid.UUID | None
    missed_slots: int
    updated_at: datetime

    @field_serializer("next_scheduled_at", "updated_at")
    def _time(self, value: datetime | None) -> str | None:
        return to_display_time(value) if value is not None else None


class JobOverviewOut(BaseModel):
    job: JobDefinitionOut
    scheduler_health: str  # ok | stale | not_configured
    instances: list[SchedulerInstanceOut]


class JobRunOut(BaseModel):
    id: uuid.UUID
    job_id: str
    trigger: str
    slot_key: date | None
    actor_id: int | None
    state: str
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    attempt_count: int
    retry_at: datetime | None
    retry_pending: bool
    counts: dict[str, Any]
    counts_complete: bool
    error_code: str | None
    created_at: datetime

    @field_serializer(
        "queued_at", "started_at", "finished_at", "heartbeat_at", "retry_at",
        "created_at",
    )
    def _time(self, value: datetime | None) -> str | None:
        return to_display_time(value) if value is not None else None


class JobRunPage(PageData[JobRunOut]):
    """run 历史分页。"""


class JobEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


class JobEnabledResult(BaseModel):
    job_id: str
    enabled: bool
    changed: bool


class JobTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


class JobTriggerResult(BaseModel):
    run_id: uuid.UUID
    state: str
