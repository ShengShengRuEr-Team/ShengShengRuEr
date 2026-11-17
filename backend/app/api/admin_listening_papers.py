"""模块二管理员接口：配套内容、可见性操作、检查结果。

仅管理员可调用（require_admin，先 401 后 403）；本期所有管理员可管理全部
题库，不按导入人限制。状态字段（当前批次、最低内容检查、可见性）分别表示，
不合并为一个“完成”状态。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import bad_request, not_found, ok
from app.db.base import get_db
from app.db.models_listening import ExamPaper
from app.repositories import listening as repo
from app.repositories.annotations import current_annotations
from app.schemas import ApiResponse
from app.schemas_listening import (
    CheckIssue,
    CheckResultData,
    PaperCompanionAdmin,
    VisibilityActionRequest,
    VisibilityStateData,
)
from app.services import visibility as visibility_service
from app.services.processing.workflows import conflict

router = APIRouter(tags=["听力试卷管理"])


def _get_paper_or_404(db: Session, exam_paper_id: int):
    paper = repo.get_paper(db, exam_paper_id)
    if paper is None:
        raise not_found()
    return paper


@router.get(
    "/admin/listening-papers/{exam_paper_id}/companion",
    response_model=ApiResponse[PaperCompanionAdmin],
)
def get_companion(
    exam_paper_id: int,
    expected_batch_id: int | None = Query(default=None, gt=0),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    paper = _get_paper_or_404(db, exam_paper_id)
    batch = repo.get_current_batch(db, exam_paper_id)
    if expected_batch_id is not None and (not batch or expected_batch_id != batch.id):
        raise conflict("CURRENT_BATCH_CHANGED", "正式批次已变化，请整体刷新")
    return ok(PaperCompanionAdmin(**repo.assemble_admin_companion(db, paper, batch)))


@router.post(
    "/admin/listening-papers/{exam_paper_id}/visibility",
    response_model=ApiResponse[VisibilityStateData],
)
def set_visibility(
    exam_paper_id: int,
    payload: VisibilityActionRequest,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    paper = db.scalar(
        select(ExamPaper).where(ExamPaper.id == exam_paper_id).with_for_update()
    )
    if not paper:
        raise not_found()
    batch = repo.get_current_batch(db, exam_paper_id)
    if batch is None:
        raise bad_request("当前没有可用批次，无法操作可见性")
    if batch.id != payload.expected_batch_id:
        raise conflict("CURRENT_BATCH_CHANGED", "正式批次已变化，请刷新后重新确认")

    if payload.action == "confirm":
        visibility, check = visibility_service.confirm_visible(
            db,
            paper,
            batch,
            current_user.id,
            payload.reason,
            settings.audio_storage_path,
        )
    else:
        visibility = visibility_service.cancel_visible(
            db, paper, batch, current_user.id, payload.reason
        )
        check = repo.get_latest_check(db, batch.id)

    return ok(
        VisibilityStateData(
            exam_paper_id=paper.id,
            batch_code=batch.batch_code,
            is_visible=visibility.is_visible,
            check_passed=bool(check and check.is_passed),
            action=payload.action,
        ),
        "操作成功",
    )


@router.get("/admin/listening-papers/{exam_paper_id}/annotations")
def annotations(
    exam_paper_id: int,
    expected_batch_id: int | None = Query(default=None, gt=0),
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(current_annotations(db, exam_paper_id, expected_batch_id, cursor, limit))


@router.get("/admin/listening-papers/{exam_paper_id}/evidences/{evidence_id}/audio")
def published_evidence_audio(
    exam_paper_id: int,
    evidence_id: str,
    expected_batch_id: int = Query(gt=0),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.db import models_processing_workflows as m
    from app.services.processing import orchestration, tasks
    from app.services.processing.media import evidence_clip

    current_annotations(db, exam_paper_id, expected_batch_id, 0, 1)
    revision = db.scalar(
        select(m.ProcessingWorkflowRevision).where(
            m.ProcessingWorkflowRevision.batch_id == expected_batch_id
        )
    )
    if not revision:
        raise not_found("旧批次没有可用的新规则证据")
    content, projection = orchestration.stage_payload(db, revision, "final", settings)
    evidence = next(
        (row for row in content["evidences"] if row["_src_id"] == evidence_id), None
    )
    if not evidence:
        raise not_found()
    from uuid import UUID

    material = next(
        row
        for row in tasks.task_materials(db, UUID(projection["task_id"]))
        if row.source_kind == "audio"
    )
    if material.sha256 != content["audio"]["file_hash"]:
        raise conflict("ARTIFACT_CHANGED", "证据原音身份变化")
    path = evidence_clip(
        tasks.verify_material(material, settings),
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


@router.get(
    "/admin/listening-papers/{exam_paper_id}/checks",
    response_model=ApiResponse[CheckResultData],
)
def get_checks(
    exam_paper_id: int,
    expected_batch_id: int | None = Query(default=None, gt=0),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    paper = _get_paper_or_404(db, exam_paper_id)
    batch = repo.get_current_batch(db, exam_paper_id)
    if expected_batch_id is not None and (not batch or batch.id != expected_batch_id):
        raise conflict("CURRENT_BATCH_CHANGED", "正式批次已变化，请整体刷新详情")
    if batch is None:
        return ok(
            CheckResultData(
                exam_paper_id=paper.id,
                batch_code=None,
                is_passed=False,
                issues=[],
                checked_at=None,
            )
        )
    check = repo.get_latest_check(db, batch.id)
    if check is None:
        return ok(
            CheckResultData(
                exam_paper_id=paper.id,
                batch_code=batch.batch_code,
                is_passed=False,
                issues=[],
                checked_at=None,
            )
        )
    return ok(
        CheckResultData(
            exam_paper_id=paper.id,
            batch_code=batch.batch_code,
            is_passed=check.is_passed,
            issues=[CheckIssue(**i) for i in (check.issues or [])],
            checked_at=check.checked_at.isoformat() if check.checked_at else None,
        )
    )
