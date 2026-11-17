"""健康探针：live 不连库，ready 只校验本期必需结构（§12.1/AC-34）。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

router = APIRouter(tags=["健康"])

REQUIRED_TABLES = (
    "users",
    "auth_sessions",
    "admin_login_events",
    "admin_audit_events",
    "admin_job_definitions",
    "admin_job_runs",
    "admin_job_scheduler_state",
    "exam_papers",
    "attempts",
)

_ready_engine = None


def _engine():
    global _ready_engine
    if _ready_engine is None:
        _ready_engine = create_engine(
            get_settings().database_url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
    return _ready_engine


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    try:
        engine = _engine()
        with engine.connect() as connection:
            connection.execute(text("SET statement_timeout = '2500ms'"))
            connection.execute(text("SELECT 1"))
            present = set(
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables"
                        " WHERE table_schema = 'public'"
                    )
                ).scalars()
            )
            missing = [table for table in REQUIRED_TABLES if table not in present]
            column_ok = bool(
                connection.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns"
                        " WHERE table_name='users' AND column_name='auth_version'"
                    )
                ).first()
            )
    except Exception:  # noqa: BLE001 - 不泄漏连接信息
        return JSONResponse(status_code=503, content={"status": "not_ready"})

    if missing or not column_ok:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return JSONResponse(status_code=200, content={"status": "ready"})
