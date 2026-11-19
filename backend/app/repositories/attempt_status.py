"""API-3 仓储：count 与 latest 单条 SQL 同快照。

禁止两次查询回退（N05）：窗口函数不可用时视为实现失败，须改等效单语句，
不得用默认 READ COMMITTED 下的两条语句冒充同一快照。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models_attempt import Attempt


def get_attempt_status_row(
    db: Session, student_id: int, exam_paper_id: int
) -> tuple[Attempt, int] | None:
    """返回 (最新成功提交, 本人本卷成功总数)；无记录返回 None。"""

    stmt = (
        select(Attempt, func.count().over().label("attempt_count"))
        .where(
            Attempt.student_id == student_id,
            Attempt.exam_paper_id == exam_paper_id,
        )
        .order_by(Attempt.submitted_at.desc(), Attempt.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    attempt = row[0]
    attempt_count = int(row[1])
    return attempt, attempt_count
