"""Unified administrator workflow API. GETs never advance processing."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ok
from app.db import models_processing_workflows as m
from app.db.base import get_db
from app.db.models_processing import MaterialSource, ProcessingTask
from app.module3.annotation_identity import rules_manifest
from app.schemas_processing_workflows import (
    AlignmentCorrectionRequest,
    ContinueRequest,
    OperationDto,
    PublishRequest,
    ReprocessPreview,
    ReprocessRequest,
    RetryOperationRequest,
    ReviewSaveRequest,
    ReviewSubmitRequest,
    RevisionCreate,
    RevisionListDto,
    SourceCorrectionRequest,
    StageApprovalRequest,
    UploadCancel,
    UploadReserve,
    WorkflowAction,
    WorkflowCreate,
    WorkflowDetailDto,
    WorkflowEnvelope,
    WorkflowErrorResponse,
    WorkflowListDto,
)
from app.services.processing import (
    orchestration,
    publication,
    reading,
    reviewing,
    uploads,
)
from app.services.processing import workflows as service
from app.services.processing.tasks import verify_material

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
            "max_upload_bytes": settings.m3_upload_max_bytes,
            "formats": {
                "paper": ["pdf"],
                "answer": ["pdf"],
                "audio": ["m4a", "mp3", "wav", "flac", "ogg"],
            },
            "document_modes": ["text", "scan"],
            "rules": rules_manifest(),
            "processing_ready": orchestration.environment_ready(settings),
            "blocked_reason": None
            if orchestration.environment_ready(settings)
            else "处理/OCR环境或模型目录未配置",
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
    # One bounded task query for the page; never load question content here.
    task_issues = dict(
        db.execute(
            select(ProcessingTask.id, ProcessingTask.issues).where(
                ProcessingTask.id.in_(
                    [r.current_task_id for r in rows if r.current_task_id]
                )
            )
        ).all()
    )
    # List projections are bounded and do not query per-question/per-workflow details.
    return ok(
        {
            "items": [
                {
                    "workflow_id": row.id,
                    "revision_id": row.current_revision_id,
                    "row_version": row.row_version,
                    "source_check_required": service.source_check_required(
                        row.processing_state, task_issues.get(row.current_task_id, [])
                    ),
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


@router.post(
    "/{workflow_id}/material-uploads",
    status_code=201,
    response_model=WorkflowEnvelope[OperationDto],
)
def reserve_upload(
    workflow_id: UUID,
    payload: UploadReserve,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    service.get_workflow(db, workflow_id)
    command = uploads.reserve(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {"code": 201, "msg": "上传已预留", "data": service.command_data(command)}


@router.post(
    "/{workflow_id}/material-uploads/{upload_id}/cancel",
    response_model=WorkflowEnvelope[OperationDto],
)
def cancel_upload(
    workflow_id: UUID,
    upload_id: UUID,
    payload: UploadCancel,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.get_workflow(db, workflow_id)
    command = uploads.cancel(
        db, workflow_id, upload_id, payload, user.id, idempotency_key
    )
    return ok(service.command_data(command))


@router.put("/{workflow_id}/materials/{kind}")
async def upload_material(
    workflow_id: UUID,
    kind: str,
    request: Request,
    upload_id: UUID = Header(alias="X-Upload-Id"),
    revision_id: UUID = Header(alias="X-Expected-Revision-Id"),
    version: int = Header(alias="X-Expected-Upload-Version", gt=0),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    service.get_workflow(db, workflow_id)
    if kind not in {"paper", "answer", "audio"}:
        raise AppError(422, "未知材料类别")
    db.rollback()
    return ok(
        await uploads.receive(
            request,
            workflow_id,
            revision_id,
            kind,
            upload_id,
            version,
            user.id,
            settings,
        ),
        "材料已验证并保存",
    )


@router.get("/{workflow_id}/materials/{material_id}")
def get_material(
    workflow_id: UUID,
    material_id: int,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    workflow = service.get_workflow(db, workflow_id)
    material = db.scalar(
        select(MaterialSource)
        .join(
            m.ProcessingWorkflowMaterial,
            m.ProcessingWorkflowMaterial.material_id == MaterialSource.id,
        )
        .where(
            m.ProcessingWorkflowMaterial.revision_id == workflow.current_revision_id,
            MaterialSource.id == material_id,
        )
        .limit(1)
    )
    if not material:
        raise AppError(404, "本修订没有该材料")
    path = verify_material(material, settings)
    return FileResponse(
        path,
        media_type=material.media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/{workflow_id}/start", status_code=202)
def start(
    workflow_id: UUID,
    payload: WorkflowAction,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    command = orchestration.start(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {"code": 202, "msg": "开始操作已受理", "data": service.command_data(command)}


@router.post("/{workflow_id}/stage-approvals")
def stage_approval(
    workflow_id: UUID,
    payload: StageApprovalRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return ok(
        service.command_data(
            orchestration.approve_stage(
                db, workflow_id, payload, user.id, idempotency_key, settings
            )
        )
    )


@router.post("/{workflow_id}/continue", status_code=202)
def continue_stage(
    workflow_id: UUID,
    payload: ContinueRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    command = orchestration.continue_stage(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {"code": 202, "msg": "继续操作已受理", "data": service.command_data(command)}


@router.post("/{workflow_id}/stop")
def stop(
    workflow_id: UUID,
    payload: WorkflowAction,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(
        service.command_data(
            orchestration.stop(db, workflow_id, payload, user.id, idempotency_key)
        )
    )


@router.post("/{workflow_id}/retries", status_code=202)
def retry(
    workflow_id: UUID,
    payload: RetryOperationRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    command = orchestration.retry(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {"code": 202, "msg": "重试操作已受理", "data": service.command_data(command)}


@router.get("/{workflow_id}/revisions/{revision_id}/stages/{stage}")
def stage(
    workflow_id: UUID,
    revision_id: UUID,
    stage: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    expected_artifact_hash: str | None = None,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    workflow = service.get_workflow(db, workflow_id)
    if workflow.current_revision_id != revision_id:
        raise service.conflict("VERSION_CONFLICT", "当前修订已变化")
    revision = db.get(m.ProcessingWorkflowRevision, revision_id)
    content, projection = orchestration.stage_payload(db, revision, stage, settings)
    if (
        expected_artifact_hash and expected_artifact_hash != projection["artifact_hash"]
    ) or (cursor and not expected_artifact_hash):
        raise service.conflict("VERSION_CONFLICT", "阶段分页版本变化")
    items = (
        content.get("segments", [])
        if stage == "align"
        else content.get("questions", [])
    )
    if stage == "source" and revision.workflow_contract == "library.v1":
        items = items + [
            s
            for s in content.get("transcript_segments", [])
            if s["segment_type"] == "body"
        ]
    if stage == "sample":
        items = content.get("questions", [])[:5] + [
            {
                **a,
                "text": (
                    f"{a['question_src_id']} / {a['option_letter']} · "
                    f"{a['status']}：{a['reason']}"
                ),
            }
            for a in content.get("distractor_assessments", [])
        ]
        items += [
            {
                "_src_id": d["reference"],
                "text": (
                    f"{d['question_src_id']} 候选删改复核："
                    + "；".join(
                        f"{r.get('option_letter', '')}/{r.get('error_cause_code', '')} "
                        f"{r['kind']}"
                        for r in d["diff"]["changes"]
                    )
                ),
            }
            for d in content.get("candidate_changes", [])
        ]
    return ok(
        {
            **projection,
            "result_hash": __import__(
                "app.module3.contracts", fromlist=["result_hash"]
            ).result_hash(content)
            if content.get("schema_version") in {"m3.v2", "m3.v3"}
            else None,
            "items": reading.public_value(items[cursor : cursor + limit]),
            "total": len(items),
            "next_cursor": cursor + limit if cursor + limit < len(items) else None,
        }
    )


@router.get("/{workflow_id}/revisions/{revision_id}/questions")
def questions(
    workflow_id: UUID,
    revision_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    expected_result_hash: str | None = None,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    workflow = service.get_workflow(db, workflow_id)
    if workflow.current_revision_id != revision_id:
        raise service.conflict("VERSION_CONFLICT", "当前修订已变化")
    return ok(
        reading.questions(
            db,
            db.get(m.ProcessingWorkflowRevision, revision_id),
            settings,
            expected_result_hash,
            cursor,
            limit,
        )
    )


@router.get("/{workflow_id}/review-sessions/{session_id}")
def review_session(
    workflow_id: UUID,
    session_id: UUID,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _, _, session, _, content = reviewing.session_context(db, workflow_id, session_id)
    items = db.scalars(
        select(m.ProcessingReviewItem)
        .where(m.ProcessingReviewItem.session_id == session.id)
        .order_by(m.ProcessingReviewItem.question_src_id)
        .offset(cursor)
        .limit(limit)
    ).all()
    return ok(
        {
            "session_id": session.id,
            "row_version": session.row_version,
            "state": session.state,
            "result_hash": session.result_hash,
            "total": len(content["questions"]),
            "items": [row.decisions for row in items],
            "next_cursor": cursor + limit if len(items) == limit else None,
        }
    )


@router.patch("/{workflow_id}/review-sessions/{session_id}/items")
def save_reviews(
    workflow_id: UUID,
    session_id: UUID,
    payload: ReviewSaveRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(
        service.command_data(
            reviewing.save(db, workflow_id, session_id, payload, user, idempotency_key)
        )
    )


@router.post("/{workflow_id}/review-sessions/{session_id}/returns")
def return_reviews(
    workflow_id: UUID,
    session_id: UUID,
    payload: ReviewSaveRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not any(
        item.content == "changes_required" and item.note.strip() and item.issues
        for item in payload.items
    ):
        raise AppError(422, "退回须定位题目/字段并填写具体原因")
    return ok(
        service.command_data(
            reviewing.save(db, workflow_id, session_id, payload, user, idempotency_key)
        )
    )


@router.post("/{workflow_id}/review-sessions/{session_id}/submit")
def submit_reviews(
    workflow_id: UUID,
    session_id: UUID,
    payload: ReviewSubmitRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return ok(
        service.command_data(
            reviewing.submit(
                db, workflow_id, session_id, payload, user, idempotency_key, settings
            )
        )
    )


@router.get("/{workflow_id}/operations")
def list_operations(
    workflow_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    service.get_workflow(db, workflow_id)
    commands = db.scalars(
        select(m.ProcessingWorkflowCommand)
        .where(
            m.ProcessingWorkflowCommand.workflow_id == workflow_id,
            m.ProcessingWorkflowCommand.created_by == user.id,
        )
        .order_by(
            m.ProcessingWorkflowCommand.created_at.desc(),
            m.ProcessingWorkflowCommand.id.desc(),
        )
        .limit(limit)
    ).all()
    return ok({"items": [service.command_data(command) for command in commands]})


@router.post("/{workflow_id}/reprocess-preview")
def reprocess_preview(
    workflow_id: UUID,
    payload: "ReprocessPreview",
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing import reprocessing

    return ok(reprocessing.preview(db, workflow_id, payload, settings))


@router.post("/{workflow_id}/reprocess", status_code=202)
def reprocess(
    workflow_id: UUID,
    payload: "ReprocessRequest",
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing import reprocessing

    command = reprocessing.execute(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {"code": 202, "msg": "修复计划已受理", "data": service.command_data(command)}


@router.post("/{workflow_id}/source-corrections", status_code=201)
def source_correction(
    workflow_id: UUID,
    payload: "SourceCorrectionRequest",
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing import reprocessing

    command = reprocessing.correct_source(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {
        "code": 201,
        "msg": "来源校正已建立子修订，待逐项确认",
        "data": service.command_data(command),
    }


@router.post("/{workflow_id}/alignment-corrections", status_code=202)
def alignment_correction(
    workflow_id: UUID,
    payload: AlignmentCorrectionRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing.reprocessing import correct_alignment

    command = correct_alignment(
        db, workflow_id, payload, user.id, idempotency_key, settings
    )
    return {
        "code": 202,
        "msg": "来源原文已建立子修订并重新计算对齐",
        "data": service.command_data(command),
    }


@router.post("/{workflow_id}/publish", status_code=202)
def publish(
    workflow_id: UUID,
    payload: PublishRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    command = publication.begin(db, workflow_id, payload, user.id, idempotency_key)
    return {"code": 202, "msg": "发布操作已受理", "data": service.command_data(command)}


@router.get("/{workflow_id}/revisions/{revision_id}/segments/{segment_id}/audio")
def aligned_sentence_audio(
    workflow_id: UUID,
    revision_id: UUID,
    segment_id: str,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing import tasks
    from app.services.processing.media import evidence_clip

    workflow = service.get_workflow(db, workflow_id)
    if workflow.current_revision_id != revision_id:
        raise service.conflict("VERSION_CONFLICT", "当前修订已变化")
    revision = db.get(m.ProcessingWorkflowRevision, revision_id)
    content, projection = orchestration.stage_payload(db, revision, "align", settings)
    segment = next(
        (
            row
            for row in content["segments"]
            if row["_src_id"] == segment_id and row["segment_type"] == "body"
        ),
        None,
    )
    if not segment:
        raise AppError(404, "当前对齐结果没有该正文句")
    material = next(
        row
        for row in tasks.task_materials(db, UUID(projection["task_id"]))
        if row.source_kind == "audio"
    )
    if material.sha256 != revision.materials_manifest["audio"]["sha256"]:
        raise service.conflict("ARTIFACT_CHANGED", "对齐原音身份变化")
    path = evidence_clip(
        verify_material(material, settings),
        material.sha256,
        segment["start_ms"],
        segment["end_ms"],
        settings,
    )
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={
            "Cache-Control": "private, no-store",
            "X-Source-Start-Ms": str(segment["start_ms"]),
            "X-Source-End-Ms": str(segment["end_ms"]),
        },
    )


@router.get("/{workflow_id}/revisions/{revision_id}/evidences/{evidence_id}/audio")
def evidence_audio(
    workflow_id: UUID,
    revision_id: UUID,
    evidence_id: str,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.processing import tasks
    from app.services.processing.media import evidence_clip

    workflow = service.get_workflow(db, workflow_id)
    if workflow.current_revision_id != revision_id:
        raise service.conflict("VERSION_CONFLICT", "当前修订已变化")
    revision = db.get(m.ProcessingWorkflowRevision, revision_id)
    stage = next(
        (
            stage
            for stage in ("final", "sample", "source")
            if stage in revision.stage_fingerprints
        ),
        None,
    )
    if not stage:
        raise AppError(404, "尚无有效证据")
    content, projection = orchestration.stage_payload(db, revision, stage, settings)
    evidence = next(
        (row for row in content.get("evidences", []) if row["_src_id"] == evidence_id),
        None,
    )
    if not evidence:
        raise AppError(404, "证据不存在")
    material = next(
        row
        for row in tasks.task_materials(db, UUID(projection["task_id"]))
        if row.source_kind == "audio"
    )
    if material.sha256 != content["audio"]["file_hash"]:
        raise service.conflict("ARTIFACT_CHANGED", "证据原音身份变化")
    path = evidence_clip(
        verify_material(material, settings),
        material.sha256,
        evidence["start_ms"],
        evidence["end_ms"],
        settings,
    )
    return FileResponse(
        path,
        media_type="audio/wav",
        headers={
            "Cache-Control": "private, no-store",
            "X-Source-Start-Ms": str(evidence["start_ms"]),
            "X-Source-End-Ms": str(evidence["end_ms"]),
        },
    )
