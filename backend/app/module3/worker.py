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
from app.module3 import audio, auto_reference, reference, reuse
from app.module3.assembly import assemble
from app.module3.contracts import (
    ProcessingError,
    atomic_json,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.module3.diagnostics import diagnose
from app.module3.source_assembly import assemble as assemble_sources
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


def run_ocr(task, materials, settings, *, assembly_pages=None):
    directory = (
        settings.m3_path("m3_artifacts_dir")
        / str(task.id)
        / ("assembly-documents" if assembly_pages is not None else "documents")
    )
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "task_id": str(task.id),
        "model_root": str(settings.m3_path("m3_model_root")),
        "nltk_data": str(settings.nltk_data),
        "prepare_reference": (
            task.request.get("text_source", "reference") == "reference"
            and task.request.get("reference_preparation", "provided") == "auto"
            and not task.request.get("reference_segments")
        ),
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
    manifest["reference_only"] = (
        manifest["prepare_reference"]
        and task.request.get("stop_after", "align") == "align"
    )
    if assembly_pages is not None:
        manifest["assembly_only"] = True
        manifest["files"] = [
            {**item, "page_numbers": assembly_pages}
            for item in manifest["files"]
            if item["source_kind"] == "answer_explanation"
        ]
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
        OMP_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
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


def stop_draft(task_id, token, stage, result, settings):
    """Stop with task artifacts/drafts before any business check or write."""
    with SessionLocal() as db:
        task = tasks.fenced_task(db, task_id, token)
        if tasks.get_draft(db, task, "auto_draft") is None:
            tasks.store_draft(db, task, result, view="auto_draft")
        tasks.store_draft(db, task, result, view="final")
        task.state, task.stage = "awaiting_confirmation", stage
        task.issues = [
            {
                "issue_code": "DOWNSTREAM_SCOPE_STOP",
                "severity": "info",
                "stage": stage,
                "message": "授权范围内草稿已保存；第9步未开始",
                "retryable": False,
            }
        ]
        task.lease_token, task.expires_at = None, None
        task.updated_at = tasks.utcnow()
        db.commit()
    return 0


def process(task_id, token, settings):
    result = None
    db = None
    try:
        with renewed_lease(task_id, token, settings) as lost:
            with SessionLocal() as db:
                task = tasks.fenced_task(db, task_id, token)
                if task.method_hash != fingerprint(task.method):
                    raise ProcessingError(
                        "METHOD_CHANGED",
                        "已登记的方法快照发生变化",
                    )
                for key, expected in task.method.get(
                    "implementation_sha256", {}
                ).items():
                    if file_hash(controlled_path(BASE_DIR, key)) != expected:
                        raise ProcessingError(
                            "METHOD_CHANGED",
                            "实现已变更，请以新方法快照建立任务",
                        )
            report = diagnose(
                "align"
                if task.request.get("text_source", "reference") == "reference"
                else "asr",
                settings,
            )
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
                    if task.request.get("stop_after", "align") == "align":
                        raise ProcessingError(
                            "ALIGNMENT_REVIEW_REQUIRED",
                            "当前仅授权对齐阶段，请先复核对齐产物",
                        )
            if correction and task.request.get("stop_after") in {
                "assemble",
                "annotate_sample",
                "annotate",
            }:
                stage = (
                    "assemble"
                    if task.request["stop_after"] == "assemble"
                    else "annotate"
                )
                checkpoint(task_id, token, stage, result, settings)
                return stop_draft(task_id, token, stage, result, settings)
            if not correction:
                reused = None
                if task.request.get("reuse_alignment_task_id"):
                    with SessionLocal() as reuse_db:
                        reused, provenance = reuse.load(reuse_db, task, settings)
                    for stage in ("extract", "normalize", "reference", "align"):
                        source_row = next(
                            r for r in provenance["artifacts"] if r["stage"] == stage
                        )
                        checkpoint(
                            task_id,
                            token,
                            stage,
                            reused[stage],
                            settings,
                            source_artifact_id=source_row["artifact_id"],
                        )
                    checkpoint(task_id, token, "reuse", provenance, settings)
                    extracted, meta = reused["extract"], reused["normalize"]
                    transcription, aligned = reused["reference"], reused["align"]
                else:
                    extracted = run_ocr(task, materials, settings)
                    checkpoint(task_id, token, "extract", extracted, settings)
                    normalized = (
                        settings.m3_path("m3_artifacts_dir")
                        / str(task.id)
                        / "normalized.npy"
                    )
                    meta = audio.decode(source, normalized, settings)
                    checkpoint(task_id, token, "normalize", meta, settings)
                    use_reference = (
                        task.request.get("text_source", "reference") == "reference"
                    )
                    if use_reference:
                        transcription = {
                            "segments": task.request.get("reference_segments", [])
                        }
                        if (
                            not transcription["segments"]
                            and task.request.get("reference_preparation") == "auto"
                        ):
                            prepared = auto_reference.prepare(
                                extracted,
                                [
                                    {
                                        "material_id": m.id,
                                        "source_kind": m.source_kind,
                                        "storage_key": m.storage_key,
                                        "sha256": m.sha256,
                                    }
                                    for m in materials
                                ],
                                normalized,
                                settings,
                                normalized.parent,
                            )
                            discovered = prepared["trusted_question_structure"]
                            expected = task.request.get("expected_question_count")
                            if expected and discovered["question_count"] != expected:
                                raise ProcessingError(
                                    "REFERENCE_QUESTION_COUNT_CONFLICT",
                                    "原卷自动题量与请求的可信题量不一致",
                                )
                            ranges = task.request.get("expected_question_ranges")
                            actual_ranges = [
                                {k: group[k] for k in ("section", "start", "end")}
                                for group in discovered.get("groups", [])
                            ]
                            if ranges and actual_ranges != ranges:
                                raise ProcessingError(
                                    "REFERENCE_QUESTION_RANGES_CONFLICT",
                                    "原卷自动题组范围与请求的可信范围不一致",
                                )
                            transcription = prepared
                        if not transcription["segments"]:
                            raise ProcessingError(
                                "REFERENCE_TEXT_REQUIRED", "缺少答案逐句原文，不运行ASR"
                            )
                        checkpoint(task_id, token, "reference", transcription, settings)
                    else:
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
                        aligned = (
                            reference.align(
                                normalized, transcription["segments"], settings
                            )
                            if use_reference
                            else audio.align(normalized, transcription, settings)
                        )
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
                if task.request.get("stop_after", "align") == "align":
                    with SessionLocal() as db:
                        current = tasks.fenced_task(db, task_id, token)
                        current.state, current.stage = "awaiting_confirmation", "align"
                        current.issues = [
                            {
                                "issue_code": "ALIGNMENT_REVIEW_REQUIRED",
                                "severity": "info",
                                "stage": "align",
                                "message": "对齐产物已保存，等待用户确认后继续",
                                "retryable": False,
                            }
                        ]
                        current.lease_token, current.expires_at = None, None
                        current.updated_at = tasks.utcnow()
                        db.commit()
                    return 0
                if task.request.get("reuse_assembly_task_id"):
                    with SessionLocal() as reuse_db:
                        result, assembly_source = reuse.assembly(
                            reuse_db, task, settings
                        )
                    checkpoint(
                        task_id,
                        token,
                        "assemble",
                        result,
                        settings,
                        source_artifact_id=assembly_source,
                    )
                else:
                    source_mode = (
                        task.request.get("text_source", "reference") == "reference"
                    )
                    assembly_kwargs = {}
                    if source_mode:
                        pages = sorted(
                            {
                                p
                                for r in transcription["segments"]
                                for p in r["source_pages"]
                            }
                        )
                        scan_source = None
                        if task.request.get("reuse_assembly_scan_task_id"):
                            with SessionLocal() as reuse_db:
                                answer_extracted, scan_source = reuse.assembly_scan(
                                    reuse_db, task, settings
                                )
                            if (
                                sorted(p["page"] for p in answer_extracted["pages"])
                                != pages
                            ):
                                raise ProcessingError(
                                    "REUSE_PAGES_CHANGED", "解析OCR页覆盖不一致"
                                )
                        else:
                            answer_extracted = run_ocr(
                                task, materials, settings, assembly_pages=pages
                            )
                        checkpoint(
                            task_id,
                            token,
                            "assembly_extract",
                            answer_extracted,
                            settings,
                            source_artifact_id=scan_source,
                        )
                        extracted = {
                            **extracted,
                            "material_sha256": {str(m.id): m.sha256 for m in materials},
                        }
                        assembly_kwargs = {
                            "reference_data": transcription,
                            "answer_extracted": answer_extracted,
                        }
                    result = (assemble_sources if source_mode else assemble)(
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
                        **assembly_kwargs,
                    )
                    checkpoint(task_id, token, "assemble", result, settings)
                stop_after = task.request.get("stop_after", "align")
                if stop_after == "assemble":
                    return stop_draft(task_id, token, "assemble", result, settings)
                from app.module3.annotation_checks import annotate_questions

                annotate_questions(task, token, result, settings, checkpoint)
                if stop_after in {"annotate_sample", "annotate"}:
                    return stop_draft(task_id, token, "annotate", result, settings)
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
                if error.code.startswith("REFERENCE_")
                or error.code
                in {
                    "ENVIRONMENT_BLOCKED",
                    "CREDENTIALS_MISSING",
                    "BUDGET_LIMIT",
                    "ASSEMBLY_UNRESOLVED",
                    "ALIGNMENT_UNVERIFIED",
                    "ALIGNMENT_REVIEW_REQUIRED",
                    "METHOD_CHANGED",
                    "REFERENCE_TEXT_REQUIRED",
                    "REFERENCE_TEXT_CHANGED",
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
