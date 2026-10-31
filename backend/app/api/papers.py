"""学生可访问的试卷与题目接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_permission
from app.core.errors import not_found, ok
from app.core.permissions import PAPER_READ, QUESTION_READ
from app.db.base import get_db
from app.db.models import ListeningPaper, ListeningQuestion
from app.schemas import (
    ApiResponse,
    PaperListData,
    PaperOut,
    StudentQuestion,
    StudentQuestionListData,
)

router = APIRouter(tags=["试卷与题目"])


@router.get("/papers", response_model=ApiResponse[PaperListData])
def list_papers(
    current_user: CurrentUser = Depends(require_permission(PAPER_READ)),
    db: Session = Depends(get_db),
) -> dict:
    statement = select(ListeningPaper).order_by(ListeningPaper.id)
    # 一期只有 admin/student 两个角色，公开范围由角色决定：
    # admin 读全部，student 仅读已发布。5 个权限码中没有"读全部试卷"这一项，
    # 若以后新增可读未发布试卷的角色，应先新增独立权限码，不能复用 paper:read。
    if not current_user.is_admin:
        statement = statement.where(ListeningPaper.is_visible.is_(True))
    papers = db.scalars(statement).all()
    items = [PaperOut.model_validate(paper) for paper in papers]
    return ok(PaperListData(items=items, total=len(items)))


@router.get(
    "/papers/{paper_id}/questions",
    response_model=ApiResponse[StudentQuestionListData],
)
def list_student_questions(
    paper_id: int,
    current_user: CurrentUser = Depends(require_permission(QUESTION_READ)),
    db: Session = Depends(get_db),
) -> dict:
    paper = db.get(ListeningPaper, paper_id)
    if paper is None:
        raise not_found("试卷不存在")
    if not current_user.is_admin and not paper.is_visible:
        # 学生不可通过题目接口探测未发布试卷。
        raise not_found("试卷不存在")

    questions = db.scalars(
        select(ListeningQuestion)
        .where(ListeningQuestion.paper_id == paper_id)
        .order_by(ListeningQuestion.question_no)
    ).all()
    items = [StudentQuestion.model_validate(question) for question in questions]
    return ok(StudentQuestionListData(items=items, total=len(items)))
