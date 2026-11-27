"""Run/resume a local P6 evaluation through fenced, budgeted candidate-only jobs."""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select

from app.core.config import BASE_DIR, get_settings
from app.core.errors import AppError
from app.db import models_annotations as _annotations  # noqa: F401
from app.db import models_library as library_models
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.db.base import SessionLocal
from app.db.models import Role, User, UserRole
from app.db.models_listening import ExamPaper
from app.module3 import comparison, providers
from app.module3.annotation_identity import question_input_hash, rules_manifest
from app.module3.contracts import ProcessingError, file_hash, fingerprint
from app.module3.distractor_annotations import SYSTEM_PROMPT_V7, check_option_candidate
from app.module3.workflow_worker import generation_input
from app.schemas_library import EvaluationCandidates
from app.services.processing import library_content as content
from app.services.processing import library_editing as editing
from app.services.processing import library_generation as generation
from app.services.processing import orchestration as o
from app.services.processing import workflows as w

FATAL = {
    "LLM_AUTH",
    "LLM_HTTP",
    "LLM_TRANSPORT",
    "BUDGET_LIMIT",
    "BUDGET_AUDIT_BLOCKED",
    "CREDENTIALS_MISSING",
    "PRICE_CONFIGURATION_REQUIRED",
    "PROVIDER_REGION_UNSUPPORTED",
    "LEASE_REVOKED",
    "ANNOTATION_VERSION_MISMATCH",
    "ARTIFACT_CHANGED",
    "SOURCE_CHANGED",
    "METHOD_CHANGED",
}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def frozen_context(workflow_id, username, settings):
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .join(UserRole)
            .join(Role)
            .where(
                User.username == username,
                User.status == "active",
                Role.role_key == "admin",
            )
        )
        if not user:
            raise ProcessingError("ADMIN_REQUIRED", "评测须指定本地有效管理员")
        workflow = db.get(m.ProcessingWorkflow, workflow_id)
        if not workflow or not workflow.exam_paper_id:
            raise ProcessingError("SOURCE_REQUIRED", "须先完成真实材料来源组装")
        paper = db.get(ExamPaper, workflow.exam_paper_id)
        if (paper.exam_level, paper.exam_year, paper.exam_month, paper.paper_set) != (
            "CET4",
            2025,
            6,
            1,
        ):
            raise ProcessingError(
                "COMPARISON_SAMPLE_INVALID", "P6固定使用2025年6月CET4第1套"
            )
        editing.available(db, workflow, paper)
        parent = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
        source, projection = o.stage_payload(db, parent, "source", settings)
        snapshot = content.canonical_snapshot(content.projection(source))
        comparison.compare(source, {})  # Validate the fixed sample before any charge.
        return (
            source,
            projection,
            {
                "operator_user_id": user.id,
                "workflow_id": str(workflow_id),
                "source_revision_id": str(parent.id),
                "expected_row_version": paper.library_row_version,
                "expected_content_hash": fingerprint(snapshot),
                "source_dependency_hash": projection["dependency_hash"],
                "source_artifact_hash": projection["artifact_hash"],
                "rules_manifest": rules_manifest(),
                "prompt_sha256": fingerprint(SYSTEM_PROMPT_V7),
                "edit_head_before": head_identity(db, paper.id),
            },
        )


def head_identity(db, paper_id):
    head = db.get(library_models.LibraryEditHead, paper_id)
    return (
        {
            "revision_id": str(head.revision_id),
            "row_version": head.row_version,
            "save_version_id": str(head.current_save_version_id)
            if head.current_save_version_id
            else None,
        }
        if head
        else None
    )


def observations(command_id, source, question, settings):
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, command_id)
        task = db.get(p.ProcessingTask, UUID(command.result["task_id"]))
        attempts = db.scalars(
            select(p.LlmAttempt)
            .where(p.LlmAttempt.task_id == task.id)
            .order_by(p.LlmAttempt.id)
        ).all()
        attempts_data = []
        raw = None
        trusted = False
        reason = command.failure_code
        for attempt in attempts:
            parsed = None
            valid_response = False
            try:
                choice = attempt.response_payload["choices"][0]
                parsed = json.loads(
                    choice["message"]["content"],
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("nonfinite")
                    ),
                )
                valid_response = (
                    isinstance(parsed, dict) and choice["finish_reason"] == "stop"
                )
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            request = attempt.request_payload
            bound = False
            try:
                bound = (
                    attempt.request_hash == fingerprint(request)
                    and request["model"]
                    == task.method["provider_manifest"]["requested_model"]
                    and request["messages"][0]["content"].startswith(
                        SYSTEM_PROMPT_V7 + "\nReturn JSON."
                    )
                    and json.loads(request["messages"][1]["content"])
                    == generation_input(source, question, task.request)
                    and attempt.provider_manifest == task.method["provider_manifest"]
                )
            except (KeyError, TypeError, ValueError):
                pass
            first_valid = False
            if valid_response and bound:
                try:
                    validation = check_option_candidate(source, question, parsed)
                    first_valid = (
                        validation["generation_state"] != "generation_incomplete"
                    )
                except (ProcessingError, ValueError):
                    pass
            attempts_data.append(
                {
                    "attempt_id": attempt.id,
                    "status": attempt.status,
                    "error_code": attempt.error_code,
                    "response_model": attempt.response_model,
                    "request_hash": attempt.request_hash,
                    "billing_status": attempt.billing_status,
                    "reserved_usd": str(attempt.reserved_usd),
                    "charged_usd": str(attempt.charged_usd)
                    if attempt.charged_usd is not None
                    else None,
                    "currency": attempt.currency,
                    "original_reserved": str(attempt.original_reserved),
                    "original_charged": str(attempt.original_charged)
                    if attempt.original_charged is not None
                    else None,
                    "usage": attempt.usage_detail,
                    "exchange_rate": attempt.exchange_rate,
                    "full_candidate_valid": first_valid,
                    "response_bound_to_input": bound,
                }
            )
            # Only the final model output is used, never an earlier/human repair.
            raw = parsed if valid_response else None
            trusted = valid_response and bound
        classification = reason
        if reason == "PROCESSING_FAILED" and attempts:
            artifact = db.scalar(
                select(p.ProcessingArtifact)
                .where(
                    p.ProcessingArtifact.task_id == task.id,
                    p.ProcessingArtifact.stage == "workflow_candidate",
                    p.ProcessingArtifact.method_hash == task.method_hash,
                    p.ProcessingArtifact.input_hash == task.input_hash,
                )
                .order_by(p.ProcessingArtifact.id.desc())
                .limit(1)
            )
            if artifact:
                value, _artifact = o.artifact_payload(db, artifact.id, settings)
                if (
                    value.get("call", {}).get("attempt_id") == attempts[-1].id
                    and value.get("validation", {}).get("state") == "failed"
                    and value["validation"].get("code") == "ANNOTATION_SCHEMA_INVALID"
                ):
                    classification = "ANNOTATION_SCHEMA_INVALID"
        elapsed = max(0, (task.updated_at - task.created_at).total_seconds())
        return {
            "origin_type": "AI",
            "execution_state": "executed" if attempts else "not_executed",
            "complete_record": trusted,
            "raw": raw,
            "question_input_hash": question_input_hash(source, question),
            "dictionary_sha256": task.method["rules_manifest"]["dictionary_sha256"],
            "reason": reason or (None if trusted else "缺少可信完整响应"),
            "failure_classification": classification,
            "operation_id": str(command.id),
            "task_id": str(task.id),
            "revision_id": str(command.revision_id),
            "command_state": command.state,
            "attempts": attempts_data,
            "correction_count": max(0, len(attempts) - 1),
            "first_pass": bool(
                attempts_data and attempts_data[0]["full_candidate_valid"]
            ),
            "elapsed_worker_seconds": elapsed,
        }


def execution_summary(records, methods):
    result = {}
    from decimal import Decimal

    for provider in comparison.PROVIDERS:
        rows = list(records.get(provider, {}).values())
        attempts = [a for row in rows for a in row.get("attempts", [])]
        charged = sum(
            (
                Decimal(a["charged_usd"])
                for a in attempts
                if a["charged_usd"] is not None
            ),
            Decimal(0),
        )
        reserved = sum(
            (Decimal(a["reserved_usd"]) for a in attempts if a["charged_usd"] is None),
            Decimal(0),
        )
        result[provider] = {
            "method": methods[provider],
            "questions_executed": sum(bool(r.get("attempts")) for r in rows),
            "questions_not_executed": sum(
                r.get("execution_state") == "not_executed" for r in rows
            ),
            "first_pass": comparison.metric(
                sum(r.get("first_pass", False) for r in rows), 25
            ),
            "corrections": sum(r.get("correction_count", 0) for r in rows),
            "attempt_count": len(attempts),
            "estimated_usd": str(charged),
            "unknown_reserved_usd": str(reserved),
            "committed_usd": str(charged + reserved),
            "response_models": sorted(
                {a["response_model"] for a in attempts if a["response_model"]}
            ),
            "elapsed_worker_seconds": sum(
                r.get("elapsed_worker_seconds", 0) for r in rows
            ),
            "questions": [
                {
                    k: v
                    for k, v in row.items()
                    if k
                    not in {
                        "raw",
                        "question_input_hash",
                        "dictionary_sha256",
                        "origin_type",
                        "complete_record",
                    }
                }
                for row in rows
            ],
        }
    return result


def recover_records(source, manifest, stored, settings):
    """Rebuild completed observations from immutable calls rather than edited JSON."""
    result = {provider: {} for provider in comparison.PROVIDERS}
    evaluation_id = UUID(manifest["evaluation_id"])
    for provider in comparison.PROVIDERS:
        for question in source["questions"]:
            qid = question["_src_id"]
            previous = stored.get(provider, {}).get(qid)
            key = uuid5(evaluation_id, provider + ":" + qid)
            with SessionLocal() as db:
                command = w.command_by_key(
                    db, manifest["operator_user_id"], "library_generate", key
                )
                if command and (
                    str(command.workflow_id) != manifest["workflow_id"]
                    or command.request.get("evaluation_id") != manifest["evaluation_id"]
                    or command.request.get("provider") != provider
                    or command.request.get("question_src_ids") != [qid]
                ):
                    raise ProcessingError(
                        "COMPARISON_RECORD_UNTRUSTED", "评测操作归属不一致"
                    )
                command_id = command.id if command else None
                state = command.state if command else None
            if command_id and state not in {"accepted", "running"}:
                result[provider][qid] = observations(
                    command_id, source, question, settings
                )
            elif previous:
                if previous.get("execution_state") == "executed":
                    raise ProcessingError(
                        "COMPARISON_RECORD_UNTRUSTED", "已执行记录缺少终态数据库操作"
                    )
                result[provider][qid] = previous
    return result


def fatal_reason(record):
    code = record.get("failure_classification") or record.get("reason")
    return code if code in FATAL | {"PROCESSING_FAILED"} else None


def budget_snapshot(source, settings):
    """Read-only conservative admission snapshot; the request gate still reserves."""
    from decimal import Decimal

    from app.module3.llm import external_commitments

    key = providers.paper_budget_key(source)
    external = external_commitments(key)
    with SessionLocal() as db:
        rows = db.scalars(select(p.LlmAttempt)).all()

        def cost(row):
            return row.charged_usd if row.charged_usd is not None else row.reserved_usd

        total = sum((cost(row) for row in rows), external[0])
        paper = sum(
            (
                cost(row)
                for row in rows
                if row.paper_budget_key == key or row.run_key == key
            ),
            external[1],
        )
    return {
        "budget_enforced": settings.m3_budget_enforced,
        "override_reference": settings.m3_budget_override_reference
        if not settings.m3_budget_enforced
        else None,
        "total_committed_usd": str(total),
        "paper_committed_usd": str(paper),
        "total_limit_usd": str(settings.m3_total_budget_usd),
        "paper_limit_usd": str(settings.m3_run_budget_usd),
        "unknown_attempts_external": int(external[3]),
        "limit_reached": settings.m3_budget_enforced
        and (
            total >= Decimal(str(settings.m3_total_budget_usd))
            or paper >= Decimal(str(settings.m3_run_budget_usd))
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=UUID, required=True)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--listening-waiver-reference", required=True)
    parser.add_argument(
        "--question-indices",
        nargs="+",
        type=int,
        help="Run only these question numbers; preserve the full 25/75 report",
    )
    parser.add_argument(
        "--resume-executor-fix-reference",
        help="Audit an executor-only fix; frozen inputs must match",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly allow budgeted paid calls; default produces a dry-run report",
    )
    args = parser.parse_args()
    selected = set(args.question_indices or range(1, 26))
    if not selected <= set(range(1, 26)):
        parser.error("question-indices must be within 1..25")
    settings = get_settings()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source, projection, context = frozen_context(
        args.workflow, args.admin_username, settings
    )
    path = out / "manifest.json"
    methods = {
        provider: providers.freeze(provider, settings)
        for provider in comparison.PROVIDERS
    }
    manifest = {
        **context,
        "source_hash": fingerprint(source),
        "provider_methods": methods,
        "listening_review": {
            "state": "waived_by_user",
            "actual_listening_performed": False,
            "reference": args.listening_waiver_reference,
        },
        "evaluation_only": True,
        "comparison_sha256": file_hash(BASE_DIR / "app/module3/comparison.py"),
        "executor_sha256": file_hash(Path(__file__)),
    }
    if args.question_indices is not None:
        manifest["selected_question_indices"] = sorted(selected)
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        prior = {
            k: v for k, v in old.items() if k not in {"evaluation_id", "created_at"}
        }
        if prior != manifest:
            compatible = {k: v for k, v in prior.items() if k != "executor_sha256"} == {
                k: v for k, v in manifest.items() if k != "executor_sha256"
            }
            if not compatible or not args.resume_executor_fix_reference:
                raise ProcessingError(
                    "COMPARISON_MANIFEST_CHANGED",
                    "来源或模型方法变化，不能续用原评测；仅执行器修复须记录依据",
                )
            journal = out / "executor-revisions.json"
            entries = (
                json.loads(journal.read_text(encoding="utf-8"))
                if journal.exists()
                else []
            )
            if (
                not entries
                or entries[-1]["current_sha256"] != manifest["executor_sha256"]
            ):
                entries.append(
                    {
                        "previous_sha256": old["executor_sha256"],
                        "current_sha256": manifest["executor_sha256"],
                        "reference": args.resume_executor_fix_reference,
                        "recorded_at": datetime.now(UTC).isoformat(),
                    }
                )
                write_json(journal, entries)
        manifest = old
    else:
        manifest.update(
            evaluation_id=str(uuid4()), created_at=datetime.now(UTC).isoformat()
        )
        write_json(path, manifest)
        write_json(out / "source.json", source)
    records = {provider: {} for provider in comparison.PROVIDERS}
    records_path = out / "records.json"
    if records_path.exists():
        records = recover_records(
            source,
            manifest,
            json.loads(records_path.read_text(encoding="utf-8")),
            settings,
        )
    budget = None
    admission_failure = None
    if args.execute:
        try:
            budget = budget_snapshot(source, settings)
            if budget["limit_reached"]:
                admission_failure = (
                    "BUDGET_LIMIT: 历史已知费用与未知预留已达到原有单套或阶段总上限"
                )
        except ProcessingError as error:
            admission_failure = error.code + ": " + str(error)
    write_json(
        out / "budget-admission.json",
        {"budget": budget, "blocked_reason": admission_failure},
    )

    def save():
        write_json(records_path, records)
        metadata = {
            **manifest,
            "execution": execution_summary(records, methods),
            "paid_execution_authorized": args.execute,
            "budget_admission": {"budget": budget, "blocked_reason": admission_failure},
            "executor_revisions": json.loads(
                (out / "executor-revisions.json").read_text(encoding="utf-8")
            )
            if (out / "executor-revisions.json").exists()
            else [],
        }
        report = comparison.compare(source, records, metadata=metadata)
        write_json(out / "comparison.json", report)
        (out / "comparison.md").write_text(
            comparison.render_markdown(report), encoding="utf-8"
        )

    evaluation_id = UUID(manifest["evaluation_id"])
    for provider in comparison.PROVIDERS:
        fatal = admission_failure
        for question in sorted(source["questions"], key=lambda q: q["question_index"]):
            qid = question["_src_id"]
            if question["question_index"] not in selected:
                records[provider][qid] = {
                    "execution_state": "not_executed",
                    "reason": "OUT_OF_SCOPE: excluded from the selected rerun",
                }
                continue
            if (
                qid in records[provider]
                and records[provider][qid].get("execution_state") == "executed"
            ):
                previous_failure = fatal_reason(records[provider][qid])
                audit_recovered = (
                    previous_failure == "BUDGET_AUDIT_BLOCKED"
                    and args.resume_executor_fix_reference
                    and budget is not None
                    and admission_failure is None
                )
                if previous_failure and not audit_recovered:
                    fatal = previous_failure
                continue
            if not args.execute or fatal:
                records[provider][qid] = {
                    "execution_state": "not_executed",
                    "reason": fatal or "未显式授权执行收费调用",
                }
                continue
            key = uuid5(evaluation_id, provider + ":" + qid)
            try:
                if (
                    rules_manifest() != context["rules_manifest"]
                    or providers.freeze(provider, settings) != methods[provider]
                ):
                    raise ProcessingError(
                        "METHOD_CHANGED", "评测期间冻结方法变化，停止新调用"
                    )
                payload = EvaluationCandidates(
                    expected_row_version=context["expected_row_version"],
                    expected_content_hash=context["expected_content_hash"],
                    reason="P6 independent comparison; preserve model-only candidates",
                    question_src_ids=[qid],
                    provider=provider,
                    evaluation_id=evaluation_id,
                    evaluation_source_hash=projection["dependency_hash"],
                    evaluation_source_revision_id=UUID(context["source_revision_id"]),
                    listening_waiver_reference=args.listening_waiver_reference,
                )
                with SessionLocal() as db:
                    command = generation.generate(
                        db,
                        args.workflow,
                        payload,
                        context["operator_user_id"],
                        key,
                        settings,
                    )
                    command_id = command.id
                    db.commit()
                while True:
                    with SessionLocal() as db:
                        command = db.get(m.ProcessingWorkflowCommand, command_id)
                        state = command.state
                    if state not in {"accepted", "running"}:
                        break
                    if state == "accepted":
                        with (out / "worker.log").open("ab") as log:
                            subprocess.run(
                                [
                                    settings.m3_asr_python or sys.executable,
                                    "-m",
                                    "app.module3.worker",
                                    "--once",
                                ],
                                cwd=BASE_DIR,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                                check=False,
                            )
                    else:
                        time.sleep(0.5)
                record = observations(command_id, source, question, settings)
                records[provider][qid] = record
                if fatal_reason(record):
                    fatal = fatal_reason(record)
            except (ProcessingError, AppError) as error:
                code = getattr(error, "error_code", None) or getattr(
                    error, "code", "COMPARISON_BLOCKED"
                )
                records[provider][qid] = {
                    "execution_state": "not_executed",
                    "reason": str(code) + ": " + str(error),
                }
                fatal = str(code)
            save()
            state = records[provider][qid]["execution_state"]
            print(
                f"{provider} question {question['question_index']}: {state}",
                flush=True,
            )
        save()
    with SessionLocal() as db:
        workflow = db.get(m.ProcessingWorkflow, args.workflow)
        paper = db.get(ExamPaper, workflow.exam_paper_id)
        if (
            paper.library_row_version != context["expected_row_version"]
            or str(workflow.current_revision_id) != context["source_revision_id"]
            or head_identity(db, paper.id) != context["edit_head_before"]
        ):
            raise ProcessingError(
                "EDIT_HEAD_CHANGED", "评测期间编辑内容发生变化，请保留报告并核对"
            )
    print("Report: " + str(out / "comparison.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
