"""Student notebook list, protected detail and review state."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_student
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ok
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_wrong_answers import (
    WrongAnswerDetail,
    WrongAnswerItem,
    WrongAnswerPage,
    WrongAnswerPatch,
    WrongAnswerQuery,
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
    request: Request,
    filters: Annotated[WrongAnswerQuery, Query()],
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if len(request.query_params.multi_items()) != len(request.query_params):
        raise AppError(422, "错题筛选参数不能重复")
    return ok(wrong_answers.list_entries(db, user.id, settings, **filters.model_dump()))


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
