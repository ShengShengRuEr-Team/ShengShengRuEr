"""Student-only list, detail, audio and removal for the wrong-answer notebook."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_student
from app.core.audio_response import ranged_file_response
from app.core.config import Settings, get_settings
from app.core.errors import not_found, ok
from app.db.base import get_db
from app.repositories import wrong_answers
from app.schemas import ApiResponse
from app.schemas_wrong_answers import WrongAnswerDetail, WrongAnswerPage

router = APIRouter(prefix="/wrong-answers", tags=["错题本"])
QuestionNo = Annotated[int, Path(gt=0, le=2**31 - 1)]


@router.get("", response_model=ApiResponse[WrongAnswerPage])
def list_entries(
    response: Response,
    keyword: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=2**31 - 1),
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return ok(wrong_answers.list_entries(db, user.id, keyword.strip(), page, limit))


@router.get(
    "/{attempt_code}/{question_no}", response_model=ApiResponse[WrongAnswerDetail]
)
def get_entry(
    response: Response,
    attempt_code: UUID,
    question_no: QuestionNo,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return ok(wrong_answers.get_entry(db, user.id, attempt_code, question_no))


@router.delete("/{attempt_code}/{question_no}", response_model=ApiResponse[None])
def dismiss_entry(
    attempt_code: UUID,
    question_no: QuestionNo,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
):
    wrong_answers.dismiss_entry(db, user.id, attempt_code, question_no)
    return ok(msg="已移出错题本")


@router.get("/{attempt_code}/{question_no}/audio")
def get_entry_audio(
    request: Request,
    attempt_code: UUID,
    question_no: QuestionNo,
    user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    audio = wrong_answers.get_entry_audio(db, user.id, attempt_code, question_no)
    path = settings.audio_storage_path / audio.storage_key
    if not path.is_file():
        raise not_found("音频文件不可用")
    response = ranged_file_response(request, path, audio.mime_type)
    response.headers["Cache-Control"] = "no-store"
    return response
