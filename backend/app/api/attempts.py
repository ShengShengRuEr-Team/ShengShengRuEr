"""API-1：学生提交整卷作答。

路由层职责（判定顺序 2.6.2 的第 1–3 步）：
- 认证 401、角色 403 由 ``require_student`` 依赖完成（先于请求体校验）；
- 路径参数 ``PathId`` 允许整数文本转换，并校验正数与 BIGINT 上限；
- 请求体由 T02 的 ``AttemptSubmitIn`` 严格解析；
- ``Idempotency-Key`` 仅接受 UUIDv4 规范字符串（E05 400），随后交给服务编排。

本层不写库、不做业务判定；错误外壳复用既有 ``AppError`` 处理器。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_student
from app.core.config import Settings, get_settings
from app.core.errors import bad_request, ok
from app.db.base import get_db
from app.schemas_attempts import (
    MSG_E05_INVALID_IDEMPOTENCY_KEY,
    MSG_E12_SUCCESS,
    AttemptSubmitIn,
    AttemptSubmitResponse,
    validate_idempotency_key,
)
from app.services import attempts as attempts_service

router = APIRouter(tags=["作答提交"])

# 路径参数：允许 FastAPI/Pydantic 将路径数字文本转换为 int，范围仍受约束。
PathId = Annotated[int, Path(gt=0, le=2**63 - 1)]


@router.post(
    "/listening-papers/{exam_paper_id}/attempts",
    response_model=AttemptSubmitResponse,
)
def submit_attempt(
    exam_paper_id: PathId,
    payload: AttemptSubmitIn,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key")
    ] = None,
    current_user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """提交整卷作答；同键重试返回原结果，不新增记录。"""

    if not validate_idempotency_key(idempotency_key):
        raise bad_request(MSG_E05_INVALID_IDEMPOTENCY_KEY)

    data = attempts_service.submit_attempt(
        db,
        student_id=current_user.id,
        exam_paper_id=exam_paper_id,
        idempotency_key=idempotency_key,
        payload=payload,
        settings=settings,
    )
    return ok(data, msg=MSG_E12_SUCCESS)
