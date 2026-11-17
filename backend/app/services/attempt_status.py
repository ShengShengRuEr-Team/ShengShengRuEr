"""API-3 服务：权限/准入后查询本人本卷状态；只读、不 commit。"""

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import attempt_status as status_repo
from app.repositories import listening as listening_repo
from app.schemas_attempt_status import AttemptStatusData
from app.schemas_attempts import MSG_E03_PAPER_NOT_ACCESSIBLE
from app.services.attempts import attempt_summary_from_attempt


def get_attempt_status(
    db: Session, *, student_id: int, exam_paper_id: int
) -> AttemptStatusData:
    visible, _paper, _batch = listening_repo.student_access(db, exam_paper_id)
    if not visible:
        # 不存在/隐藏/下线统一 404，不泄露存在性；查询失败不改变任何数据。
        raise AppError(
            404,
            MSG_E03_PAPER_NOT_ACCESSIBLE,
            headers={"Cache-Control": "no-store"},
        )

    row = status_repo.get_attempt_status_row(db, student_id, exam_paper_id)
    if row is None:
        return AttemptStatusData(
            exam_paper_id=exam_paper_id,
            submitted=False,
            attempt_count=0,
            latest_attempt=None,
        )
    attempt, attempt_count = row
    return AttemptStatusData(
        exam_paper_id=exam_paper_id,
        submitted=True,
        attempt_count=attempt_count,
        latest_attempt=attempt_summary_from_attempt(attempt),
    )
