"""Read-only progress from committed checkpoints and current OCR page outputs."""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models_processing import ProcessingArtifact
from app.db.models_processing_workflows import ProcessingWorkflowCommand
from app.module3.contracts import ProcessingError, controlled_path

DESCRIPTIONS = {
    "registered": "等待 Worker 领取任务",
    "preflight": "检查处理环境和原件身份",
    "extract": "提取原卷与解析内容",
    "normalize": "解码并规范化原始音频",
    "reference": "整理听力原文和题组",
    "align": "计算原文与原音的对应时间",
    "reuse": "读取已确认的对齐结果",
    "assemble": "整理题干、选项、答案和解析",
    "annotate_sample": "生成前5题试标结果",
    "annotate": "生成整套技能、答案证据和错因标注",
    "review": "等待整套逐题审核",
    "publish": "校验并写入正式批次",
}
WAITING = {
    "awaiting_alignment": "对齐已完成，等待核听确认",
    "awaiting_source": "来源整理已完成，等待核对题干、选项、答案和解析",
    "awaiting_sample": "前5题试标已完成，等待语义复核",
    "awaiting_review": "整套结果已完成，等待逐题审核",
}


def read_json(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("progress input too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("progress object required")
    return value


def ocr_progress(task, settings, artifact_stages):
    root = settings.m3_path("m3_artifacts_dir")
    for folder, checkpoint in (
        ("assembly-documents", "assembly_extract"),
        ("documents", "extract"),
    ):
        if checkpoint in artifact_stages:
            continue
        try:
            prefix = f"{task.id}/{folder}"
            directory = controlled_path(root, prefix, must_exist=False)
            manifest = read_json(controlled_path(root, prefix + "/input-manifest.json"))
            if manifest.get("task_id") != str(task.id):
                continue
            # Once the OCR process has returned, the following assembly/refinement
            # is a separate step; completed pages do not imply a completed task.
            if (directory / "extracted.json").is_file():
                continue
            pairs = []
            known_total = True
            for material in manifest.get("files", []):
                identity = material["material_id"]
                if (
                    type(identity) is not int
                    or identity not in task.request["material_ids"]
                ):
                    raise ValueError("unbound progress material")
                pages = material.get("page_numbers")
                if not pages:
                    known_total = False
                    continue
                if len(pages) > 500 or any(
                    type(n) is not int or not 1 <= n <= 500 for n in pages
                ):
                    raise ValueError("invalid progress page selection")
                pairs.extend((identity, n) for n in pages)
            pairs = list(dict.fromkeys(pairs))
            completed, current = 0, None
            updated = None
            for identity, number in pairs:
                name = f"{identity}-{number}"
                finished = False
                for subfolder in ("page-results", "reference-pages"):
                    try:
                        path = controlled_path(
                            root, f"{prefix}/{subfolder}/{name}.json"
                        )
                        value = read_json(path)
                        if (
                            value.get("material_id") == identity
                            and value.get("page") == number
                        ):
                            finished = True
                            stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                            updated = max(updated, stamp) if updated else stamp
                            break
                    except (OSError, ValueError, ProcessingError):
                        continue
                completed += finished
                image = controlled_path(
                    root, f"{prefix}/pages/{name}.png", must_exist=False
                )
                if not finished and image.is_file() and current is None:
                    current = f"原件第 {number} 页"
            return {
                "stage": "assembly_extract"
                if folder == "assembly-documents"
                else "extract",
                "description": "识别答案解析 PDF，提取答案与解析"
                if folder == "assembly-documents"
                else "识别原件 PDF，提取听力内容",
                "completed_count": completed,
                "total_count": len(pairs) if known_total and pairs else None,
                "unit": "页",
                "current_item": current,
                "last_progress_at": updated,
            }
        except (OSError, ValueError, KeyError, TypeError, ProcessingError):
            continue
    return None


def workflow_progress(db, workflow, task, materials, now, settings, revision):
    command = db.scalar(
        select(ProcessingWorkflowCommand)
        .where(
            ProcessingWorkflowCommand.workflow_id == workflow.id,
            ProcessingWorkflowCommand.revision_id == workflow.current_revision_id,
            ProcessingWorkflowCommand.action.in_(
                ("start", "continue", "retry", "publish")
            ),
        )
        .order_by(ProcessingWorkflowCommand.created_at.desc())
        .limit(1)
    )
    publishing = bool(command and command.result.get("stage") == "publish")
    active = bool(
        command
        and command.state == "running"
        and command.lease_expires_at
        and command.lease_expires_at > now
        and workflow.processing_state == "running"
    )
    rows = (
        db.scalars(
            select(ProcessingArtifact)
            .where(ProcessingArtifact.task_id == task.id)
            .order_by(ProcessingArtifact.id)
        ).all()
        if task
        else []
    )
    started = command.created_at if publishing else task.created_at if task else None
    ended = command.updated_at if publishing else task.updated_at if task else now
    latest = rows[-1] if rows else None
    stage = (
        "publish"
        if publishing
        else task.request.get("workflow_stage", task.stage)
        if task
        else "materials"
    )
    result = {
        "stage": stage,
        "description": DESCRIPTIONS.get(stage, "准备处理材料"),
        "completed_count": sum(r["state"] == "ready" for r in materials)
        if not task
        else 0,
        "total_count": 3 if not task else None,
        "unit": "份" if not task else "项",
        "current_item": None,
        "active": active,
        "observed_at": now,
        "started_at": started,
        "last_progress_at": latest.created_at if latest else None,
        "elapsed_ms": max(
            0, int(((now if active else ended) - started).total_seconds() * 1000)
        )
        if started
        else 0,
        "checkpoint": latest.stage if latest else None,
    }
    if task and not publishing:
        stages = {r.stage for r in rows}
        if active:
            result.update(ocr_progress(task, settings, stages) or {})
            if result["stage"] in {"align", "assemble"} and task.stage != "registered":
                result["stage"] = task.stage
                result["description"] = DESCRIPTIONS.get(
                    task.stage, DESCRIPTIONS[stage]
                )
                if (
                    task.stage == "reuse"
                    and (
                        settings.m3_path("m3_artifacts_dir")
                        / str(task.id)
                        / "assembly-documents/extracted.json"
                    ).is_file()
                ):
                    result.update(
                        stage="assemble", description=DESCRIPTIONS["assemble"]
                    )
        if stage in {"annotate", "annotate_sample"}:
            reused = set()
            if stage == "annotate":
                from app.services.processing.orchestration import artifact_payload

                projections = [(revision.stage_fingerprints.get("sample"), None)]
                plan = task.request.get("repair_plan", {})
                if task.request.get("reuse_final_projection"):
                    projections.append(
                        (
                            task.request["reuse_final_projection"],
                            set(plan.get("reusable_question_ids", [])),
                        )
                    )
                for projection, allowed in projections:
                    if not projection:
                        continue
                    try:
                        payload, artifact = artifact_payload(
                            db, projection["artifact_id"], settings
                        )
                        if artifact.artifact_hash == projection["artifact_hash"]:
                            reused.update(
                                r["question_src_id"]
                                for r in payload.get("generation_receipts", [])
                                if allowed is None or r["question_src_id"] in allowed
                            )
                    except (OSError, ValueError, KeyError, ProcessingError):
                        continue
            result.update(
                completed_count=len(reused)
                + sum(r.stage == "workflow_candidate" for r in rows),
                total_count=5
                if stage == "annotate_sample"
                else task.request.get("expected_question_count"),
                unit="题",
            )
    if (
        workflow.processing_state == "running"
        and command
        and command.state == "running"
        and not active
    ):
        result["description"] = "处理心跳已过期，等待恢复检查"
    elif workflow.processing_state in WAITING:
        result.update(description=WAITING[workflow.processing_state], active=False)
        if task and workflow.processing_state in {
            "awaiting_source",
            "awaiting_sample",
            "awaiting_review",
        }:
            total = (
                5
                if workflow.processing_state == "awaiting_sample"
                else task.request.get("expected_question_count")
            )
            result.update(completed_count=total or 0, total_count=total, unit="题")
    elif workflow.processing_state == "queued":
        result.update(description="任务已排队，等待 Worker 领取", active=False)
    elif workflow.processing_state in {"failed", "stopped", "stopping"}:
        result["description"] = {
            "failed": "处理失败，请查看问题记录",
            "stopped": "处理已停止",
            "stopping": "正在停止所属处理进程",
        }[workflow.processing_state]
        result["active"] = False
    elif workflow.publication_state == "published":
        result.update(description="正式批次已入库", active=False)
    return result
