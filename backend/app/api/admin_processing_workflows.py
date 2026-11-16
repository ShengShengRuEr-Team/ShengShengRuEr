"""Unified administrator workflow API. GETs never advance processing."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ok
from app.db import models_processing_workflows as m
from app.db.base import get_db
from app.module3.annotation_identity import rules_manifest
from app.schemas_processing_workflows import (
    OperationDto,
    RevisionCreate,
    RevisionListDto,
    WorkflowCreate,
    WorkflowDetailDto,
    WorkflowEnvelope,
    WorkflowErrorResponse,
    WorkflowListDto,
)
from app.services.processing import workflows as service

router = APIRouter(
    prefix="/admin/processing-workflows",
    tags=["处理工作流"],
    responses={
        code: {"model": WorkflowErrorResponse} for code in (401, 403, 404, 409, 422)
    },
)


def operation_not_found():
    return AppError(
        404, "未查询到该操作，请保留原请求及操作键", error_code="OPERATION_NOT_FOUND"
    )


@router.get("/capabilities")
def capabilities(
    user: CurrentUser = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    return ok(
        {
            "max_upload_bytes": 536870912,
            "formats": {
                "paper": ["pdf"],
                "answer": ["pdf"],
                "audio": ["m4a", "mp3", "wav", "flac", "ogg"],
            },
            "document_modes": ["text", "scan"],
            "rules": rules_manifest(),
            "processing_ready": False,
            "blocked_reason": "工作流 Worker 接入待完成",
            "budget_limits_usd": {
                "sample": str(settings.m3_sample_budget_usd),
                "paper": str(settings.m3_run_budget_usd),
                "total": str(settings.m3_total_budget_usd),
            },
        }
    )


@router.get("/operations/by-key", response_model=WorkflowEnvelope[OperationDto])
def operation_by_key(
    action: str = Query(min_length=1, max_length=64),
    idempotency_key: UUID = Query(),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    command = service.command_by_key(db, user.id, action, idempotency_key)
    if command is None:
        raise operation_not_found()
    return ok(service.command_data(command))


@router.post("", status_code=201, response_model=WorkflowEnvelope[OperationDto])
def create_workflow(
    payload: WorkflowCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    command = service.create_workflow(db, payload, user.id, idempotency_key)
    return {"code": 201, "msg": "工作流已建立", "data": service.command_data(command)}


@router.get("", response_model=WorkflowEnvelope[WorkflowListDto])
def list_workflows(
    exam_level: str | None = Query(default=None, pattern="^CET[46]$"),
    exam_year: int | None = Query(default=None, ge=1980, le=2200),
    processing_state: str | None = None,
    content_review_state: str | None = None,
    error_review_state: str | None = None,
    publication_state: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(m.ProcessingWorkflow)
    filters = {
        "exam_level": exam_level,
        "exam_year": exam_year,
        "processing_state": processing_state,
        "content_review_state": content_review_state,
        "error_review_state": error_review_state,
        "publication_state": publication_state,
    }
    for field, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(m.ProcessingWorkflow, field) == value)
    rows, next_cursor = service.cursor_page(
        db, stmt, m.ProcessingWorkflow, limit, cursor
    )
    # List projections are bounded and do not query per-question/per-workflow details.
    return ok(
        {
            "items": [
                {
                    "workflow_id": row.id,
                    "revision_id": row.current_revision_id,
                    "row_version": row.row_version,
                    **{
                        key: getattr(row, key)
                        for key in (
                            "exam_level",
                            "exam_year",
                            "exam_month",
                            "paper_set",
                            "exam_paper_id",
                            "processing_state",
                            "content_review_state",
                            "error_review_state",
                            "publication_state",
                            "created_at",
                            "updated_at",
                        )
                    },
                }
                for row in rows
            ],
            "next_cursor": next_cursor,
        }
    )


@router.get("/{workflow_id}", response_model=WorkflowEnvelope[WorkflowDetailDto])
def get_workflow(
    workflow_id: UUID,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(service.workflow_data(db, service.get_workflow(db, workflow_id)))


@router.get(
    "/{workflow_id}/operations/{operation_id}",
    response_model=WorkflowEnvelope[OperationDto],
)
def get_operation(
    workflow_id: UUID,
    operation_id: UUID,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.get_workflow(db, workflow_id)
    command = db.scalar(
        select(m.ProcessingWorkflowCommand).where(
            m.ProcessingWorkflowCommand.id == operation_id,
            m.ProcessingWorkflowCommand.workflow_id == workflow_id,
            m.ProcessingWorkflowCommand.created_by == user.id,
        )
    )
    if command is None:
        raise operation_not_found()
    return ok(service.command_data(command))


@router.get(
    "/{workflow_id}/revisions", response_model=WorkflowEnvelope[RevisionListDto]
)
def list_revisions(
    workflow_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.get_workflow(db, workflow_id)
    rows, next_cursor = service.cursor_page(
        db,
        select(m.ProcessingWorkflowRevision).where(
            m.ProcessingWorkflowRevision.workflow_id == workflow_id
        ),
        m.ProcessingWorkflowRevision,
        limit,
        cursor,
    )
    return ok(
        {
            "items": [
                {
                    "revision_id": r.id,
                    "revision_no": r.revision_no,
                    "parent_revision_id": r.parent_revision_id,
                    "reason": r.reason,
                    "document_mode": r.document_mode,
                    "listening_pages": r.listening_pages,
                    "materials_hash": r.materials_hash,
                    "result_hash": r.final_result_hash,
                    "batch_id": r.batch_id,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
            "next_cursor": next_cursor,
        }
    )


@router.post(
    "/{workflow_id}/revisions",
    status_code=201,
    response_model=WorkflowEnvelope[OperationDto],
)
def create_revision(
    workflow_id: UUID,
    payload: RevisionCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.get_workflow(db, workflow_id)
    command = service.create_revision(
        db, workflow_id, payload, user.id, idempotency_key
    )
    return {"code": 201, "msg": "子修订已建立", "data": service.command_data(command)}
