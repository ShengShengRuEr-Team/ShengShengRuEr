"""留存调度查询与行锁（主文档 §10.1）。"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.admin_jobs import JOB_ID
from app.db.models_admin import (
    AdminJobDefinition,
    AdminJobRun,
    AdminJobSchedulerState,
)


def get_definition(db: Session) -> AdminJobDefinition | None:
    return db.get(AdminJobDefinition, JOB_ID)


def lock_definition(db: Session) -> AdminJobDefinition:
    """行锁读取唯一任务定义；随后重验 active_run_id。"""

    definition = db.scalar(
        select(AdminJobDefinition)
        .where(AdminJobDefinition.job_id == JOB_ID)
        .with_for_update()
    )
    if definition is None:  # pragma: no cover - 迁移已 seed
        raise RuntimeError("缺少 admin.retention_cleanup 任务定义")
    return definition


def get_run(db: Session, run_id: uuid.UUID) -> AdminJobRun | None:
    return db.get(AdminJobRun, run_id)


def list_runs(
    db: Session, *, page: int, page_size: int
) -> tuple[list[AdminJobRun], int]:
    stmt = select(AdminJobRun).where(AdminJobRun.job_id == JOB_ID)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(AdminJobRun.created_at.desc(), AdminJobRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), int(total or 0)


def list_schedulers(db: Session) -> list[AdminJobSchedulerState]:
    return list(
        db.scalars(
            select(AdminJobSchedulerState).order_by(
                AdminJobSchedulerState.heartbeat_at.desc()
            )
        ).all()
    )


def queued_retry_due(
    db: Session, *, now: datetime
) -> AdminJobRun | None:
    return db.scalar(
        select(AdminJobRun)
        .where(
            AdminJobRun.job_id == JOB_ID,
            AdminJobRun.state == "QUEUED",
        )
        .order_by(AdminJobRun.queued_at.asc().nulls_first(), AdminJobRun.created_at)
        .limit(1)
    )


def active_run(db: Session) -> AdminJobRun | None:
    return db.scalar(
        select(AdminJobRun).where(
            AdminJobRun.job_id == JOB_ID,
            AdminJobRun.state.in_(("QUEUED", "RUNNING")),
        )
    )
