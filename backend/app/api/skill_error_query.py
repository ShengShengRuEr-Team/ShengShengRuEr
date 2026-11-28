"""Read-only admin API for skill/error lookup."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.errors import ok
from app.db.base import get_db
from app.schemas import ApiResponse
from app.schemas_skill_error_query import (
    DictionaryData,
    QuestionDetailData,
    QuestionListData,
)
from app.services.skill_error_query.dictionary import build_dictionary
from app.services.skill_error_query.questions import (
    get_question_detail,
    list_questions,
)
from app.services.skill_error_query.scope import (
    begin_read_snapshot,
    check_expected_scope,
    read_scope,
)

router = APIRouter(prefix="/admin/skill-error-query", tags=["技能与错因查询"])

DICTIONARY_DESCRIPTION = "技能表、错因表三级分类、条目详情及叶级计数"


@router.get("/dictionary", response_model=ApiResponse[DictionaryData])
def get_dictionary(
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    begin_read_snapshot(db)
    scope = read_scope(db)
    return ok(build_dictionary(db, scope))


@router.get("/questions", response_model=ApiResponse[QuestionListData])
def get_questions(
    subject_type: str = Query(
        ..., description="skill、error_cause、skill_category、error_category"
    ),
    subject_code: str = Query(..., min_length=1, max_length=64),
    role: str = Query("all", pattern="^(all|primary|auxiliary)$"),
    cursor: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    expected_scope_version: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    begin_read_snapshot(db)
    scope = read_scope(db)
    check_expected_scope(scope, expected_scope_version, cursor=cursor)
    return ok(
        list_questions(
            db,
            scope,
            subject_type,
            subject_code,
            role,
            cursor,
            limit,
        )
    )


@router.get("/questions/{question_id}", response_model=ApiResponse[QuestionDetailData])
def get_question(
    question_id: int,
    exam_paper_id: int | None = Query(default=None, gt=0),
    expected_scope_version: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    begin_read_snapshot(db)
    scope = read_scope(db)
    check_expected_scope(scope, expected_scope_version)
    return ok(get_question_detail(db, scope, question_id, exam_paper_id))
