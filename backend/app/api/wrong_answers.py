"""Student notebook list, protected detail and review state."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_student
from app.core.config import Settings, get_settings
from app.core.errors import ok
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_wrong_answers import (
    LearningStatus,
    NotebookVisibility,
    WrongAnswerDetail,
    WrongAnswerItem,
    WrongAnswerPage,
    WrongAnswerPatch,
    WrongAnswerType,
)
from app.services import wrong_answers

NOTEBOOK_PATH = "/wrong-answers"
router = APIRouter(prefix=NOTEBOOK_PATH, tags=["错题本"])
QuestionNo = Annotated[int, Path(gt=0, le=2**31 - 1)]


def is_notebook_path(path: str) -> bool:
    prefix = f"/api/v1{NOTEBOOK_PATH}"
    return path == prefix or path.startswith(prefix + "/")


@router.get("", response_model=ApiResponse[WrongAnswerPage])
def list_entries(
    page: int = Query(default=1, ge=1, le=2**31 - 1),
    limit: int = Query(default=20, ge=1, le=100),
    exam_paper_id: int | None = Query(default=None, gt=0, le=2**63 - 1),
    answer_type: WrongAnswerType | None = None,
    learning_status: LearningStatus | None = None,
    visibility: NotebookVisibility = "visible",
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return ok(
        wrong_answers.list_entries(
            db,
            user.id,
            settings,
            page=page,
            limit=limit,
            exam_paper_id=exam_paper_id,
            answer_type=answer_type,
            learning_status=learning_status,
            visibility=visibility,
        )
    )


@router.get(
    "/{attempt_code}/{question_no}", response_model=ApiResponse[WrongAnswerDetail]
)
def get_entry(
    attempt_code: UUID,
    question_no: QuestionNo,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return ok(wrong_answers.get_entry(db, user.id, attempt_code, question_no, settings))


@router.patch(
    "/{attempt_code}/{question_no}", response_model=ApiResponse[WrongAnswerItem]
)
def update_entry(
    attempt_code: UUID,
    question_no: QuestionNo,
    patch: WrongAnswerPatch,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return ok(
        wrong_answers.update_entry(
            db, user.id, attempt_code, question_no, settings, patch
        ),
        msg="已更新错题状态",
    )
