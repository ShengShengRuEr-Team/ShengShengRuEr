"""留存任务控制与监控路由（主文档 §10.1）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.admin_platform.common import request_ip, request_user_agent
from app.api.deps import CurrentUser, require_permission
from app.core.admin_jobs import JOB_ID
from app.core.admin_permissions import PERM_JOB_CONTROL, PERM_JOB_READ
from app.core.errors import bad_request, not_found, ok
from app.core.request_context import current_request_id, monotonic_ms
from app.db.base import get_db
from app.repositories.admin import jobs as jobs_repo
from app.schemas import ApiResponse
from app.schemas_admin.jobs import (
    JobEnabledRequest,
    JobEnabledResult,
    JobOverviewOut,
    JobRunPage,
    JobTriggerRequest,
    JobTriggerResult,
)
from app.services.admin import jobs as jobs_service

router = APIRouter(prefix="/admin", tags=["管理端-任务"])

PageNumber = Annotated[int, Query(ge=1)]


def _require_supported(job_id: str) -> None:
    if job_id != JOB_ID:
        raise bad_request("不支持的任务编码")


@router.get("/monitor/jobs", response_model=ApiResponse[JobOverviewOut])
def get_jobs(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_JOB_READ)),
) -> dict:
    return ok(jobs_service.build_overview(db))


@router.get(
    "/monitor/jobs/{job_id}/runs", response_model=ApiResponse[JobRunPage]
)
def get_job_runs(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_JOB_READ)),
    page: PageNumber = 1,
    page_size: Annotated[int, Query()] = 20,
) -> dict:
    from app.api.admin_platform.common import validate_page_size

    if job_id != JOB_ID:
        raise not_found("任务不存在")
    validate_page_size(page_size)
    rows, total = jobs_repo.list_runs(db, page=page, page_size=page_size)
    return ok(
        JobRunPage(
            items=[jobs_service.to_run_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/monitor/jobs/{job_id}/enabled",
    response_model=ApiResponse[JobEnabledResult],
)
def set_job_enabled(
    job_id: str,
    payload: JobEnabledRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_JOB_CONTROL)),
) -> dict:
    _require_supported(job_id)
    result = jobs_service.set_enabled(
        db,
        actor=current_user,
        enabled=payload.enabled,
        reason=payload.reason,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
    )
    return ok(result, "配置已更新")


@router.post(
    "/monitor/jobs/{job_id}/run",
    response_model=ApiResponse[JobTriggerResult],
)
def trigger_job(
    job_id: str,
    payload: JobTriggerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_permission(PERM_JOB_CONTROL)),
) -> dict:
    _require_supported(job_id)
    run_id = jobs_service.trigger_manual(
        db,
        actor=current_user,
        reason=payload.reason,
        request_id=current_request_id(),
        ip=request_ip(request),
        user_agent=request_user_agent(request),
        started_at=monotonic_ms(),
    )
    return ok(JobTriggerResult(run_id=run_id, state="QUEUED"), "已排队")
