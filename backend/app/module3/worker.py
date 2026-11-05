"""Independent single-concurrency ASR worker with fenced checkpoints and heartbeat."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select, text

from app.core.config import BASE_DIR, get_settings
from app.db import models as auth_models  # noqa: F401
from app.db import models_annotations as annotation_models  # noqa: F401
from app.db import models_listening as listening_models  # noqa: F401
from app.db.base import SessionLocal, engine
from app.db.models_processing import ProcessingArtifact
from app.module3 import audio
from app.module3.annotations import SYSTEM_PROMPT, annotation_input, merge_candidate
from app.module3.assembly import assemble
from app.module3.contracts import (
    ProcessingError,
    atomic_json,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.module3.diagnostics import diagnose
from app.module3.llm import request_json
from app.services.processing import tasks
from app.services.processing.persistence import cleanup_failed_files, persist_result


@contextmanager
def renewed_lease(task_id, token, settings):
    stopped = threading.Event()
    lost = threading.Event()

    def renew():
        while not stopped.wait(settings.m3_heartbeat_seconds):
            try:
                with SessionLocal() as db:
                    tasks.heartbeat(db, task_id, token, settings.m3_lease_seconds)
                    db.commit()
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stopped.set()
        thread.join(timeout=6)


def checkpoint(task_id, token, stage, value, settings, **identity):
    with SessionLocal() as db:
        task = tasks.fenced_task(db, task_id, token)
        for material in tasks.task_materials(db, task.id):
            tasks.verify_material(material, settings)
        tasks.save_artifact(db, task_id, token, stage, value, settings, **identity)
        db.commit()


def cached_stage(stage, key, method_hash, settings):
    with SessionLocal() as db:
        rows = db.scalars(
            select(ProcessingArtifact)
            .where(
                ProcessingArtifact.stage == stage,
                ProcessingArtifact.input_hash == key,
                ProcessingArtifact.method_hash == method_hash,
            )
            .order_by(ProcessingArtifact.id.desc())
        ).all()
        for row in rows:
            try:
                path = controlled_path(
                    settings.m3_path("m3_artifacts_dir"), row.storage_key
                )
                if file_hash(path) != row.artifact_hash:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("issues") or not data.get("segments"):
                    continue
                return data, row.id
            except (OSError, ProcessingError, ValueError):
                continue
    return None, None


def run_ocr(task, materials, settings):
    directory = settings.m3_path("m3_artifacts_dir") / str(task.id) / "documents"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "task_id": str(task.id),
        "model_root": str(settings.m3_path("m3_model_root")),
        "files": [
            {
                "material_id": m.id,
                "source_kind": m.source_kind,
                "path": str(tasks.verify_material(m, settings)),
                "sha256": m.sha256,
                "page_numbers": task.request.get("material_pages", {}).get(str(m.id)),
            }
            for m in materials
            if m.source_kind != "audio"
        ],
    }
    atomic_json(directory, "input-manifest.json", manifest)
    child_env = {
        k: v
        for k, v in os.environ.items()
        if not (
            k.upper().startswith(("DEEPSEEK", "PG", "JWT"))
            or k.upper() == "DATABASE_URL"
        )
    }
    child_env.update(
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK="True",
        HF_HUB_OFFLINE="1",
        PYTHONIOENCODING="utf-8",
    )
    command = [
        str(Path(settings.m3_ocr_python).resolve()),
        "-m",
        "app.module3.ocr_worker",
        "--manifest",
        str(directory / "input-manifest.json"),
        "--output",
        str(directory),
    ]
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
    )
    (directory / "ocr-process.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise ProcessingError(
            "OCR_PROCESS_FAILED", "独立文档提取进程失败，详见受控产物日志"
        )
    return json.loads((directory / "extracted.json").read_text(encoding="utf-8"))


def process(task_id, token, settings):
    result = None
    db = None
    try:
        with renewed_lease(task_id, token, settings) as lost:
            report = diagnose("asr", settings)
            if report["status"] != "PASS":
                raise ProcessingError("ENVIRONMENT_BLOCKED", ";".join(report["issues"]))
            checkpoint(task_id, token, "preflight", report, settings)
            with SessionLocal() as db:
                task = tasks.fenced_task(db, task_id, token)
                materials = tasks.task_materials(db, task.id)
                audio_material = next(m for m in materials if m.source_kind == "audio")
                source = tasks.verify_material(audio_material, settings)
                existing = tasks.get_draft(db, task)
                correction = bool(task.request.get("correction"))
                if correction:
                    result = existing.payload
            if not correction:
                extracted = run_ocr(task, materials, settings)
                checkpoint(task_id, token, "extract", extracted, settings)
                normalized = (
                    settings.m3_path("m3_artifacts_dir")
                    / str(task.id)
                    / "normalized.npy"
                )
                meta = audio.decode(source, normalized, settings)
                checkpoint(task_id, token, "normalize", meta, settings)
                transcribe_key = fingerprint(
                    {
                        "original_audio": audio_material.sha256,
                        "normalized": meta["normalized_sha256"],
                        "method": task.method_hash,
                    }
                )
                transcription, source_artifact = cached_stage(
                    "transcribe", transcribe_key, task.method_hash, settings
                )
                if transcription is None:
                    transcription = audio.transcribe(normalized, settings)
                checkpoint(
                    task_id,
                    token,
                    "transcribe",
                    transcription,
                    settings,
                    stage_input_hash=transcribe_key,
                    source_artifact_id=source_artifact,
                )
                align_key = fingerprint(
                    {
                        "transcription": transcription,
                        "method": task.method_hash,
                        "normalized": meta["normalized_sha256"],
                    }
                )
                aligned, source_artifact = cached_stage(
                    "align", align_key, task.method_hash, settings
                )
                if aligned is None:
                    aligned = audio.align(normalized, transcription, settings)
                checkpoint(
                    task_id,
                    token,
                    "align",
                    aligned,
                    settings,
                    stage_input_hash=align_key,
                    source_artifact_id=source_artifact,
                )
                if aligned.get("issues"):
                    raise ProcessingError(
                        "ALIGNMENT_UNVERIFIED",
                        "对齐存在缺句或未决边界，保留检查点待校正",
                    )
                if lost.is_set():
                    raise ProcessingError("STALE_LEASE", "处理进程失去租约")
                result = assemble(
                    task,
                    extracted,
                    aligned,
                    {
                        "audio_code": "A_"
                        + fingerprint(
                            {
                                "paper": task.exam_paper_code,
                                "audio": audio_material.sha256,
                            }
                        )[:40],
                        "file_hash": audio_material.sha256,
                        "duration_ms": meta["duration_ms"],
                        "format": source.suffix.lower().lstrip("."),
                        "mime_type": audio_material.media_type,
                        "collector": "module3",
                        "variant_type": "原始",
                    },
                    settings,
                )
                checkpoint(task_id, token, "assemble", result, settings)
                for index, question in enumerate(result["questions"]):
                    raw, call = request_json(
                        task.id,
                        task.input_hash,
                        "sample" if index < 5 else "run",
                        SYSTEM_PROMPT,
                        annotation_input(result, question),
                        settings,
                    )
                    merge_candidate(result, question, raw)
                    checkpoint(
                        task_id,
                        token,
                        "annotate",
                        {
                            "question_src_id": question["_src_id"],
                            "candidate": raw,
                            "call": call,
                        },
                        settings,
                    )
                with SessionLocal() as db:
                    current = tasks.fenced_task(db, task_id, token)
                    tasks.store_draft(db, current, result, view="auto_draft")
                    db.commit()
            with SessionLocal() as db:
                persist_result(db, task_id, token, result, source, settings)
                db.commit()
    except Exception as exc:
        created_files = db.info.pop("m3_created_files", []) if db is not None else []
        if created_files:
            try:
                cleanup_failed_files(created_files)
            except Exception:
                pass  # Preserve uncertain files; never delete without DB confirmation.
        # This transaction is independent from the rolled-back business transaction.
        error = (
            exc
            if isinstance(exc, ProcessingError)
            else ProcessingError(
                "PROCESSING_FAILED",
                f"处理阶段失败（{type(exc).__name__}），保留已有检查点",
                retryable=True,
            )
        )
        with SessionLocal() as db:
            try:
                task = tasks.fenced_task(db, task_id, token)
            except ProcessingError:
                return 2
            if result is not None and tasks.get_draft(db, task, "auto_draft") is None:
                tasks.store_draft(db, task, result, view="auto_draft")
            task.state = (
                "awaiting_confirmation"
                if error.code
                in {
                    "ENVIRONMENT_BLOCKED",
                    "CREDENTIALS_MISSING",
                    "BUDGET_LIMIT",
                    "ASSEMBLY_UNRESOLVED",
                    "ALIGNMENT_UNVERIFIED",
                }
                else "failed"
            )
            task.issues = [*task.issues, error.issue(task.stage)]
            task.lease_token = None
            task.updated_at = tasks.utcnow()
            db.commit()
        return 2
    return 0


def run_once(settings):
    # One inference process across all workers, without an open long transaction.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock:
        if not lock.execute(text("SELECT pg_try_advisory_lock(3913343170)")).scalar():
            return 0
        try:
            with SessionLocal() as db:
                tasks.expire_leases(db)
                task = tasks.claim_task(
                    db,
                    socket.gethostname() + ":" + str(os.getpid()),
                    settings.m3_lease_seconds,
                )
                db.commit()
                if task is None:
                    return 0
                task_id, token = task.id, task.lease_token
            return process(task_id, token, settings)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(3913343170)"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2)
    args = parser.parse_args()
    settings = get_settings()
    if args.once:
        return run_once(settings)
    if args.poll_seconds <= 0:
        parser.error("poll interval must be positive")
    event = threading.Event()
    while True:
        run_once(settings)
        event.wait(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
