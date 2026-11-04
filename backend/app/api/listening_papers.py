"""模块二学生接口：试卷列表、整卷详情、受控音频。

学生可见 = 当前批次 ∧ 最低内容检查通过 ∧ 管理员确认可见。学生接口只返回
学生可见字段，不含答案、解析与听力正文；不可见试卷统一返回 404，不泄露
是否存在该卷。音频访问权限与试卷访问条件一致。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.audio_response import ranged_file_response
from app.core.config import Settings, get_settings
from app.core.errors import not_found, ok
from app.db.base import get_db
from app.repositories import listening as repo
from app.schemas import ApiResponse
from app.schemas_listening import (
    PaperDetailStudent,
    PaperListData,
    PaperListItem,
)

router = APIRouter(tags=["听力试卷"])


def _paper_list_item(db: Session, paper, batch) -> PaperListItem:
    audio = repo.get_audio(db, paper.playback_audio_id)
    return PaperListItem(
        exam_paper_id=paper.id,
        exam_paper_code=paper.exam_paper_code,
        exam_level=paper.exam_level,
        exam_year=paper.exam_year,
        exam_month=paper.exam_month,
        paper_set=paper.paper_set,
        content_scope=paper.content_scope,
        audio_url=f"/api/v1/listening-papers/{paper.id}/audio",
        duration_ms=audio.duration_ms if audio else None,
    )


@router.get("/listening-papers", response_model=ApiResponse[PaperListData])
def list_listening_papers(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = repo.list_papers(db, is_admin=current_user.is_admin)
    items = [_paper_list_item(db, paper, batch) for paper, batch in rows]
    return ok(PaperListData(items=items))


@router.get("/listening-papers/{exam_paper_id}", response_model=ApiResponse[PaperDetailStudent])
def get_listening_paper(
    exam_paper_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    visible, paper, batch = repo.student_access(db, exam_paper_id)
    if not visible:
        raise not_found()
    data = repo.assemble_student_detail(db, paper, batch)
    return ok(PaperDetailStudent(**data))


@router.get("/listening-papers/{exam_paper_id}/audio")
def get_listening_paper_audio(
    exam_paper_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if current_user.is_admin:
        paper = repo.get_paper(db, exam_paper_id)
        if paper is None:
            raise not_found()
    else:
        visible, paper, _ = repo.student_access(db, exam_paper_id)
        if not visible:
            raise not_found()

    audio = repo.get_audio(db, paper.playback_audio_id)
    if audio is None:
        raise not_found("试卷未绑定音频")
    audio_path = settings.audio_storage_path / audio.storage_key
    if not audio_path.is_file():
        raise not_found("音频文件不可用")
    return ranged_file_response(request, audio_path, audio.mime_type)
