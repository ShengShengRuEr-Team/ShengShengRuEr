"""Local UI adapter. Imports the existing app without changing repository files."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent
from console_config import BACKEND

LEGACY = Path(os.getenv("M3_CONSOLE_EXAMPLES_DIR", str(ROOT / "examples"))).resolve()
DATA = Path(os.getenv("M3_CONSOLE_DATA_DIR", str(ROOT / "data"))).resolve()
DBNAME = os.getenv("M3_CONSOLE_DATABASE", "m3_console_local")
PORT = int(os.getenv("M3_CONSOLE_PORT", "8002"))
if not re.fullmatch(r"m3_console_[a-zA-Z0-9_]+", DBNAME):
    raise RuntimeError("Console database name must use the m3_console_ prefix")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from dotenv import dotenv_values
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

cfg = dotenv_values(BACKEND / ".env")
base = make_url(os.getenv("DATABASE_URL") or cfg["DATABASE_URL"])
for name in ("materials", "artifacts", "audio", "workflows", "logs"):
    (DATA / name).mkdir(parents=True, exist_ok=True)
os.environ.update(
    DATABASE_URL=base.set(database=DBNAME).render_as_string(False),
    M3_MATERIALS_DIR=str(DATA / "materials"),
    M3_ARTIFACTS_DIR=str(DATA / "artifacts"),
    AUDIO_STORAGE_DIR=str(DATA / "audio"),
    PYTHONIOENCODING="utf-8",
)

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from alignment_revision import copy_retry_record, create_revision, revision_record
from app.api.deps import CurrentUser, require_admin
from app.core.audio_response import ranged_file_response
from app.core.config import get_settings
from app.core.errors import AppError, ok
from app.db import models_processing as m
from app.db.base import SessionLocal
from app.db.models_listening import ImportBatch, PaperVisibility
from app.main import app
from app.module3.contracts import controlled_path, file_hash, result_hash
from app.schemas_processing import (
    ActivationRequest,
    CorrectionRequest,
    MaterialRequest,
    RetryRequest,
    ReviewRequest,
    TaskRequest,
)
from app.services import visibility
from app.services.processing import tasks
from console_runtime import AdoptedWorker, kill_worker_tree, progress
from draft_generation import pending_question, pending_report, stamp_task

settings = get_settings()
LOCK = threading.RLock()
UPLOADING = set()
worker = None
stop_monitor = threading.Event()
worker_log = None
schema = json.loads(
    (BACKEND / "config/module3/dictionary-schema.json").read_text(encoding="utf-8")
)
skill_dict = {
    r["skill_code"]: r
    for t in schema["tables"]
    if t["name"] == "skill"
    for r in t["rows"]
}
error_dict = {
    r["error_cause_code"]: r
    for t in schema["tables"]
    if t["name"] == "error_cause"
    for r in t["rows"]
}


def now():
    return datetime.now(UTC).isoformat()


def workflow_path(wid):
    try:
        return DATA / "workflows" / (str(UUID(str(wid))) + ".json")
    except ValueError:
        raise AppError(422, "任务编号无效") from None


def load_job(wid):
    path = workflow_path(wid)
    if not path.is_file():
        raise AppError(404, "处理任务不存在")
    return json.loads(path.read_text(encoding="utf-8"))


def save_job(job):
    job["updated_at"] = now()
    path = workflow_path(job["id"])
    temporary = path.with_suffix("." + uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(job, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def task_for(db, job):
    return tasks.get_task(db, job["task_id"])


def queue(db, job, phase, user_id, **extra):
    ensure_active(job)
    request = {
        **job["base_request"],
        "stop_after": "completed" if phase == "persist" else phase,
        **extra,
    }
    for key in (
        "reuse_alignment_task_id",
        "reuse_assembly_task_id",
        "reuse_annotation_task_id",
        "reuse_full_annotation_task_id",
        "sample_review",
        "annotation_review",
    ):
        if key in job.get("bindings", {}):
            request[key] = job["bindings"][key]
    task = tasks.create_task(db, TaskRequest.model_validate(request), user_id, settings)
    if phase in {"assemble", "annotate_sample", "annotate"}:
        stamp_task(task, db)
    db.commit()
    job.update(phase=phase, task_id=str(task.id), error=None, finalized=False)
    job.setdefault("history", []).append(
        {"phase": phase, "task_id": str(task.id), "at": now()}
    )
    save_job(job)
    return task


def artifact(db, task_id, stage):
    row = db.scalar(
        select(m.ProcessingArtifact)
        .where(
            m.ProcessingArtifact.task_id == task_id, m.ProcessingArtifact.stage == stage
        )
        .order_by(m.ProcessingArtifact.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    path = controlled_path(DATA / "artifacts", row.storage_key)
    if file_hash(path) != row.artifact_hash:
        raise AppError(409, "阶段文件发生变化，请停止并核查")
    return {
        "artifact_hash": row.artifact_hash,
        "result": json.loads(path.read_text(encoding="utf-8")),
    }


def clean_task(task):
    return {
        key: getattr(task, key)
        for key in (
            "id",
            "state",
            "stage",
            "issues",
            "result_hash",
            "exam_paper_id",
            "batch_id",
            "created_at",
            "updated_at",
        )
    }


def status_job(job, db):
    value = copy.deepcopy(job)
    value.pop("base_request", None)
    value.pop("bindings", None)
    value.pop("full_review", None)
    if job.get("task_id"):
        task = task_for(db, job)
        value["task"] = clean_task(task)
        if task.batch_id:
            current = db.scalar(
                select(ImportBatch).where(
                    ImportBatch.exam_paper_id == task.exam_paper_id,
                    ImportBatch.is_current.is_(True),
                )
            )
            pv = db.scalar(
                select(PaperVisibility)
                .where(PaperVisibility.batch_id == task.batch_id)
                .order_by(PaperVisibility.id.desc())
            )
            value["is_current"] = bool(current and current.id == task.batch_id)
            value["is_visible"] = bool(pv and pv.is_visible)
    value["progress"] = progress(job, db, m, DATA)
    return value


def ensure_active(job):
    if job.get("stopped"):
        raise AppError(409, "本次处理已停止；如需继续，请填写原因后重新处理当前阶段")


def ready_task(db, job):
    ensure_active(job)
    task = task_for(db, job)
    if task.state not in {"awaiting_confirmation", "completed"} or any(
        i.get("severity") == "error" for i in task.issues
    ):
        raise AppError(409, "处理尚未完成或存在阻断，请查看任务问题")
    return task


def semantic_review(data, payload, count, digest, user):
    expected = {
        q["_src_id"]
        for q in payload["questions"][:count]
        if not (
            payload.get("assembly_audit", {}).get("draft_first")
            and pending_question(q, payload, "annotate")
        )
    }
    items = data.get("items", [])
    if (
        len(items) != len(expected)
        or {i.get("question_src_id") for i in items} != expected
    ):
        raise AppError(422, "请完成本阶段每一道题的复核")
    for item in items:
        if (
            not str(item.get("support_reason", "")).strip()
            or not str(item.get("skill_reason", "")).strip()
        ):
            raise AppError(422, "每题都需要填写答案支持依据和技能适用依据")
        if item.get("decision") not in {"approved", "changes_required"}:
            raise AppError(422, "请明确每题的复核结论")
        if (
            item["decision"] == "changes_required"
            and not str(item.get("repair_feedback", "")).strip()
        ):
            raise AppError(422, "需修复题目必须填写具体修复意见")
    return {
        "result_hash": digest,
        "decision": (
            "deferred"
            if not expected and payload.get("assembly_audit", {}).get("draft_first")
            else "approved"
            if all(i["decision"] == "approved" for i in items)
            else "changes_required"
        ),
        "reviewer": user.username,
        "reviewed_at": now(),
        "items": items,
        "scope": "available_questions_only"
        if payload.get("assembly_audit", {}).get("draft_first")
        else "all_questions",
    }


def finalize(db, job):
    ensure_active(job)
    task = task_for(db, job)
    if not task.batch_id or task.state in {"pending", "running", "failed"}:
        return
    draft = tasks.get_draft(db, task)
    payload = draft.payload
    if draft.result_hash != job["full_review"]["result_hash"]:
        raise AppError(409, "入库结果已变化，请重新复核")
    check = tasks.check_result(db, task.id, draft.result_hash, settings)
    db.commit()
    if not check.is_passed:
        raise AppError(409, "入库检查未通过，请查看检查问题")
    # Service functions only read these two fields of the authenticated actor.
    from types import SimpleNamespace

    actor = SimpleNamespace(id=job["user_id"], username=job["reviewer"])
    approved = {i["question_src_id"]: i for i in job["full_review"]["items"]}
    scopes = {
        "content": [
            {
                "entity_type": "questions",
                "src_id": q["_src_id"],
                "verdict": "PASS",
                "reference": approved[q["_src_id"]]["support_reason"]
                + "; "
                + job["content_note"],
            }
            for q in payload["questions"]
        ],
        "annotations": [
            {
                "entity_type": section,
                "src_id": r["_src_id"],
                "verdict": "PASS",
                "reference": "逐题复核记录 "
                + job["id"]
                + "; "
                + job["full_review"]["reviewed_at"],
            }
            for section in (
                "skill_question_relations",
                "error_question_relations",
                "other_relations",
            )
            for r in payload.get(section, [])
        ],
        "audio": [
            {
                "entity_type": "audio",
                "src_id": "original",
                "verdict": "PASS",
                "file_hash": payload["audio"]["file_hash"],
                "reference": job["audio_approval"]["note"],
            }
        ],
    }
    if payload["audio"]["file_hash"] != job["uploads"]["audio"]["sha256"]:
        raise AppError(409, "音频与核听确认不一致")
    for scope, items in scopes.items():
        values = dict(
            result_hash=draft.result_hash,
            scope=scope,
            decision="approved",
            items=items,
            evidence_refs=[
                "console:" + job["id"] + ":" + job["full_review"]["reviewed_at"]
            ],
            note="管理员在本地工作台逐项确认；" + job["content_note"],
        )
        if scope == "audio":
            values.update(
                review_basis="user_confirmation",
                approval_reference="console:"
                + job["id"]
                + ":"
                + job["audio_approval"]["at"],
            )
        tasks.record_review(db, task.id, ReviewRequest.model_validate(values), actor)
    db.commit()
    job.update(finalized=True, check_id=check.id, phase="completed", error=None)
    save_job(job)


router = APIRouter(prefix="/console-api", dependencies=[Depends(require_admin)])


@router.get("/config")
def configuration():
    return ok(
        {
            "database": DBNAME,
            "worker_running": bool(worker and worker.poll() is None),
            "deepseek_configured": bool(settings.deepseek_api_key),
            "skills": skill_dict,
            "error_causes": error_dict,
            "examples": [
                r
                for r, f in (("text", "text-recheck"), ("scan", "r15-full-pipeline"))
                if (LEGACY / f / "latest.json").is_file()
            ],
            "max_file_bytes": 512 * 1024 * 1024,
        }
    )


@router.get("/workflows")
def list_jobs():
    with LOCK, SessionLocal() as db:
        jobs = [
            status_job(json.loads(p.read_text(encoding="utf-8")), db)
            for p in (DATA / "workflows").glob("*.json")
        ]
    return ok(sorted(jobs, key=lambda j: j["created_at"], reverse=True))


@router.post("/workflows", status_code=201)
async def new_job(request: Request, user: CurrentUser = Depends(require_admin)):
    data = await request.json()
    paper = data.get("exam_paper", {})
    code = paper.get("exam_paper_code", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code):
        raise AppError(422, "试卷编码仅允许字母、数字、下划线和短横线")
    wid = str(uuid4())
    base_request = {
        "exam_paper": paper,
        "material_ids": [1],
        "document_mode": data.get("document_mode", "text"),
        "text_source": "reference",
        "reference_preparation": "auto",
        "dictionary_snapshot_sha256": file_hash(
            BACKEND / "config/module3/dictionary-schema.json"
        ),
        "profile_version": "M3-WIN64-1.1.0",
        "stop_after": "align",
    }
    TaskRequest.model_validate(base_request)
    pages = data.get("answer_pages", [])
    if (
        not isinstance(pages, list)
        or len(pages) > 500
        or any(type(p) is not int or p <= 0 for p in pages)
        or len(pages) != len(set(pages))
    ):
        raise AppError(422, "答案页码应为不重复的正整数")
    job = {
        "id": wid,
        "title": data.get("title", code),
        "created_at": now(),
        "updated_at": now(),
        "user_id": user.id,
        "reviewer": user.username,
        "phase": "upload",
        "uploads": {},
        "bindings": {},
        "base_request": base_request,
        "answer_pages": pages,
        "history": [],
    }
    with LOCK:
        save_job(job)
    return ok(job)


@router.put("/workflows/{wid}/files/{kind}")
async def upload(wid: str, kind: str, request: Request, name: str):
    if kind not in {"paper", "answer", "audio"}:
        raise AppError(422, "材料类别无效")
    filename = Path(name.replace("\\", "/")).name
    if (
        filename != name
        or any(c in filename for c in '<>:"|?*')
        or any(ord(c) < 32 for c in filename)
        or len(filename) > 180
    ):
        raise AppError(422, "文件名无效，请使用简单文件名")
    suffix = Path(filename).suffix.lower()
    if (kind in {"paper", "answer"} and suffix != ".pdf") or (
        kind == "audio" and suffix not in {".m4a", ".mp3", ".wav", ".flac", ".ogg"}
    ):
        raise AppError(422, "试卷与解析请选择PDF，音频请选择M4A/MP3/WAV/FLAC/OGG")
    key = (wid, kind)
    with LOCK:
        job = load_job(wid)
        ensure_active(job)
        if job["phase"] != "upload" or key in UPLOADING:
            raise AppError(409, "任务已开始或该文件正在上传")
        UPLOADING.add(key)
    directory = DATA / "materials" / wid / kind
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / (uuid4().hex + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with temp.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise AppError(413, "单文件上限512MB")
                digest.update(chunk)
                output.write(chunk)
        if not size:
            raise AppError(422, "文件为空")
        dest = directory / filename
        item = {
            "name": filename,
            "storage_key": dest.relative_to(DATA / "materials").as_posix(),
            "sha256": digest.hexdigest(),
            "size": size,
        }
        with LOCK:
            job = load_job(wid)
            ensure_active(job)
            if job["phase"] != "upload":
                raise AppError(409, "任务已开始，不能继续覆盖材料")
            os.replace(temp, dest)
            job["uploads"][kind] = item
            save_job(job)
        return ok(item)
    finally:
        temp.unlink(missing_ok=True)
        with LOCK:
            UPLOADING.discard(key)


@router.post("/workflows/{wid}/start")
def start(wid: str, user: CurrentUser = Depends(require_admin)):
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        ensure_active(job)
        if job["phase"] != "upload":
            raise AppError(409, "任务已开始，不能重复启动")
        if set(job["uploads"]) != {"paper", "answer", "audio"}:
            raise AppError(422, "请完整上传三份材料")
        ids = []
        answer_id = None
        for kind in ("paper", "answer", "audio"):
            item = job["uploads"][kind]
            skind = (
                ("paper_" + job["base_request"]["document_mode"])
                if kind == "paper"
                else ("answer_explanation" if kind == "answer" else "audio")
            )
            row = tasks.register_material(
                db,
                MaterialRequest(
                    exam_paper_code=job["base_request"]["exam_paper"][
                        "exam_paper_code"
                    ],
                    source_kind=skind,
                    storage_key=item["storage_key"],
                    expected_sha256=item["sha256"],
                    source_locator="本地工作台上传：" + item["name"],
                ),
                user.id,
                settings,
            )
            ids.append(row.id)
            if kind == "answer":
                answer_id = row.id
        job["base_request"]["material_ids"] = ids
        if job["answer_pages"]:
            job["base_request"]["material_pages"] = {
                str(answer_id): job["answer_pages"]
            }
        queue(db, job, "align", user.id)
        return ok(status_job(job, db))


@router.get("/workflows/{wid}")
def get_job(wid: str):
    with LOCK, SessionLocal() as db:
        return ok(status_job(load_job(wid), db))


@router.get("/workflows/{wid}/result")
def get_result(wid: str):
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        if not job.get("task_id"):
            return ok({"missing": True})
        task = task_for(db, job)
        draft = tasks.get_draft(db, task)
        if draft:
            return ok(
                {
                    "payload": draft.payload,
                    "result_hash": draft.result_hash,
                    "draft_pending": pending_report(draft.payload, job["phase"]),
                    "draft_first": bool(
                        draft.payload.get("assembly_audit", {}).get("draft_first")
                    ),
                }
            )
        align = artifact(db, task.id, "align")
        read_only = False
        if align is None and job.get("alignment_revision"):
            align = artifact(db, job["alignment_revision"]["source_task_id"], "align")
            read_only = True
        row = revision_record(db, task.id)
        revision = (
            {
                "reason": row.reason,
                "change": row.changes[0],
                "parent_task_id": str(row.parent_task_id),
                "created_at": row.created_at,
            }
            if row
            else None
        )
        editable = bool(
            align
            and not read_only
            and job["phase"] == "align"
            and not job.get("stopped")
            and task.stage == "align"
            and task.state in {"awaiting_confirmation", "failed"}
        )
        return ok(
            {
                "alignment": align,
                "missing": align is None,
                "alignment_editor": {
                    "can_edit": editable,
                    "previous_result": read_only,
                },
                "alignment_revision": revision,
            }
        )


@router.post("/workflows/{wid}/alignment-revisions", status_code=202)
async def revise_alignment(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        ensure_active(job)
        if job["phase"] != "align":
            raise AppError(409, "仅可在对齐阶段校正，后续阶段不得静默修改原文")
        parent = tasks.get_task(db, job["task_id"], lock=True)
        if str(parent.id) != data.get("task_id"):
            raise AppError(409, "任务版本已变化，请刷新后校正")
        child = create_revision(db, parent, data, user, settings)
        db.commit()
        job.update(
            task_id=str(child.id),
            error=None,
            finalized=False,
            bindings={},
            alignment_revision={
                "source_task_id": str(parent.id),
                "task_id": str(child.id),
                "at": now(),
            },
        )
        for key in ("audio_approval", "content_note", "full_review", "check_id"):
            job.pop(key, None)
        job["history"].append(
            {
                "phase": "align",
                "kind": "alignment_revision",
                "task_id": str(child.id),
                "source_task_id": str(parent.id),
                "at": now(),
            }
        )
        save_job(job)
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/continue")
async def continue_job(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        task = ready_task(db, job)
        if str(task.id) != data.get("task_id"):
            raise AppError(409, "任务版本已更新，请刷新后操作")
        phase = job["phase"]
        if phase == "align":
            aligned = artifact(db, task.id, "align")
            if not aligned or aligned["artifact_hash"] != data.get("artifact_hash"):
                raise AppError(409, "对齐结果已更新")
            if (
                data.get("audio_confirmed") is not True
                or not str(data.get("note", "")).strip()
            ):
                raise AppError(422, "请核听并填写本套音频确认说明")
            job["audio_approval"] = {
                "at": now(),
                "note": data["note"],
                "reviewer": user.username,
                "artifact_hash": aligned["artifact_hash"],
            }
            job["bindings"]["reuse_alignment_task_id"] = str(task.id)
            queue(db, job, "assemble", user.id)
        elif phase == "assemble":
            draft = tasks.get_draft(db, task)
            if not draft or draft.result_hash != data.get("result_hash"):
                raise AppError(409, "题目草稿已更新")
            draft_first = draft.payload.get("assembly_audit", {}).get("draft_first")
            if data.get("paid_call_confirmed") is not True or (
                not draft_first
                and (
                    data.get("content_confirmed") is not True
                    or not str(data.get("note", "")).strip()
                )
            ):
                raise AppError(422, "请确认开始付费标注草稿")
            job["content_note"] = (
                data.get("note") or "管理员选择先生成草稿，来源字段及标注仍待最终复核"
            )
            job["bindings"]["reuse_assembly_task_id"] = str(task.id)
            queue(db, job, "annotate_sample", user.id)
        elif phase in {"annotate_sample", "annotate"}:
            draft = tasks.get_draft(db, task)
            if not draft or draft.result_hash != data.get("result_hash"):
                raise AppError(409, "标注草稿已更新")
            review = semantic_review(
                data,
                draft.payload,
                5 if phase == "annotate_sample" else len(draft.payload["questions"]),
                draft.result_hash,
                user,
            )
            if phase == "annotate_sample":
                if review["decision"] not in {"approved", "deferred"}:
                    raise AppError(422, "小样有待修复项，请修改来源或重新生成小样")
                job["bindings"].update(
                    reuse_annotation_task_id=str(task.id), sample_review=review
                )
                queue(db, job, "annotate", user.id)
            else:
                job["bindings"].update(
                    reuse_full_annotation_task_id=str(task.id), annotation_review=review
                )
                if review["decision"] == "approved":
                    if draft.payload.get("assembly_audit", {}).get(
                        "draft_first"
                    ) and pending_report(draft.payload, "annotate"):
                        raise AppError(
                            409,
                            "草稿仍有待补或未完成标注的题目；可先查看结果，补全后再正式入库",
                        )
                    if data.get("content_confirmed") is not True:
                        raise AppError(
                            422, "请确认已核对本套全部题干、选项、答案与解析"
                        )
                    job.update(user_id=user.id, reviewer=user.username)
                    job["full_review"] = review
                    queue(db, job, "persist", user.id)
                else:
                    queue(db, job, "annotate", user.id)
        else:
            raise AppError(409, "该阶段不接受继续操作")
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/corrections")
async def corrections(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        if job["phase"] != "assemble":
            raise AppError(409, "请在组装阶段校正来源字段；标注后不得静默改写")
        parent = ready_task(db, job)
        child = tasks.correct_task(
            db, parent.id, CorrectionRequest.model_validate(data), user.id
        )
        db.commit()
        job["task_id"] = str(child.id)
        job["history"].append(
            {"phase": "correction", "task_id": str(child.id), "at": now()}
        )
        save_job(job)
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/retry")
async def retry(wid: str, request: Request, user: CurrentUser = Depends(require_admin)):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        task = task_for(db, job)
        if task.state in {"running", "pending"}:
            raise AppError(409, "处理仍在执行")
        if not str(data.get("reason", "")).strip():
            raise AppError(422, "请填写重试原因")
        if job["phase"] == "persist" and task.batch_id:
            job["error"] = None
            save_job(job)
            finalize(db, job)
            return ok(status_job(job, db))
        child = tasks.retry_task(
            db,
            task.id,
            RetryRequest(expected_input_hash=task.input_hash, reason=data["reason"]),
            user.id,
            settings,
        )
        copy_retry_record(db, task, child, user.id)
        if job["phase"] == "assemble":
            if artifact(db, task.id, "assembly_extract"):
                child.request = {
                    **child.request,
                    "reuse_assembly_scan_task_id": str(task.id),
                }
            stamp_task(child, db)
        elif task.method.get("console_partial_draft"):
            stamp_task(child, db)
        db.commit()
        job.update(task_id=str(child.id), error=None, stopped=False)
        job.pop("stopped_at", None)
        job.pop("stopped_by", None)
        job["history"].append(
            {
                "phase": job["phase"],
                "kind": "retry",
                "task_id": str(child.id),
                "at": now(),
            }
        )
        save_job(job)
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/return-to-assembly")
async def return_to_assembly(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        parent = ready_task(db, job)
        if job["phase"] not in {"annotate_sample", "annotate"} or str(
            parent.id
        ) != data.get("task_id"):
            raise AppError(409, "仅可从当前已完成的标注草稿返回补全")
        draft = tasks.get_draft(db, parent)
        if not draft or draft.result_hash != data.get("result_hash"):
            raise AppError(409, "草稿版本已变化")
        payload = copy.deepcopy(draft.payload)
        for name in (
            "evidences",
            "skill_question_relations",
            "error_question_relations",
            "other_relations",
        ):
            payload[name] = []
        payload.setdefault("assembly_audit", {}).pop("annotation_skipped", None)
        child = tasks.child_task(db, parent, user.id, state="awaiting_confirmation")
        child.request = {
            **job["base_request"],
            "stop_after": "assemble",
            "reuse_alignment_task_id": job["bindings"]["reuse_alignment_task_id"],
        }
        stamp_task(child, db)
        tasks.store_draft(db, child, payload, view="auto_draft")
        tasks.store_draft(db, child, payload, view="final")
        # Preserve an immutable assembly checkpoint for reuse.
        from app.module3.contracts import atomic_json, fingerprint

        digest, size = atomic_json(
            DATA / "artifacts",
            f"{child.id}/assemble/{fingerprint(payload)}.json",
            payload,
        )
        db.add(
            m.ProcessingArtifact(
                task_id=child.id,
                stage="assemble",
                input_hash=child.input_hash,
                method_hash=child.method_hash,
                storage_key=f"{child.id}/assemble/{digest}.json",
                artifact_hash=digest,
                size_bytes=size,
            )
        )
        child.stage = "assemble"
        child.issues = []
        db.commit()
        job.update(task_id=str(child.id), phase="assemble", error=None, finalized=False)
        job["bindings"] = {
            "reuse_alignment_task_id": job["bindings"]["reuse_alignment_task_id"]
        }
        job["history"].append(
            {
                "phase": "assemble",
                "kind": "return_to_assembly",
                "task_id": str(child.id),
                "at": now(),
            }
        )
        save_job(job)
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/stop")
async def stop_job(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        if job.get("stopped"):
            return ok(status_job(job, db))
        if job["phase"] == "completed":
            raise AppError(409, "本套已入库；可见性请使用单独的撤销操作")
        if data.get("task_id") != job.get("task_id"):
            raise AppError(409, "任务版本已变化，请刷新后停止")
        was_running = False
        if job.get("task_id"):
            task = tasks.get_task(db, job["task_id"], lock=True)
            if task.state == "running":
                # Lock first to fence later checkpoints from the old lease.
                try:
                    kill_worker_tree(worker, task.worker_id)
                except RuntimeError as exc:
                    raise AppError(409, str(exc)) from None
                was_running = True
            if task.state in {"pending", "running"}:
                task.state = "failed"
                task.lease_token = None
                task.expires_at = None
                task.updated_at = tasks.utcnow()
                task.issues = [
                    *task.issues,
                    {
                        "issue_code": "USER_STOPPED",
                        "message": "管理员主动停止本次处理；已有材料和结果保留",
                        "severity": "error",
                        "stage": task.stage,
                        "retryable": True,
                    },
                ]
            db.commit()
        job.update(stopped=True, stopped_at=now(), stopped_by=user.username, error=None)
        job.setdefault("history", []).append(
            {
                "phase": "stop",
                "task_id": job.get("task_id"),
                "at": now(),
                "operator": user.username,
            }
        )
        save_job(job)
        if was_running:
            try:
                launch_worker()
            except Exception:
                job["error"] = (
                    "本次已停止，但处理进程重启失败；请重启工作台后处理其他任务"
                )
                save_job(job)
        return ok(status_job(job, db))


@router.post("/workflows/{wid}/activate")
def activate(wid: str, user: CurrentUser = Depends(require_admin)):
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        task = task_for(db, job)
        if not job.get("finalized"):
            raise AppError(409, "请先完成整套复核和入库检查")
        current = db.scalar(
            select(ImportBatch).where(
                ImportBatch.exam_paper_id == task.exam_paper_id,
                ImportBatch.is_current.is_(True),
            )
        )
        out = tasks.activate(
            db,
            task.exam_paper_id,
            ActivationRequest(
                task_id=task.id,
                batch_id=task.batch_id,
                check_id=job["check_id"],
                result_hash=task.result_hash,
                expected_current_batch_id=current.id if current else None,
            ),
            user.id,
        )
        db.commit()
        return ok(out)


@router.post("/workflows/{wid}/visibility")
async def set_visibility(
    wid: str, request: Request, user: CurrentUser = Depends(require_admin)
):
    data = await request.json()
    with LOCK, SessionLocal() as db:
        job = load_job(wid)
        task = task_for(db, job)
        from app.db.models_listening import ExamPaper

        paper = db.get(ExamPaper, task.exam_paper_id)
        batch = db.get(ImportBatch, task.batch_id)
        if not batch or not batch.is_current:
            raise AppError(409, "请先明确设为当前批次")
        if data.get("action") == "confirm":
            visibility.confirm_visible(
                db,
                paper,
                batch,
                user.id,
                "管理员在本地工作台明确确认学生可见",
                settings.audio_storage_path,
            )
        elif data.get("action") == "cancel":
            visibility.cancel_visible(
                db, paper, batch, user.id, "管理员在本地工作台撤销学生可见"
            )
        else:
            raise AppError(422, "可见性动作无效")
        db.commit()
        return ok(status_job(job, db))


@router.get("/workflows/{wid}/files/{kind}")
def get_source(wid: str, kind: str, request: Request):
    job = load_job(wid)
    item = job["uploads"].get(kind)
    if not item:
        raise AppError(404, "源文件不存在")
    path = controlled_path(DATA / "materials", item["storage_key"])
    if file_hash(path) != item["sha256"]:
        raise AppError(409, "源文件哈希已变化")
    if kind == "audio":
        return ranged_file_response(
            request,
            path,
            {
                ".m4a": "audio/mp4",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".flac": "audio/flac",
                ".ogg": "audio/ogg",
            }[path.suffix.lower()],
        )
    return FileResponse(path, media_type="application/pdf", filename=item["name"])


@router.get("/examples/{route}")
def example(route: str):
    if route not in {"text", "scan"}:
        raise AppError(404, "示例不存在")
    folder = "text-recheck" if route == "text" else "r15-full-pipeline"
    if not (LEGACY / folder / "latest.json").is_file():
        raise AppError(404, "本环境未配置历史示例，请上传自己的材料")
    latest = json.loads((LEGACY / folder / "latest.json").read_text(encoding="utf-8"))
    payload = json.loads(
        (Path(latest["directory"]) / "draft.json").read_text(encoding="utf-8")
    )
    if result_hash(payload) != latest["result_hash"]:
        raise AppError(409, "示例结果哈希不符")
    return ok(
        {
            "payload": payload,
            "result_hash": latest["result_hash"],
            "archived": True,
            "route": route,
            "title": "2025年6月四级第1套 · " + ("文本" if route == "text" else "扫描"),
        }
    )


@router.get("/examples/{route}/audio")
def example_audio(route: str, request: Request):
    if route not in {"text", "scan"}:
        raise AppError(404, "示例不存在")
    path = next((LEGACY / "materials").glob("*.m4a"), None)
    if path is None:
        raise AppError(404, "本环境未配置示例音频")
    return ranged_file_response(request, path, "audio/mp4")


def monitor():
    while not stop_monitor.wait(2):
        with LOCK:
            for path in (DATA / "workflows").glob("*.json"):
                job = json.loads(path.read_text(encoding="utf-8"))
                if (
                    job.get("phase") != "persist"
                    or job.get("error")
                    or job.get("stopped")
                ):
                    continue
                try:
                    with SessionLocal() as db:
                        finalize(db, job)
                except Exception as exc:
                    job["error"] = getattr(
                        exc, "msg", "入库后检查暂未完成，请查看任务日志并重试"
                    )
                    save_job(job)


def launch_worker():
    global worker, worker_log
    if worker and worker.poll() is None:
        return
    if os.getenv("M3_CONSOLE_WORKER", "1") != "1":
        return
    if worker_log is None:
        worker_log = (DATA / "logs/worker.log").open("a", encoding="utf-8")
    worker = subprocess.Popen(
        [
            settings.m3_asr_python,
            str(ROOT / "console_worker.py"),
            "--poll-seconds",
            "2",
        ],
        cwd=BACKEND,
        env=dict(os.environ),
        stdout=worker_log,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    (DATA / "logs/worker.pid").write_text(str(worker.pid), encoding="utf-8")


@asynccontextmanager
async def lifespan(_app):
    global worker
    (DATA / "logs/server.pid").write_text(str(os.getpid()), encoding="utf-8")
    thread = None
    if os.getenv("M3_CONSOLE_MONITOR", "1") == "1":
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
    if os.getenv("M3_CONSOLE_ADOPT_WORKER_PID"):
        worker = AdoptedWorker(int(os.environ["M3_CONSOLE_ADOPT_WORKER_PID"]))
    launch_worker()
    try:
        yield
    finally:
        stop_monitor.set()
        if thread:
            thread.join(timeout=5)
        if worker and worker.poll() is None:
            kill_worker_tree(worker)
        if worker_log:
            worker_log.close()


app.include_router(router)
from fastapi.responses import JSONResponse
from pydantic import ValidationError


@app.exception_handler(ValidationError)
async def invalid_console_input(_request, _error):
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "msg": "参数不符合现有接口要求，请检查试卷信息或复核内容",
            "data": None,
        },
    )


app.router.lifespan_context = lifespan
app.title = "声声入耳 · 本地处理工作台"
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="console")


def initialize_database():
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            if not c.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": DBNAME}
            ):
                c.execute(text(f'CREATE DATABASE "{DBNAME}"'))
    finally:
        admin.dispose()
    from alembic import command
    from alembic.config import Config

    ac = Config(str(BACKEND / "alembic.ini"))
    ac.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(ac, "head")
    from app.seed import seed

    seed()


if __name__ == "__main__":
    initialize_database()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT)
