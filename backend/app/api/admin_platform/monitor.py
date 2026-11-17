"""监控读取、缓存清理、TLS 证据与 OAuth 能力页（§9.2—§9.5）。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.api.admin_platform.common import request_ip, request_user_agent
from app.api.deps import CurrentUser, require_permission
from app.core.admin_permissions import (
    PERM_CACHE_CLEAR,
    PERM_MONITOR_READ,
)
from app.core.errors import AppError, ok
from app.core.request_context import current_request_id, monotonic_ms
from app.core.transport_evidence import evidence_payload
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_admin.users import validate_reason
from app.services.admin import cache_admin, module3, monitoring

router = APIRouter(prefix="/admin/monitor", tags=["管理端-监控"])


def _snapshot() -> tuple[dict[str, Any], str]:
    service = monitoring.get_monitoring_service()
    if service is None:
        # 采样关闭（测试/开发）时按请求即时采集一次，不伪装成周期样本。
        transient = monitoring.MonitoringService()
        try:
            transient.collect()
            return transient.snapshot(), "on_demand"
        finally:
            transient.dispose()
    return service.snapshot(), "interval_15s"


def _filtered(prefix: str) -> dict[str, Any]:
    snapshot, sampling = _snapshot()
    metrics = {
        name: value
        for name, value in snapshot["metrics"].items()
        if name.startswith(prefix)
    }
    return {
        "instance_id": snapshot["instance_id"],
        "booted_at": snapshot["booted_at"],
        "server_time": snapshot["server_time"],
        "sampling": sampling,
        "metrics": metrics,
    }


@router.get("/database", response_model=ApiResponse[dict])
def get_database(
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
) -> dict:
    return ok(_filtered("database."))


@router.get("/server", response_model=ApiResponse[dict])
def get_server(
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
) -> dict:
    payload = _filtered("server.")
    payload["module3"] = module3.observation_payload()
    return ok(payload)


@router.get("/cache", response_model=ApiResponse[dict])
def get_cache(
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
) -> dict:
    return ok(cache_admin.overview_payload())


@router.get("/cache/entries", response_model=ApiResponse[dict])
def get_cache_entries(
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query()] = 20,
) -> dict:
    from app.api.admin_platform.common import validate_page_size

    validate_page_size(page_size)
    items = cache_admin.entries_payload()
    start = (page - 1) * page_size
    return ok(
        {
            "items": items[start : start + page_size],
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }
    )


class CacheClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    expected_instance_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return validate_reason(value)


@router.post("/cache/clear", response_model=ApiResponse[dict])
def clear_cache(
    payload: CacheClearRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_CACHE_CLEAR)),
) -> dict:
    request_id = current_request_id()
    started = monotonic_ms()
    try:
        deleted = cache_admin.clear_cache(
            actor=current_user,
            domain=payload.domain,
            expected_instance_id=payload.expected_instance_id,
            reason=payload.reason,
            request_id=request_id,
            ip=request_ip(request),
            user_agent=request_user_agent(request),
            started_at=started,
        )
    except AppError as exc:
        if exc.status_code == 400:
            cache_admin.record_clear_failure(
                actor=current_user,
                request_id=request_id,
                reason_code="clear_rejected",
                ip=request_ip(request),
                user_agent=request_user_agent(request),
                started_at=started,
            )
        raise
    return ok(
        {
            "domain": payload.domain,
            "instance_id": payload.expected_instance_id,
            "deleted_count": deleted,
        },
        "缓存已清理",
    )


@router.get("/transport", response_model=ApiResponse[dict])
def get_transport(
    request: Request,
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
) -> dict:
    evidence = getattr(request.state, "transport_evidence", None)
    return ok(evidence_payload(evidence))


@router.get("/oauth", response_model=ApiResponse[dict])
def get_oauth(
    current_user: CurrentUser = Depends(require_permission(PERM_MONITOR_READ)),
) -> dict:
    return ok(
        {
            "status": "not_configured",
            "enabled": False,
            "reason": "oauth_server_not_deployed",
            "events": [],
            "login_mode": "jwt_bearer",
        }
    )
