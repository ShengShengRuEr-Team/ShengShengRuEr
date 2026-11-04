"""可见性操作：管理员确认可见 / 取消可见（需求 §3.3 第 3、4 条）。

- 确认可见：须最低内容检查通过；写 paper_visibility 并记 audit log。
- 取消可见：不以检查通过为前提；取消后学生列表/详情/音频均拒绝。
- 状态与操作记录持久保存；不联动修改标注审核或模块三验收状态。
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.db.models_listening import (
    ExamPaper,
    ImportBatch,
    PaperVisibility,
    VisibilityAuditLog,
)
from app.services import content_check


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_visibility(
    db: Session, paper: ExamPaper, batch: ImportBatch
) -> PaperVisibility:
    visibility = (
        db.query(PaperVisibility)
        .filter(PaperVisibility.batch_id == batch.id)
        .order_by(PaperVisibility.id.desc())
        .first()
    )
    if visibility is None:
        visibility = PaperVisibility(
            exam_paper_id=paper.id, batch_id=batch.id, is_visible=False
        )
        db.add(visibility)
        db.flush()
    return visibility


def confirm_visible(
    db: Session,
    paper: ExamPaper,
    batch: ImportBatch,
    operator_user_id: int,
    reason: str,
    audio_dir: Path,
) -> tuple[PaperVisibility, content_check.ContentCheck]:
    """确认学生可见；检查未通过时拒绝并返回具体问题。"""
    check = content_check.run_check(db, paper, batch, audio_dir)
    if not check.is_passed:
        db.commit()  # 保留检查记录，便于排查
        messages = "；".join(i["message"] for i in (check.issues or [])) or "检查未通过"
        raise bad_request(f"最低内容检查未通过，不能确认可见：{messages}")

    visibility = _get_or_create_visibility(db, paper, batch)
    visibility.is_visible = True
    visibility.confirmed_by = operator_user_id
    visibility.confirmed_at = _utc_now()
    db.add(
        VisibilityAuditLog(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            action="confirm",
            operator_user_id=operator_user_id,
            reason=reason,
        )
    )
    db.commit()
    return visibility, check


def cancel_visible(
    db: Session,
    paper: ExamPaper,
    batch: ImportBatch,
    operator_user_id: int,
    reason: str,
) -> PaperVisibility:
    """取消学生可见；不以检查通过为前提。"""
    visibility = _get_or_create_visibility(db, paper, batch)
    visibility.is_visible = False
    visibility.cancelled_by = operator_user_id
    visibility.cancelled_at = _utc_now()
    db.add(
        VisibilityAuditLog(
            exam_paper_id=paper.id,
            batch_id=batch.id,
            action="cancel",
            operator_user_id=operator_user_id,
            reason=reason,
        )
    )
    db.commit()
    return visibility
