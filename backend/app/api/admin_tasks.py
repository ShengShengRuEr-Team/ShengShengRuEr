"""管理端处理任务接口（一期占位实现）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_permission
from app.core.constants import DEFAULT_TASK_TYPE, TASK_STATUSES
from app.core.errors import bad_request, not_found, ok
from app.core.permissions import TASK_READ, TASK_START
from app.db.base import get_db
from app.db.models import ListeningPaper, ProcessingTask
from app.schemas import (
    ApiResponse,
    TaskCreateRequest,
    TaskListData,
    TaskListItem,
    TaskOut,
)

router = APIRouter(prefix="/admin/processing-tasks", tags=["管理端任务"])


@router.post("", response_model=ApiResponse[TaskOut])
def create_task(
    payload: TaskCreateRequest,
    current_user: CurrentUser = Depends(require_permission(TASK_START)),
    db: Session = Depends(get_db),
) -> dict:
    paper = db.get(ListeningPaper, payload.paper_id)
    if paper is None:
        raise not_found("试卷不存在")

    task = ProcessingTask(
        paper_id=paper.id,
        task_type=DEFAULT_TASK_TYPE,
        status="pending",
        progress=0,
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return ok(TaskOut.model_validate(task), "任务已创建")


@router.get("", response_model=ApiResponse[TaskListData])
def list_tasks(
    status: str | None = Query(default=None),
    current_user: CurrentUser = Depends(require_permission(TASK_READ)),
    db: Session = Depends(get_db),
) -> dict:
    if status is not None and status not in TASK_STATUSES:
        raise bad_request(f"任务状态非法：{status}")

    statement = select(ProcessingTask).order_by(ProcessingTask.id)
    if status is not None:
        statement = statement.where(ProcessingTask.status == status)
    tasks = db.scalars(statement).all()
    items = [TaskListItem.model_validate(task) for task in tasks]
    return ok(TaskListData(items=items, total=len(items)))


@router.get("/{task_id}", response_model=ApiResponse[TaskOut])
def get_task(
    task_id: int,
    current_user: CurrentUser = Depends(require_permission(TASK_READ)),
    db: Session = Depends(get_db),
) -> dict:
    task = db.get(ProcessingTask, task_id)
    if task is None:
        raise not_found("任务不存在")
    return ok(TaskOut.model_validate(task))
