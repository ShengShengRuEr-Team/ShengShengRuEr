"""Read-only progress and Windows process ownership for the standalone console."""

from __future__ import annotations

import ctypes
import json
import subprocess
from datetime import UTC, datetime

from sqlalchemy import select

PHASES = ("align", "assemble", "annotate_sample", "annotate", "persist")
LABELS = ("原文与对齐", "题目组装", "5题试标", "整套标注", "审核入库")
STEPS = {
    "align": ("preflight", "extract", "normalize", "reference", "align"),
    "assemble": ("assemble",),
    "annotate_sample": ("annotate",),
    "annotate": ("annotate",),
    "persist": ("persist",),
}
NEXT = {
    "registered": "等待处理进程领取",
    "preflight": "提取听力原文",
    "extract": "准备音频",
    "normalize": "整理参考原文",
    "reference": "对齐音频与原文",
    "align": "组装题目与解析",
    "assemble": "生成技能与证据标注",
    "annotate": "核验并写入待审批次",
}


def process_tree(pid):
    # Fixed read-only CIM query; no credentials or environment values are read.
    command = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=True,
    )
    rows = json.loads(result.stdout or "[]")
    if isinstance(rows, dict):
        rows = [rows]
    root = next((r for r in rows if r["ProcessId"] == pid), None)
    if not root or not any(
        marker in (root.get("CommandLine") or "")
        for marker in (
            "app.module3.worker",
            "module3-console-20261110\\console_worker.py",
            "module3-console-20261110/console_worker.py",
        )
    ):
        raise RuntimeError("无法确认本工作台处理进程的身份，未终止任何进程")
    descendants = {pid}
    while True:
        added = {r["ProcessId"] for r in rows if r["ParentProcessId"] in descendants}
        if added <= descendants:
            break
        descendants |= added
    return descendants


class AdoptedWorker:
    """Keep an already running worker alive across this console's UI upgrade."""

    def __init__(self, pid):
        process_tree(pid)
        self.pid = pid
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        self.handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        if not self.handle:
            raise RuntimeError("处理进程已经退出")

    def poll(self):
        code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(
            ctypes.c_void_p(self.handle), ctypes.byref(code)
        ):
            return 1
        return None if code.value == 259 else code.value


def kill_worker_tree(worker, owner=None):
    if worker is None or worker.poll() is not None:
        if owner:
            raise RuntimeError("原处理进程不在线，请先刷新状态")
        return
    members = process_tree(worker.pid)
    if owner and int(owner.rsplit(":", 1)[-1]) not in members:
        raise RuntimeError("该任务不属于本工作台处理进程，未终止其他任务")
    result = subprocess.run(
        ["taskkill.exe", "/PID", str(worker.pid), "/T", "/F"],
        capture_output=True,
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode and worker.poll() is None:
        raise RuntimeError("处理进程尚未停止，请重试")


def seconds(start, end):
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    return max(0, round((end - start).total_seconds()))


def progress(job, db, models, data):
    current_time = datetime.now(UTC)
    history = job.get("history", [])
    ids = [h["task_id"] for h in history if h.get("task_id")]
    rows = (
        list(
            db.scalars(
                select(models.ProcessingTask).where(models.ProcessingTask.id.in_(ids))
            )
        )
        if ids
        else []
    )
    by_id = {str(t.id): t for t in rows}
    latest = by_id.get(job.get("task_id"))
    current = (
        PHASES.index(job["phase"])
        if job["phase"] in PHASES
        else (5 if job["phase"] == "completed" else -1)
    )
    items = []
    for index, (phase, label) in enumerate(zip(PHASES, LABELS, strict=True)):
        entry = next((h for h in reversed(history) if h["phase"] == phase), None)
        task = (
            latest
            if index == current
            else by_id.get(entry["task_id"])
            if entry
            else None
        )
        state, detail, completed, total = (
            "waiting",
            "等待前序流程",
            0,
            len(STEPS[phase]),
        )
        measured_count = measured_total = None
        if index < current:
            state, detail, completed = "complete", "已完成", total
        elif index == current and task:
            artifacts = set(
                db.scalars(
                    select(models.ProcessingArtifact.stage).where(
                        models.ProcessingArtifact.task_id == task.id
                    )
                )
            )
            completed = sum(s in artifacts for s in STEPS[phase])
            blocked = task.state == "failed" or any(
                i.get("severity") == "error" for i in task.issues
            )
            if job.get("stopped"):
                state, detail = "stopped", "已停止，材料和已有结果保留"
            elif blocked or job.get("error"):
                state, detail = "failed", "处理受阻，请查看问题后重试"
                if task.stage in STEPS[phase] and task.stage in artifacts:
                    completed = max(0, completed - 1)
            elif (
                task.state in {"awaiting_confirmation", "completed"}
                and phase != "persist"
            ):
                state, detail, completed = "review", "处理完成，等待你的复核", total
            elif task.state == "pending":
                state, detail = "pending", "排队中，尚未开始执行"
            else:
                state, detail = "running", NEXT.get(task.stage, "正在处理")
                if phase == "align" and job.get("alignment_revision"):
                    detail = "正在局部重对齐；复用原文、音频与未改动片段，不重复整套OCR"
                if phase in {"annotate_sample", "annotate"}:
                    qids = set()
                    for row in db.scalars(
                        select(models.ProcessingArtifact).where(
                            models.ProcessingArtifact.task_id == task.id,
                            models.ProcessingArtifact.stage == "annotate",
                        )
                    ):
                        path = (data / "artifacts" / row.storage_key).resolve()
                        if (
                            path.is_relative_to((data / "artifacts").resolve())
                            and path.is_file()
                        ):
                            value = json.loads(path.read_text(encoding="utf-8"))
                            if value.get("question_src_id"):
                                qids.add(value["question_src_id"])
                    parent_id = task.request.get("reuse_assembly_task_id")
                    draft = (
                        db.scalar(
                            select(models.ProcessingDraft)
                            .where(models.ProcessingDraft.task_id == parent_id)
                            .limit(1)
                        )
                        if parent_id
                        else None
                    )
                    measured_count = len(qids)
                    measured_total = (
                        5
                        if phase == "annotate_sample"
                        else len(draft.payload["questions"])
                        if draft
                        else None
                    )
                    detail = (
                        f"已生成并校验 {len(qids)}"
                        + (f" / {measured_total}" if measured_total else "")
                        + " 题；正在继续标注或阶段检查"
                    )
                if phase in {"align", "assemble"}:
                    folder = (
                        data
                        / "artifacts"
                        / str(task.id)
                        / ("documents" if phase == "align" else "assembly-documents")
                    )
                    count = len(list((folder / "reference-pages").glob("*.json")))
                    if not count:
                        count = len(list((folder / "page-results").glob("*.json")))
                    if count and (phase == "assemble" or "extract" not in artifacts):
                        detail = f"原文提取：已完成 {count} 页；正在继续识别或整理"
        if job.get("stopped") and index > current:
            detail = "已停止，不再执行"
        elapsed = (
            seconds(
                task.created_at,
                task.updated_at
                if task.state not in {"running", "pending"}
                else current_time,
            )
            if task
            else None
        )
        items.append(
            {
                "phase": phase,
                "label": label,
                "state": state,
                "detail": detail,
                "completed_steps": completed,
                "total_steps": total,
                "elapsed_seconds": elapsed,
                "measured_count": measured_count,
                "measured_total": measured_total,
            }
        )
    heartbeat_age = (
        seconds(latest.heartbeat_at, current_time)
        if latest and latest.heartbeat_at and latest.state == "running"
        else None
    )
    return {
        "stages": items,
        "heartbeat_age_seconds": heartbeat_age,
        "elapsed_seconds": seconds(
            job["created_at"],
            job.get("stopped_at")
            or (job["updated_at"] if job["phase"] == "completed" else current_time),
        ),
        "can_stop": not job.get("stopped") and job["phase"] != "completed",
    }
