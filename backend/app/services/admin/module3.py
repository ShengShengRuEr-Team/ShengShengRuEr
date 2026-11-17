"""模块三只读观测（默认关闭；不调用控制接口、不生成 Worker 心跳）。"""

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

#: 本仓库尚无模块三表；开启后只按显式映射探测，缺表即 missing。
TASK_TABLE = "processing_tasks"
WORKER_TABLE = "processing_workers"

_engine = None


def _engine_instance():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().database_url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 2},
        )
    return _engine


def observation_payload() -> dict:
    settings = get_settings()
    if not settings.admin_module3_observation_enabled:
        return {
            "status": "not_configured",
            "reason": "disabled",
            "tasks": None,
            "workers": None,
            "worker_liveness": "unknown",
            "source": "module3_readonly",
        }
    try:
        with _engine_instance().connect() as connection:
            present = set(
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables"
                        " WHERE table_schema='public' AND table_name = ANY(:names)"
                    ),
                    {"names": [TASK_TABLE, WORKER_TABLE]},
                ).scalars()
            )
            missing = [
                name for name in (TASK_TABLE, WORKER_TABLE) if name not in present
            ]
            if missing:
                return {
                    "status": "not_configured",
                    "reason": "missing_table",
                    "missing": missing,
                    "tasks": None,
                    "workers": None,
                    "worker_liveness": "unknown",
                    "source": "module3_readonly",
                }
            tasks = connection.execute(
                text(f"SELECT count(*) FROM {TASK_TABLE}")
            ).scalar()
            workers = connection.execute(
                text(f"SELECT count(*) FROM {WORKER_TABLE}")
            ).scalar()
            return {
                "status": "ok",
                "reason": None,
                "tasks": int(tasks or 0),
                "workers": int(workers or 0),
                # 不伪造 Worker 心跳：独立存活未知。
                "worker_liveness": "unknown",
                "source": "module3_readonly",
            }
    except Exception:  # noqa: BLE001
        return {
            "status": "error",
            "reason": "probe_failed",
            "tasks": None,
            "workers": None,
            "worker_liveness": "unknown",
            "source": "module3_readonly",
        }
