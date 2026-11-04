"""模块二管理员接口：配套内容、可见性操作、检查结果。

仅管理员可调用（require_admin，先 401 后 403）；本期所有管理员可管理全部
题库，不按导入人限制。状态字段（当前批次、最低内容检查、可见性）分别表示，
不合并为一个“完成”状态。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import bad_request, not_found, ok
from app.db.base import get_db
from app.repositories import listening as repo
from app.schemas import ApiResponse
from app.schemas_listening import (
    CheckIssue,
    CheckResultData,
    PaperCompanionAdmin,
    VisibilityActionRequest,
    VisibilityStateData,
)
from app.services import visibility as visibility_service

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
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    paper = _get_paper_or_404(db, exam_paper_id)
    batch = repo.get_current_batch(db, exam_paper_id)
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
    paper = _get_paper_or_404(db, exam_paper_id)
    batch = repo.get_current_batch(db, exam_paper_id)
    if batch is None:
        raise bad_request("当前没有可用批次，无法操作可见性")

    if payload.action == "confirm":
        visibility, check = visibility_service.confirm_visible(
            db, paper, batch, current_user.id, payload.reason, settings.audio_storage_path
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


@router.get(
    "/admin/listening-papers/{exam_paper_id}/checks",
    response_model=ApiResponse[CheckResultData],
)
def get_checks(
    exam_paper_id: int,
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    paper = _get_paper_or_404(db, exam_paper_id)
    batch = repo.get_current_batch(db, exam_paper_id)
    if batch is None:
        return ok(
            CheckResultData(
                exam_paper_id=paper.id, batch_code=None, is_passed=False, issues=[], checked_at=None
            )
        )
    check = repo.get_latest_check(db, batch.id)
    if check is None:
        return ok(
            CheckResultData(
                exam_paper_id=paper.id, batch_code=batch.batch_code, is_passed=False,
                issues=[], checked_at=None,
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
