"""管理端含敏感字段的题目接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_permission
from app.core.errors import not_found, ok
from app.core.permissions import QUESTION_READ_SENSITIVE
from app.db.base import get_db
from app.db.models import ListeningPaper, ListeningQuestion
from app.schemas import AdminQuestion, AdminQuestionListData, ApiResponse

router = APIRouter(prefix="/admin/papers", tags=["管理端题目"])


@router.get(
    "/{paper_id}/questions",
    response_model=ApiResponse[AdminQuestionListData],
)
def list_admin_questions(
    paper_id: int,
    current_user: CurrentUser = Depends(
        require_permission(QUESTION_READ_SENSITIVE)
    ),
    db: Session = Depends(get_db),
) -> dict:
    paper = db.get(ListeningPaper, paper_id)
    if paper is None:
        raise not_found("试卷不存在")

    questions = db.scalars(
        select(ListeningQuestion)
        .where(ListeningQuestion.paper_id == paper_id)
        .order_by(ListeningQuestion.question_no)
    ).all()
    items = [AdminQuestion.model_validate(question) for question in questions]
    return ok(AdminQuestionListData(items=items, total=len(items)))
