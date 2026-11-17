"""API-3：本人本卷提交状态。

- 仅学生；管理员 403；未登录 401；不可访问 404（认证→角色→准入→查询）。
- 只读：不 commit、不写审计/拒绝表；不返回逐题/答案/解析/正文/内部 ID。
- `Cache-Control: no-store`（成功与 404 均带）。
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.attempts import PathId
from app.api.deps import CurrentUser, require_student
from app.core.errors import ok
from app.db.base import get_db
from app.schemas_attempt_status import MSG_STATUS_SUCCESS, AttemptStatusResponse
from app.services.attempt_status import get_attempt_status

router = APIRouter(tags=["作答状态"])


@router.get(
    "/listening-papers/{exam_paper_id}/attempt-status",
    response_model=AttemptStatusResponse,
)
def read_attempt_status(
    exam_paper_id: PathId,
    response: Response,
    current_user: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
) -> dict:
    """查询本人本卷是否已提交及最新汇总；无记录表示可作答。"""

    response.headers["Cache-Control"] = "no-store"
    data = get_attempt_status(
        db, student_id=current_user.id, exam_paper_id=exam_paper_id
    )
    return ok(data, msg=MSG_STATUS_SUCCESS)
