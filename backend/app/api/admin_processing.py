"""Administrator-only material, processing and immutable result APIs."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_admin
from app.core.config import Settings, get_settings
from app.core.errors import AppError, not_found, ok
from app.db import models_processing as m
from app.db.base import get_db
from app.db.models_listening import ImportBatch
from app.schemas_processing import (
    ActivationRequest,
    CheckRequest,
    CorrectionRequest,
    MaterialRequest,
    RetryRequest,
    ReviewRequest,
    TaskRequest,
)
from app.services.processing import tasks

router = APIRouter(tags=["自动处理与入库"])


def row_data(row, *, exclude=()):
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in exclude
    }


def task_data(task):
    return row_data(task, exclude=("lease_token", "request", "method", "worker_id"))


@router.post("/admin/materials", status_code=201)
def register_material(
    payload: MaterialRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    material = tasks.register_material(db, payload, user.id, settings)
    db.commit()
    return {"code": 201, "msg": "材料已登记", "data": row_data(material)}


@router.get("/admin/materials/{material_id}")
def get_material(
    material_id: int,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    material = db.get(m.MaterialSource, material_id)
    if material is None:
        raise not_found()
    return ok(row_data(material))


@router.post("/admin/processing-tasks", status_code=202)
def create_task(
    payload: TaskRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    task = tasks.create_task(db, payload, user.id, settings)
    db.commit()
    return {"code": 202, "msg": "处理任务已保存", "data": task_data(task)}


@router.get("/admin/processing-tasks")
def list_tasks(
    exam_paper_code: str | None = None,
    state: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(m.ProcessingTask)
    if exam_paper_code:
        stmt = stmt.where(m.ProcessingTask.exam_paper_code == exam_paper_code)
    if state:
        stmt = stmt.where(m.ProcessingTask.state == state)
    if cursor:
        try:
            timestamp, task_id = cursor.split("|", 1)
            created = datetime.fromisoformat(timestamp)
            parsed_id = UUID(task_id)
        except ValueError:
            raise AppError(422, "分页游标无效") from None
        stmt = stmt.where(
            or_(
                m.ProcessingTask.created_at < created,
                and_(
                    m.ProcessingTask.created_at == created,
                    m.ProcessingTask.id < parsed_id,
                ),
            )
        )
    rows = db.scalars(
        stmt.order_by(
            m.ProcessingTask.created_at.desc(), m.ProcessingTask.id.desc()
        ).limit(limit + 1)
    ).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].created_at.isoformat() + "|" + str(rows[-1].id)
    return ok({"items": [task_data(r) for r in rows], "next_cursor": next_cursor})


@router.get("/admin/processing-tasks/{task_id}")
def get_task(
    task_id: UUID,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ok(task_data(tasks.get_task(db, task_id)))


@router.get("/admin/processing-tasks/{task_id}/result")
def get_result(
    task_id: UUID,
    view: str = Query(default="final", pattern="^(auto_draft|final)$"),
    section: str | None = None,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    task = tasks.get_task(db, task_id)
    draft = tasks.get_draft(db, task, view)
    if draft is None:
        return ok({"task_id": task.id, "view": view, "missing": True})
    result = draft.payload
    if section:
        if section not in result:
            raise not_found("结果段落不存在")
        result = result[section]
        if isinstance(result, list):
            result = {
                "items": result[cursor : cursor + limit],
                "next_cursor": cursor + limit if len(result) > cursor + limit else None,
            }
    return ok(
        {
            "task_id": task.id,
            "view": view,
            "missing": False,
            "result_hash": draft.result_hash,
            "result": result,
        }
    )


@router.get("/admin/processing-tasks/{task_id}/diff")
def get_diff(
    task_id: UUID,
    baseline_task_id: UUID | None = None,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    task = tasks.get_task(db, task_id)
    base = tasks.get_task(db, baseline_task_id) if baseline_task_id else task
    if base.exam_paper_code != task.exam_paper_code:
        raise AppError(409, "不可跨试卷比较草稿")
    before = tasks.get_draft(db, base, "final" if baseline_task_id else "auto_draft")
    after = tasks.get_draft(db, task)
    if before is None or after is None:
        return ok({"missing": True, "changes": []})
    changes = []
    for key in sorted(set(before.payload) | set(after.payload)):
        if before.payload.get(key) != after.payload.get(key):
            changes.append(
                {
                    "section": key,
                    "before": before.payload.get(key),
                    "after": after.payload.get(key),
                }
            )
    return ok(
        {
            "before_hash": before.result_hash,
            "after_hash": after.result_hash,
            "changes": changes,
        }
    )


@router.post("/admin/processing-tasks/{task_id}/checks")
def run_checks(
    task_id: UUID,
    payload: CheckRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    check = tasks.check_result(db, task_id, payload.expected_result_hash, settings)
    db.commit()
    return ok(row_data(check))


@router.post("/admin/processing-tasks/{task_id}/reviews")
def review(
    task_id: UUID,
    payload: ReviewRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = tasks.record_review(db, task_id, payload, user)
    db.commit()
    return ok(row_data(row))


@router.post("/admin/processing-tasks/{task_id}/corrections", status_code=202)
def correct(
    task_id: UUID,
    payload: CorrectionRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    task = tasks.correct_task(db, task_id, payload, user.id)
    db.commit()
    return {"code": 202, "msg": "已建立独立修订任务", "data": task_data(task)}


@router.post("/admin/processing-tasks/{task_id}/retries", status_code=202)
def retry(
    task_id: UUID,
    payload: RetryRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    task = tasks.retry_task(db, task_id, payload, user.id, settings)
    db.commit()
    return {"code": 202, "msg": "已建立独立重试任务", "data": task_data(task)}


@router.get("/admin/listening-papers/{exam_paper_id}/batches")
def list_batches(
    exam_paper_id: int,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.exam_paper_id == exam_paper_id, ImportBatch.id > cursor)
        .order_by(ImportBatch.id)
        .limit(limit + 1)
    ).all()
    return ok(
        {
            "items": [row_data(r) for r in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }
    )


@router.post("/admin/listening-papers/{exam_paper_id}/current-batch")
def activate_batch(
    exam_paper_id: int,
    payload: ActivationRequest,
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = tasks.activate(db, exam_paper_id, payload, user.id)
    db.commit()
    return ok(result)
