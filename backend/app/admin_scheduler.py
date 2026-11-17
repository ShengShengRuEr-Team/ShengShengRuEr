"""独立留存调度进程入口：``python -m app.admin_scheduler``。

- 不嵌入 API lifespan，不启动模块三 Worker；
- 每 15 秒独立心跳（清理执行期间由独立线程持续写入）；
- 调度 tick 通过 session 级 advisory lock 保证互斥；
- API 是否 ready 与本进程无关，监控页按心跳展示 ok/stale/not_configured。
"""

import logging
import signal
import threading
import uuid
from datetime import datetime

from app.core.admin_jobs import HEARTBEAT_INTERVAL_SECONDS, JOB_ID
from app.core.security import utc_now
from app.db.base import SessionLocal
from app.db.models_admin import AdminJobSchedulerState
from app.services.admin import jobs as jobs_service

logger = logging.getLogger(__name__)


def write_heartbeat(
    instance_id: uuid.UUID,
    booted_at: datetime,
    *,
    state: str = "idle",
    last_error_code: str | None = None,
) -> None:
    """独立连接写入/更新本实例心跳；失败不抛出到主循环。"""

    with SessionLocal() as db:
        row = db.get(AdminJobSchedulerState, instance_id)
        now = utc_now()
        if row is None:
            db.add(
                AdminJobSchedulerState(
                    instance_id=instance_id,
                    booted_at=booted_at,
                    heartbeat_at=now,
                    last_error_code=last_error_code,
                    state=state,
                    version=1,
                )
            )
        else:
            row.heartbeat_at = now
            row.state = state
            row.last_error_code = last_error_code
        db.commit()


def _heartbeat_loop(
    instance_id: uuid.UUID,
    booted_at: datetime,
    stop_event: threading.Event,
    runtime: dict,
) -> None:
    while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
        try:
            write_heartbeat(
                instance_id,
                booted_at,
                state=runtime.get("state", "idle"),
                last_error_code=runtime.get("last_error_code"),
            )
        except Exception:  # noqa: BLE001 - 心跳失败不影响调度主循环
            logger.exception("调度心跳写入失败 instance_id=%s", instance_id)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    instance_id = uuid.uuid4()
    booted_at = utc_now()
    stop_event = threading.Event()
    runtime: dict = {"state": "idle", "last_error_code": None}

    def _stop(signum, frame) -> None:  # noqa: ANN001
        logger.info("收到退出信号 %s，停止调度", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        write_heartbeat(instance_id, booted_at, state="idle")
    except Exception:  # noqa: BLE001
        logger.exception("首次心跳写入失败")

    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(instance_id, booted_at, stop_event, runtime),
        name="admin-scheduler-heartbeat",
        daemon=True,
    )
    heartbeat.start()
    logger.info("留存调度启动 instance_id=%s job_id=%s", instance_id, JOB_ID)

    while not stop_event.is_set():
        runtime["state"] = "running"
        try:
            result = jobs_service.tick()
            runtime["state"] = "idle"
            if result.get("executed"):
                logger.info("留存执行完成 run_id=%s", result["executed"])
        except Exception:  # noqa: BLE001
            runtime["last_error_code"] = "tick_failed"
            runtime["state"] = "idle"
            logger.exception("调度 tick 失败")
        stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    stop_event.set()
    heartbeat.join(timeout=2)
    logger.info("留存调度已停止 instance_id=%s", instance_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
