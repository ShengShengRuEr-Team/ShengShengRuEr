"""Stage-8 candidate gates, sample reuse, and text-only call orchestration.

These checks do not execute the stage-9 batch validator or create business rows.
Semantic review is a separate, content-hash-bound record, never an LLM self-score.
"""

import copy
import json

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import BASE_DIR
from app.db.base import SessionLocal
from app.db.models_processing import ProcessingArtifact
from app.module3.annotations import (
    SYSTEM_PROMPT,
    AnnotationCandidate,
    annotation_input,
    merge_candidate,
)
from app.module3.contracts import (
    ProcessingError,
    controlled_path,
    file_hash,
    fingerprint,
)
from app.module3.contracts import (
    result_hash as business_hash,
)
from app.module3.llm import request_json
from app.module3.reuse import implementation_hash
from app.services.processing import tasks
from app.services.processing.validation import load_dictionary

PROMPT_VERSION = "m3.annotations.v5"


def check_candidate(payload, question, raw):
    candidate = AnnotationCandidate.model_validate(raw)
    if candidate.question_src_id != question["_src_id"]:
        raise ProcessingError("ANNOTATION_REFERENCE_INVALID", "候选题号错误")
    tables = {t["name"]: t for t in load_dictionary()["tables"]}
    skills = {
        r["skill_code"]: r
        for r in tables["skill"]["rows"]
        if r["skill_level"] == 3
        and r["status"] == "启用"
        and r.get("usage_scope") == "题目标注"
    }
    errors = {
        r["error_cause_code"]
        for r in tables["error_cause"]["rows"]
        if r["cause_level"] == 3 and r["status"] == "启用"
    }
    if not any(s.role == "PRIMARY" for s in candidate.skills):
        raise ProcessingError("ANNOTATION_PRIMARY_MISSING", "每题必须有主要技能")
    if len({s.skill_code for s in candidate.skills}) != len(candidate.skills) or any(
        s.skill_code not in skills for s in candidate.skills
    ):
        raise ProcessingError("ANNOTATION_DICTIONARY_INVALID", "技能非法/重复/不适用")
    if any(e.error_cause_code not in errors for e in candidate.candidate_errors):
        raise ProcessingError("ANNOTATION_DICTIONARY_INVALID", "错因编号非法")
    segments = {s["_src_id"]: s for s in payload["transcript_segments"]}
    for evidence_path, evidence in [
        *[(f"skills[{i}]", e) for i, e in enumerate(candidate.skills)],
        *[
            (f"answer_evidence[{i}]", e)
            for i, e in enumerate(candidate.answer_evidence)
        ],
        *[
            (f"candidate_errors[{i}]", e)
            for i, e in enumerate(candidate.candidate_errors)
        ],
    ]:
        refs = evidence.evidence_segment_src_ids
        if (
            not refs
            or len(refs) != len(set(refs))
            or any(r not in segments for r in refs)
        ):
            raise ProcessingError(
                "ANNOTATION_EVIDENCE_INVALID", evidence_path + ": 证据引用不存在或重复"
            )
        selected = [segments[r] for r in refs]
        if any(
            s["segment_type"] != "body"
            or s["passage_src_id"] != question["passage_src_id"]
            or s["alignment_status"] != "aligned"
            or not 0 <= s["start_ms"] < s["end_ms"]
            for s in selected
        ):
            raise ProcessingError(
                "ANNOTATION_EVIDENCE_INVALID",
                evidence_path + ": 证据跨篇/提问/无有效时间",
            )
        positions = [s["segment_index"] for s in selected]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise ProcessingError(
                "ANNOTATION_EVIDENCE_INVALID",
                f"{evidence_path}: 证据必须为连续有序正文句；收到 {refs}",
            )
        quote = " ".join(s["text"] for s in selected)
        if not (
            evidence.quote == quote or (len(refs) == 1 and evidence.quote in quote)
        ):
            raise ProcessingError(
                "ANNOTATION_QUOTE_INVALID", evidence_path + ": 引文无法在正文定位"
            )
    if any(not e.support_note for e in candidate.answer_evidence):
        raise ProcessingError("ANNOTATION_SUPPORT_MISSING", "答案证据须解释支持依据")
    return {
        "question_src_id": question["_src_id"],
        "status": "PASS",
        "checks": [
            "schema",
            "dictionary",
            "primary",
            "quote",
            "body_ownership",
            "consecutive",
            "aligned_time",
            "support_present",
        ],
        "semantic_accuracy": "requires separate content review",
    }


def sample_candidates(task, result, settings):
    source_id = task.request.get("reuse_annotation_task_id")
    if not source_id:
        return {}
    with SessionLocal() as db:
        source = tasks.get_task(db, source_id)
        draft = tasks.get_draft(db, source)
        if implementation_hash(
            source.method, "app/module3/annotations.py"
        ) != file_hash(BASE_DIR / "app/module3/annotations.py"):
            raise ProcessingError(
                "ANNOTATION_SAMPLE_CHANGED", "小样提示词/契约实现已变化"
            )
        review = task.request["sample_review"]
        if (
            source.state != "awaiting_confirmation"
            or source.stage != "annotate"
            or source.request.get("stop_after") != "annotate_sample"
            or draft is None
            or source.method_hash != fingerprint(source.method)
            or business_hash(draft.payload) != draft.result_hash
            or source.exam_paper_code != task.exam_paper_code
            or source.method["dictionary_sha256"] != task.method["dictionary_sha256"]
            or source.method["prompt_version"] != PROMPT_VERSION
            or review.get("result_hash") != draft.result_hash
            or review.get("decision") != "approved"
            or not review.get("reviewer")
            or not review.get("reviewed_at")
        ):
            raise ProcessingError(
                "ANNOTATION_SAMPLE_REVIEW_REQUIRED", "小样及其逐题语义复核不匹配"
            )
        items = review.get("items", [])
        expected = {q["_src_id"] for q in result["questions"][:5]}
        if (
            {i.get("question_src_id") for i in items} != expected
            or len(items) != len(expected)
            or any(
                i.get("decision") != "approved"
                or not i.get("support_reason")
                or not i.get("skill_reason")
                for i in items
            )
        ):
            raise ProcessingError(
                "ANNOTATION_SAMPLE_REVIEW_REQUIRED", "小样逐题支持依据/技能适用复核缺失"
            )
        for q in result["questions"]:
            old = next(
                (x for x in draft.payload["questions"] if x["_src_id"] == q["_src_id"]),
                None,
            )
            if old != q:
                raise ProcessingError(
                    "ANNOTATION_SAMPLE_CHANGED", "小样与整套的来源题目不同"
                )
        if draft.payload["transcript_segments"] != result["transcript_segments"]:
            raise ProcessingError(
                "ANNOTATION_SAMPLE_CHANGED", "小样与整套的正文/时间不同"
            )
        rows = db.scalars(
            select(ProcessingArtifact)
            .where(
                ProcessingArtifact.task_id == source.id,
                ProcessingArtifact.stage == "annotate",
            )
            .order_by(ProcessingArtifact.id)
        ).all()
        candidates = {}
        for row in rows:
            path = controlled_path(
                settings.m3_path("m3_artifacts_dir"), row.storage_key
            )
            if file_hash(path) != row.artifact_hash:
                raise ProcessingError("ANNOTATION_SAMPLE_CHANGED", "小样产物哈希变化")
            data = json.loads(path.read_text(encoding="utf-8"))
            candidates[data["question_src_id"]] = data
        if set(candidates) != expected:
            raise ProcessingError("ANNOTATION_SAMPLE_INCOMPLETE", "5题真实小样不完整")
        return candidates


def reviewed_full_candidates(task, result, settings):
    """Retain approved candidates; rerun only hash-bound semantic repair items."""
    source_id = task.request.get("reuse_full_annotation_task_id")
    if not source_id:
        return {}, {}
    with SessionLocal() as db:
        source = tasks.get_task(db, source_id)
        draft = tasks.get_draft(db, source)
        review = task.request["annotation_review"]
        if (
            source.state != "awaiting_confirmation"
            or source.stage != "annotate"
            or source.request.get("stop_after") != "annotate"
            or draft is None
            or source.method_hash != fingerprint(source.method)
            or business_hash(draft.payload) != draft.result_hash
            or source.exam_paper_code != task.exam_paper_code
            or source.method["dictionary_sha256"] != task.method["dictionary_sha256"]
            or source.method["prompt_version"] != PROMPT_VERSION
            or implementation_hash(source.method, "app/module3/annotations.py")
            != file_hash(BASE_DIR / "app/module3/annotations.py")
            or review.get("result_hash") != draft.result_hash
            or review.get("decision") not in {"approved", "changes_required"}
            or not review.get("reviewer")
            or not review.get("reviewed_at")
            or draft.payload["questions"] != result["questions"]
            or draft.payload["transcript_segments"] != result["transcript_segments"]
        ):
            raise ProcessingError(
                "ANNOTATION_REPAIR_REVIEW_INVALID", "整套修复来源或复核哈希/方法不匹配"
            )
        expected = {q["_src_id"] for q in result["questions"]}
        items = review.get("items", [])
        if (
            len(items) != len(expected)
            or {i.get("question_src_id") for i in items} != expected
        ):
            raise ProcessingError(
                "ANNOTATION_REPAIR_REVIEW_INVALID", "整套复核须逐题完整覆盖"
            )
        rows = db.scalars(
            select(ProcessingArtifact).where(
                ProcessingArtifact.task_id == source.id,
                ProcessingArtifact.stage == "annotate",
            )
        ).all()
        candidates = {}
        for row in rows:
            path = controlled_path(
                settings.m3_path("m3_artifacts_dir"), row.storage_key
            )
            if file_hash(path) != row.artifact_hash:
                raise ProcessingError(
                    "ANNOTATION_SAMPLE_CHANGED", "整套来源候选产物哈希变化"
                )
            value = json.loads(path.read_text(encoding="utf-8"))
            if value["question_src_id"] in candidates:
                raise ProcessingError(
                    "ANNOTATION_REPAIR_REVIEW_INVALID", "整套来源存在重复候选"
                )
            candidates[value["question_src_id"]] = {
                **value,
                "source_task_id": str(source.id),
            }
        if set(candidates) != expected:
            raise ProcessingError(
                "ANNOTATION_REPAIR_REVIEW_INVALID", "整套来源候选不完整"
            )
        approved, feedback = {}, {}
        for item in items:
            qid = item["question_src_id"]
            if not item.get("support_reason") or not item.get("skill_reason"):
                raise ProcessingError(
                    "ANNOTATION_REPAIR_REVIEW_INVALID", "逐题修复复核缺少依据"
                )
            if item.get("decision") == "approved":
                approved[qid] = candidates[qid]
            elif item.get("decision") == "changes_required" and item.get(
                "repair_feedback"
            ):
                feedback[qid] = {
                    "issue_code": "ANNOTATION_SEMANTIC_REVIEW",
                    "message": item["repair_feedback"],
                    "previous_candidate": candidates[qid]["candidate"],
                    "repair_contract": (
                        "Return a revised annotation using only supplied "
                        "source data; do not alter answers/text/time."
                    ),
                }
            else:
                raise ProcessingError(
                    "ANNOTATION_REPAIR_REVIEW_INVALID", "未决题须有具体修复反馈"
                )
        if task.request.get("stop_after") == "completed" and (
            review.get("decision") != "approved" or feedback
        ):
            raise ProcessingError(
                "ANNOTATION_IMPORT_REVIEW_REQUIRED", "入库前整套标注复核必须全部通过"
            )
        return approved, feedback


def annotate_questions(task, token, result, settings, checkpoint):
    reviewed, review_feedback = reviewed_full_candidates(task, result, settings)
    reused = {**reviewed, **sample_candidates(task, result, settings)}
    selected = (
        result["questions"][:5]
        if task.request.get("stop_after") == "annotate_sample"
        else result["questions"]
    )
    run_key = fingerprint({"audio": result["audio"]["file_hash"]})
    checks = []
    for index, question in enumerate(selected):
        previous = reused.get(question["_src_id"])
        feedback = review_feedback.get(question["_src_id"])
        for validation_attempt in range(3):
            if previous is not None:
                raw, call = (
                    previous["candidate"],
                    {
                        **previous["call"],
                        "reused_from_task_id": previous.get("source_task_id")
                        or task.request["reuse_annotation_task_id"],
                    },
                )
            else:
                data = annotation_input(result, question)
                if feedback is not None:
                    data["validation_feedback"] = feedback
                if question["_src_id"] in review_feedback:
                    data["semantic_review_constraints"] = review_feedback[
                        question["_src_id"]
                    ]
                raw, call = request_json(
                    task.id,
                    run_key,
                    "sample" if index < 5 else "run",
                    SYSTEM_PROMPT,
                    data,
                    settings,
                )
            checkpoint(
                task.id,
                token,
                "annotation_raw",
                {
                    "question_src_id": question["_src_id"],
                    "candidate": raw,
                    "call": call,
                    "prompt_version": PROMPT_VERSION,
                    "validation_attempt": validation_attempt,
                },
                settings,
            )
            try:
                check = check_candidate(result, question, raw)
            except (ProcessingError, ValidationError) as error:
                feedback = {
                    "issue_code": getattr(error, "code", "ANNOTATION_SCHEMA_INVALID"),
                    "message": str(error)[:1200],
                    "previous_candidate": raw,
                    "optional_candidate_policy": (
                        "candidate_errors is OPTIONAL. If an error names "
                        "candidate_errors[i], fix that exact object or omit it. "
                        "Prefer [] over stretching a quote across unrelated "
                        "sentences. Keep required skills and answer evidence."
                    ),
                    "repair_contract": (
                        "Correct the cited output-contract failure. Use existing "
                        "consecutive body IDs and exact quotes; do not skip IDs, "
                        "invent dictionary codes, alter source fields or supply times."
                    ),
                }
                checkpoint(
                    task.id,
                    token,
                    "annotation_rejected",
                    {
                        "question_src_id": question["_src_id"],
                        "candidate": raw,
                        "call": call,
                        "prompt_version": PROMPT_VERSION,
                        "validation_attempt": validation_attempt,
                        "failure": feedback,
                    },
                    settings,
                )
                if previous is not None or validation_attempt == 2:
                    raise
                continue
            break
        merged = copy.deepcopy(result)
        merge_candidate(merged, question, raw)
        result.clear()
        result.update(merged)
        checks.append(check)
        checkpoint(
            task.id,
            token,
            "annotate",
            {
                "question_src_id": question["_src_id"],
                "candidate": raw,
                "call": call,
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": fingerprint(SYSTEM_PROMPT),
                "checks": check,
            },
            settings,
        )
    checkpoint(
        task.id,
        token,
        "annotation_checks",
        {
            "status": "PASS",
            "question_count": len(selected),
            "questions": checks,
            "sample_review": task.request.get("sample_review"),
            "annotation_review": task.request.get("annotation_review"),
            "semantic_accuracy": "separate review required; structure is not accuracy",
        },
        settings,
    )
