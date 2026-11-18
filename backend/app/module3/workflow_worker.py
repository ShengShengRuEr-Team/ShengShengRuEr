"""Persistent stage executor. Each execution is an independently fenced child."""

import argparse
import copy
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import BASE_DIR, get_settings
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.db.base import SessionLocal
from app.db.models_listening import ExamPaper
from app.module3.annotation_identity import (
    RESULT_VERSION,
    question_input_hash,
    sample_dependency_hash,
)
from app.module3.candidate_diff import candidate_diff
from app.module3.contracts import ProcessingError, atomic_json, fingerprint, result_hash
from app.module3.distractor_annotations import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_V7,
    check_option_candidate,
    merge_option_candidate,
    normalize_candidate,
    option_input,
)
from app.module3.distractor_contract import generation_state
from app.services.processing import orchestration as o
from app.services.processing import tasks

MAX_EVIDENCE_CORRECTIONS = 2
CORRECTABLE_EVIDENCE_CODES = {
    "ANNOTATION_EVIDENCE_INVALID",
    "ANNOTATION_QUOTE_INVALID",
    "DISTRACTOR_OPTION_SET_INVALID",
    "DISTRACTOR_ASSESSMENT_MISSING",
    "ASSESSMENT_STATUS_CONFLICT",
    "ANNOTATION_SCHEMA_INVALID",
}


def annotation_checkpoint(command_id, token, task, payload, settings):
    with SessionLocal() as db:
        _, _, command = fence(db, command_id, token)
        current = tasks.fenced_task(db, task.id, token)
        record_artifact(db, command, current, "annotation_progress", payload, settings)
        db.commit()


def candidate_receipt(task, question, result, revision, artifact, raw, attempt):
    return {
        "question_src_id": question["_src_id"],
        "task_id": str(task.id),
        "artifact_id": artifact.id,
        "artifact_hash": artifact.artifact_hash,
        "attempt_id": attempt.id,
        "response_hash": fingerprint(attempt.response_payload),
        "candidate_hash": fingerprint(normalize_candidate(raw)),
        "question_input_hash": question_input_hash(result, question),
        "generation_input_hash": fingerprint(
            generation_input(result, question, task.request)
        ),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": fingerprint(SYSTEM_PROMPT_V7),
        "rules_manifest_hash": revision.rules_manifest["manifest_hash"],
        "state": generation_state(raw),
    }


def generate_candidate(
    command_id, token, task, revision, result, question, done, settings
):
    from app.module3.annotation_identity import rules_manifest
    from app.module3.llm import request_json
    from app.services.processing.candidate_recovery import (
        runtime_compatible,
        saved_candidate,
    )

    if not runtime_compatible(revision.rules_manifest, rules_manifest()):
        raise ProcessingError(
            "ANNOTATION_VERSION_MISMATCH", "生成方法已变化，旧任务不能收费继续"
        )

    with SessionLocal() as db:
        saved = saved_candidate(db, task, revision, result, question, settings)
    feedback = None
    previous_raw, previous_call = None, None
    history = []
    # An explicit semantic reprocess compares against the parent's raw response.
    projection = task.request.get("reuse_final_projection")
    if projection:
        with SessionLocal() as db:
            parent, _ = o.artifact_payload(db, projection["artifact_id"], settings)
            receipt = next(
                (
                    r
                    for r in parent.get("generation_receipts", [])
                    if r["question_src_id"] == question["_src_id"]
                ),
                None,
            )
            if receipt and parent.get("rules_manifest", {}).get(
                "candidate_version"
            ) == revision.rules_manifest.get("candidate_version"):
                original, _ = o.artifact_payload(db, receipt["artifact_id"], settings)
                previous_raw, previous_call = (
                    original["candidate"],
                    original["call"]["attempt_id"],
                )
    for correction in range(MAX_EVIDENCE_CORRECTIONS + 1):
        annotation_checkpoint(
            command_id,
            token,
            task,
            {
                "question_src_id": question["_src_id"],
                "question_index": question["question_index"],
                "completed_count": done,
                "correction": correction,
                "state": "correcting" if correction else "generating",
                "validation_code": feedback["code"] if feedback else None,
            },
            settings,
        )
        if saved:
            raw, call = saved
        else:
            kwargs = {"execution_token": token}
            if feedback:
                kwargs["validation_feedback"] = feedback
            raw, call = request_json(
                task.id,
                fingerprint({"audio": result["audio"]["file_hash"]}),
                "sample" if done < 5 else "run",
                SYSTEM_PROMPT_V7,
                generation_input(result, question, task.request),
                settings,
                **kwargs,
            )
        error = None
        try:
            check_option_candidate(result, question, raw)
        except (ProcessingError, ValidationError) as invalid:
            error = invalid
        validation = (
            {
                "state": "failed",
                "code": getattr(error, "code", "ANNOTATION_SCHEMA_INVALID"),
                "message": str(error),
            }
            if error
            else {"state": "passed"}
        )
        # Save every raw response before deciding whether to correct or stop.
        with SessionLocal() as db:
            _, _, command = fence(db, command_id, token)
            current = tasks.fenced_task(db, task.id, token)
            artifact = record_artifact(
                db,
                command,
                current,
                "candidate",
                {
                    "question_src_id": question["_src_id"],
                    "candidate": raw,
                    "call": call,
                    "question_input_hash": question_input_hash(result, question),
                    "rules_manifest": revision.rules_manifest,
                    "validation": validation,
                    "revision_diff": candidate_diff(
                        previous_raw,
                        raw,
                        before_call=previous_call,
                        after_call=call["attempt_id"],
                    )
                    if previous_raw is not None
                    else None,
                },
                settings,
            )
            receipt = None
            history.append(
                {"artifact_id": artifact.id, "artifact_hash": artifact.artifact_hash}
            )
            if error is None:
                receipt = candidate_receipt(
                    task,
                    question,
                    result,
                    revision,
                    artifact,
                    raw,
                    db.get(p.LlmAttempt, call["attempt_id"]),
                )
                receipt["revision_history"] = list(history)
            db.commit()
        previous_raw, previous_call = raw, call["attempt_id"]
        if error is None:
            return raw, receipt
        if (
            getattr(error, "code", "ANNOTATION_SCHEMA_INVALID")
            not in CORRECTABLE_EVIDENCE_CODES
            or correction == MAX_EVIDENCE_CORRECTIONS
        ):
            raise error
        feedback = {
            "candidate": raw,
            "code": getattr(error, "code", "ANNOTATION_SCHEMA_INVALID"),
            "message": str(error),
        }
        # A saved response has already passed current checks; never repair cache
        # corruption in place. A fresh request below is always separately fenced.
        saved = None


def lock_command_context(db, command_id):
    initial = db.get(m.ProcessingWorkflowCommand, command_id)
    if not initial:
        raise ProcessingError("LEASE_REVOKED", "操作不存在")
    workflow = db.get(m.ProcessingWorkflow, initial.workflow_id)
    if workflow.exam_paper_id:
        db.execute(
            select(ExamPaper.id)
            .where(ExamPaper.id == workflow.exam_paper_id)
            .with_for_update()
        )
    workflow = db.scalar(
        select(m.ProcessingWorkflow)
        .where(m.ProcessingWorkflow.id == workflow.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    revision = db.scalar(
        select(m.ProcessingWorkflowRevision)
        .where(m.ProcessingWorkflowRevision.id == initial.revision_id)
        .with_for_update()
    )
    command = db.scalar(
        select(m.ProcessingWorkflowCommand)
        .where(m.ProcessingWorkflowCommand.id == command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return workflow, revision, command


def fence(db, command_id, token):
    workflow, revision, command = lock_command_context(db, command_id)
    now = db.scalar(select(func.now()))
    if (
        command.state != "running"
        or command.execution_token != token
        or not command.lease_expires_at
        or command.lease_expires_at <= now
        or workflow.current_revision_id != revision.id
    ):
        raise ProcessingError("LEASE_REVOKED", "执行权已撤销或修订已切换")
    return workflow, revision, command


def record_artifact(db, command, task, stage, payload, settings):
    key = f"{task.id}/workflow-{stage}/{fingerprint(payload)}.json"
    sha, size = atomic_json(settings.m3_path("m3_artifacts_dir"), key, payload)
    row = p.ProcessingArtifact(
        task_id=task.id,
        stage="workflow_" + stage,
        input_hash=task.input_hash,
        method_hash=task.method_hash,
        storage_key=key,
        artifact_hash=sha,
        size_bytes=size,
        schema_version=RESULT_VERSION,
    )
    db.add(row)
    db.flush()
    return row


def heartbeat(command_id, token, settings, done):
    while not done.wait(settings.m3_heartbeat_seconds):
        try:
            with SessionLocal() as db:
                _workflow, _, command = fence(db, command_id, token)
                command.lease_expires_at = tasks.utcnow() + timedelta(
                    seconds=settings.m3_lease_seconds
                )
                if command.result.get("task_id"):
                    task = tasks.get_task(
                        db, UUID(command.result["task_id"]), lock=True
                    )
                    if task.state == "running" and task.lease_token == token:
                        tasks.heartbeat(db, task.id, token, settings.m3_lease_seconds)
                db.commit()
        except Exception:
            logging.getLogger(__name__).exception("Workflow heartbeat failed")
            return


def annotate(command_id, token, task, revision, settings):
    with SessionLocal() as db:
        assembly, _ = o.stage_payload(db, revision, "source", settings)
        result = copy.deepcopy(assembly)
        result["schema_version"] = RESULT_VERSION
        result["rules_manifest"] = revision.rules_manifest
        samples = {}
        if task.request.get("workflow_stage") == "annotate":
            sample, _ = o.stage_payload(db, revision, "sample", settings)
            for receipt in sample["generation_receipts"]:
                raw, _ = o.artifact_payload(db, receipt["artifact_id"], settings)
                samples[receipt["question_src_id"]] = (raw["candidate"], receipt)
        plan = task.request.get("repair_plan")
        if plan and task.request.get("reuse_final_projection"):
            parent, _ = o.artifact_payload(
                db, task.request["reuse_final_projection"]["artifact_id"], settings
            )
            for receipt in parent.get("generation_receipts", []):
                if receipt["question_src_id"] in plan["reusable_question_ids"]:
                    raw, _ = o.artifact_payload(db, receipt["artifact_id"], settings)
                    samples.setdefault(
                        receipt["question_src_id"], (raw["candidate"], receipt)
                    )
    receipts = []
    selected = (
        result["questions"][:5]
        if task.request["workflow_stage"] == "annotate_sample"
        else result["questions"]
    )
    for question in selected:
        with SessionLocal() as db:
            fence(db, command_id, token)
        qhash = question_input_hash(result, question)
        reused = samples.get(question["_src_id"])
        if reused:
            raw, receipt = reused
            if receipt["question_input_hash"] != qhash:
                raise ProcessingError("ARTIFACT_CHANGED", "小样题目依赖已变化")
        else:
            raw, receipt = generate_candidate(
                command_id,
                token,
                task,
                revision,
                result,
                question,
                len(receipts),
                settings,
            )
        check_option_candidate(result, question, raw)
        merge_option_candidate(result, question, raw)
        receipts.append(receipt)
        with SessionLocal() as db:
            result.setdefault("candidate_changes", []).extend(
                receipt_changes(db, receipt, settings)
            )
        annotation_checkpoint(
            command_id,
            token,
            task,
            {
                "question_src_id": question["_src_id"],
                "question_index": question["question_index"],
                "completed_count": len(receipts),
                "state": "validated",
            },
            settings,
        )
    result["generation_receipts"] = receipts
    return result


def execute(command_id, token, settings):
    done = threading.Event()
    renewal = threading.Thread(
        target=heartbeat, args=(command_id, token, settings, done), daemon=True
    )
    renewal.start()
    try:
        with SessionLocal() as db:
            workflow, revision, command = fence(db, command_id, token)
            stage = command.result["stage"]
            if stage == "publish":
                from app.services.processing.publication import execute_publication

                db.rollback()
                return execute_publication(command_id, token, settings)
            task = tasks.get_task(db, UUID(command.result["task_id"]))
            if task.method_hash != fingerprint(task.method):
                raise ProcessingError("ARTIFACT_CHANGED", "处理方法快照损坏")
        if stage in {"align", "assemble"}:
            from app.module3.worker import process

            if process(task.id, token, settings):
                raise ProcessingError("PROCESSING_FAILED", "处理失败，请查看阶段问题")
            with SessionLocal() as db:
                workflow, revision, command = fence(db, command_id, token)
                current = tasks.get_task(db, task.id)
                if stage == "align":
                    source = db.scalar(
                        select(p.ProcessingArtifact)
                        .where(
                            p.ProcessingArtifact.task_id == task.id,
                            p.ProcessingArtifact.stage == "align",
                        )
                        .order_by(p.ProcessingArtifact.id.desc())
                        .limit(1)
                    )
                    content, _ = o.artifact_payload(db, source.id, settings)
                else:
                    content = copy.deepcopy(tasks.get_draft(db, current).payload)
                    content.update(
                        schema_version=RESULT_VERSION,
                        rules_manifest=revision.rules_manifest,
                        generation_receipts=[],
                        source_materials=[
                            {
                                "material_id": v["material_id"],
                                "sha256": v["sha256"],
                                "kind": v["kind"],
                            }
                            for v in revision.materials_manifest.values()
                        ],
                    )
                db.rollback()
        else:
            content = annotate(command_id, token, task, revision, settings)
        with SessionLocal() as db:
            workflow, revision, command = fence(db, command_id, token)
            current = tasks.get_task(db, task.id, lock=True)
            output_stage = {
                "align": "align",
                "assemble": "source",
                "annotate_sample": "sample",
                "annotate": "final",
            }[stage]
            row = record_artifact(db, command, current, output_stage, content, settings)
            dependency = (
                sample_dependency_hash(content, revision.rules_manifest)
                if output_stage == "sample"
                else fingerprint(
                    {
                        "content": row.artifact_hash,
                        "materials": revision.materials_hash,
                        "rules": revision.rules_manifest["manifest_hash"],
                    }
                )
            )
            projection = {
                "task_id": str(task.id),
                "artifact_id": row.id,
                "artifact_hash": row.artifact_hash,
                "dependency_hash": dependency,
            }
            revision.stage_fingerprints = {
                **revision.stage_fingerprints,
                output_stage: projection,
            }
            if stage == "annotate":
                from app.services.processing.reviewing import validate_final

                validate_final(
                    db,
                    content,
                    current.request,
                    revision,
                    settings,
                    allow_incomplete=True,
                )
                tasks.store_draft(db, current, content, view="auto_draft")
                tasks.store_draft(db, current, content, view="final")
                revision.final_task_id, revision.final_result_hash = (
                    current.id,
                    result_hash(content),
                )
                revision.final_frozen_at = tasks.utcnow()
                db.flush()
                session = m.ProcessingReviewSession(
                    id=uuid4(),
                    revision_id=revision.id,
                    result_hash=revision.final_result_hash,
                    state="draft",
                    row_version=1,
                )
                db.add(session)
                current.state, current.stage = "completed", "review"
                (
                    workflow.processing_state,
                    workflow.content_review_state,
                    workflow.error_review_state,
                ) = "awaiting_review", "pending", "pending"
                command.result = {
                    **command.result,
                    "review_session_id": str(session.id),
                    "result_hash": revision.final_result_hash,
                }
            else:
                current.state = "awaiting_confirmation"
                workflow.processing_state = o.WAITING[output_stage]
            current.lease_token, current.expires_at = None, None
            command.state, command.execution_token, command.lease_expires_at = (
                "succeeded",
                None,
                None,
            )
            workflow.row_version += 1
            workflow.updated_at = func.now()
            db.commit()
        return 0
    except Exception as error:
        logging.getLogger(__name__).exception("Workflow stage failed")
        with SessionLocal() as db:
            try:
                workflow, _, command = fence(db, command_id, token)
            except ProcessingError:
                return 2
            command.state, command.failure_code = (
                "failed",
                getattr(error, "error_code", None)
                or getattr(error, "code", "PROCESSING_FAILED"),
            )
            command.execution_token, command.lease_expires_at = None, None
            workflow.processing_state = "failed"
            if command.result.get("stage") == "publish":
                workflow.publication_state = "failed"
            workflow.row_version += 1
            if command.result.get("task_id"):
                task = tasks.get_task(db, UUID(command.result["task_id"]), lock=True)
                task.state, task.lease_token, task.expires_at = "failed", None, None
                task.issues = [
                    *task.issues,
                    {
                        "issue_code": command.failure_code,
                        "message": str(error)
                        if isinstance(error, ProcessingError)
                        else "阶段未完成，请核对保存的结果和原件",
                        "severity": "error",
                    },
                ]
            db.commit()
        return 2
    finally:
        done.set()
        renewal.join(timeout=settings.m3_heartbeat_seconds + 1)


def generation_input(payload, question, request):
    data = option_input(payload, question)
    plan = request.get("repair_plan")
    if plan and question["_src_id"] in plan["affected_question_ids"]:
        data = {**data, "review_feedback": plan["feedback"]}
    return data


def receipt_changes(db, receipt, settings):
    changes = []
    for ref in receipt.get("revision_history", []):
        item, artifact = o.artifact_payload(db, ref["artifact_id"], settings)
        if (
            artifact.artifact_hash != ref["artifact_hash"]
            or item["question_src_id"] != receipt["question_src_id"]
        ):
            raise ProcessingError("ARTIFACT_CHANGED", "候选删改记录身份错误")
        diff = item.get("revision_diff")
        if diff and diff["changes"]:
            changes.append(
                {
                    "reference": "diff:" + fingerprint(diff),
                    "question_src_id": receipt["question_src_id"],
                    "diff": diff,
                }
            )
    return changes


def run_one(settings):
    from app.services.processing.uploads import expire_uploads

    with SessionLocal() as db:
        expire_uploads(db)
        # Execution with unknown external results is blocked for an explicit retry;
        # recovery never silently sends a second paid request.
        expired = db.scalars(
            select(m.ProcessingWorkflowCommand).where(
                m.ProcessingWorkflowCommand.state == "running",
                m.ProcessingWorkflowCommand.lease_expires_at <= func.now(),
            )
        ).all()
        for initial in expired:
            workflow, revision, command = lock_command_context(db, initial.id)
            if command.state != "running" or command.lease_expires_at > db.scalar(
                select(func.now())
            ):
                continue
            command.state, command.failure_code = "failed", "LEASE_REVOKED"
            command.execution_token = None
            workflow.processing_state = "failed"
            workflow.row_version += 1
            if command.result.get("task_id"):
                task = tasks.get_task(db, UUID(command.result["task_id"]))
                task.state, task.lease_token, task.expires_at = "failed", None, None
        db.commit()
        command = db.scalar(
            select(m.ProcessingWorkflowCommand)
            .where(m.ProcessingWorkflowCommand.state == "accepted")
            .order_by(
                m.ProcessingWorkflowCommand.created_at, m.ProcessingWorkflowCommand.id
            )
            .limit(1)
        )
        if not command:
            return None
        workflow, revision, command = lock_command_context(db, command.id)
        if command.state != "accepted" or workflow.current_revision_id != revision.id:
            db.rollback()
            return None
        token = uuid4()
        command.state, command.execution_token = "running", token
        command.lease_expires_at = tasks.utcnow() + timedelta(
            seconds=settings.m3_lease_seconds
        )
        workflow.processing_state = "running"
        workflow.row_version += 1
        if command.result.get("task_id"):
            task = tasks.get_task(db, UUID(command.result["task_id"]))
            task.state, task.lease_token, task.expires_at = (
                "running",
                token,
                command.lease_expires_at,
            )
            task.worker_id = f"workflow:{command.id}"
        command_id, workflow_id = command.id, workflow.id
        db.commit()
    log_path = (
        settings.m3_path("m3_artifacts_dir")
        / "operations"
        / str(command_id)
        / "worker.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.module3.workflow_worker",
            "--command-id",
            str(command_id),
            "--token",
            str(token),
        ],
        cwd=BASE_DIR,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=os.name != "nt",
    )
    log.close()
    while process.poll() is None:
        with SessionLocal() as db:
            command = db.get(m.ProcessingWorkflowCommand, command_id)
            stopped = command.state == "stopped" or (
                command.execution_token != token and command.state != "succeeded"
            )
        if stopped:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=30)
            break
        time.sleep(0.5)
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, command_id)
        workflow = db.get(m.ProcessingWorkflow, workflow_id)
        if workflow.processing_state == "stopping":
            workflow.processing_state = "stopped"
            workflow.row_version += 1
            if workflow.current_task_id:
                task = tasks.get_task(db, workflow.current_task_id)
                if task.state in {"running", "stopping"}:
                    task.state = "stopped"
        elif command.state == "running":
            command.state, command.failure_code, command.execution_token = (
                "failed",
                "WORKER_EXITED",
                None,
            )
            workflow.processing_state = "failed"
            workflow.row_version += 1
        db.commit()
    return process.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command-id", type=UUID, required=True)
    parser.add_argument("--token", type=UUID, required=True)
    args = parser.parse_args()
    return execute(args.command_id, args.token, get_settings())


if __name__ == "__main__":
    raise SystemExit(main())
