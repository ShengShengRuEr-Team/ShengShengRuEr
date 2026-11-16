"""Hash-bound full-paper review; saving opinions never changes content or calls LLMs."""

import copy
import json

from sqlalchemy import func, select

from app.core.errors import AppError
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import question_input_hash, rules_manifest
from app.module3.contracts import fingerprint, result_hash
from app.module3.option_annotations import (
    SYSTEM_PROMPT_V2,
    check_option_candidate,
    merge_option_candidate,
    normalize_candidate,
)
from app.schemas_processing import ReviewRequest
from app.services.processing import orchestration as o
from app.services.processing import tasks
from app.services.processing import workflows as w
from app.services.processing.validation import validate_result


def validate_final(db, payload, request, revision, settings):
    from app.module3.workflow_worker import generation_input
    from app.services.processing.reprocessing import ancestor_revision

    if (
        payload.get("schema_version") != "m3.v2"
        or payload.get("rules_manifest") != revision.rules_manifest
        or revision.rules_manifest != rules_manifest()
    ):
        raise w.conflict("ARTIFACT_CHANGED", "当前结果不属于有效的新规则方法")
    issues = validate_result(payload, request)
    if issues:
        raise w.conflict(
            "OPTION_ERROR_INVALID",
            "最终结果存在必需内容或标注缺口",
            issues=[
                {"code": r["issue_code"], "reference": r.get("src_id")}
                for r in issues[:30]
            ],
        )
    receipts = payload.get("generation_receipts", [])
    questions = {q["_src_id"]: q for q in payload["questions"]}
    if {r["question_src_id"] for r in receipts} != set(questions) or len(
        receipts
    ) != len(questions):
        raise w.conflict(
            "REVIEW_INCOMPLETE", "每题须有实际成功生成记录，空错因也不例外"
        )
    source, _ = o.stage_payload(db, revision, "source", settings)
    for section in (
        "questions",
        "passages",
        "transcript_segments",
        "presentations",
        "audio",
    ):
        if source[section] != payload[section]:
            raise w.conflict("ARTIFACT_CHANGED", "结果内容不匹配冻结来源")
    rebuilt = copy.deepcopy(source)
    for receipt in receipts:
        question = questions[receipt["question_src_id"]]
        raw, artifact = o.artifact_payload(db, receipt["artifact_id"], settings)
        generation_task = tasks.get_task(db, artifact.task_id)
        call = db.get(p.LlmAttempt, receipt["attempt_id"])
        if (
            not call
            or call.task_id != generation_task.id
            or call.status != "succeeded"
            or not ancestor_revision(db, revision, generation_task)
            or str(generation_task.id) != receipt["task_id"]
            or raw["rules_manifest"] != revision.rules_manifest
            or artifact.artifact_hash != receipt["artifact_hash"]
            or raw["call"]["attempt_id"] != call.id
            or receipt["response_hash"] != fingerprint(call.response_payload)
            or receipt["candidate_hash"]
            != fingerprint(normalize_candidate(raw["candidate"]))
            or receipt["question_input_hash"] != question_input_hash(payload, question)
            or receipt.get("generation_input_hash")
            != fingerprint(generation_input(payload, question, generation_task.request))
            or raw["call"]["request_hash"] != fingerprint(call.request_payload)
            or json.loads(call.request_payload["messages"][1]["content"])
            != generation_input(payload, question, generation_task.request)
            or not call.request_payload["messages"][0]["content"].startswith(
                SYSTEM_PROMPT_V2
            )
            or json.loads(call.response_payload["choices"][0]["message"]["content"])
            != raw["candidate"]
        ):
            raise w.conflict(
                "ARTIFACT_CHANGED", "生成receipt、模型响应或题目依赖不匹配"
            )
        check_option_candidate(payload, question, raw["candidate"])
        expected_state = (
            "generated" if raw["candidate"]["candidate_errors"] else "generated_empty"
        )
        if receipt["state"] != expected_state:
            raise w.conflict("OPTION_ERROR_INVALID", "错因生成状态与原始响应不匹配")
        merge_option_candidate(rebuilt, question, raw["candidate"])
    for section in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        if sorted(rebuilt[section], key=fingerprint) != sorted(
            payload[section], key=fingerprint
        ):
            raise w.conflict("ANNOTATION_CONFLICT", "标注关系与实际候选响应不匹配")


def session_context(db, workflow_id, session_id, payload=None, *, lock=False):
    if payload is None:
        workflow = w.get_workflow(db, workflow_id)
        revision = db.get(m.ProcessingWorkflowRevision, workflow.current_revision_id)
    else:
        workflow, revision = w.locked_current(db, workflow_id, payload)
    stmt = select(m.ProcessingReviewSession).where(
        m.ProcessingReviewSession.id == session_id,
        m.ProcessingReviewSession.revision_id == revision.id,
    )
    session = db.scalar(stmt.with_for_update() if lock else stmt)
    if not session:
        raise AppError(404, "当前修订没有该审核会话")
    task = tasks.get_task(db, revision.final_task_id)
    draft = tasks.get_draft(db, task)
    if (
        not draft
        or draft.result_hash != revision.final_result_hash
        or result_hash(draft.payload) != session.result_hash
    ):
        raise w.conflict("ARTIFACT_CHANGED", "审核会话不匹配冻结最终结果")
    if payload and (
        payload.expected_result_hash != session.result_hash
        or payload.expected_session_version != session.row_version
    ):
        raise w.conflict(
            "VERSION_CONFLICT",
            "审核进度已更新，请保留意见并刷新",
            session_version=session.row_version,
        )
    return workflow, revision, session, task, draft.payload


def review_requirements(payload, question_id):
    skills = [
        r
        for r in payload["skill_question_relations"]
        if r.get("question_src_id") == question_id
    ]
    skill_ids = {r["_src_id"] for r in skills}
    skill_ids |= {
        r["_src_id"]
        for r in payload["skill_question_relations"]
        if r.get("owner_relation_src_id") in skill_ids
    }
    errors = [
        r
        for r in payload["error_question_relations"]
        if r.get("question_src_id") == question_id
    ]
    error_ids = {r["_src_id"] for r in errors}
    error_ids |= {
        r["_src_id"]
        for r in payload["error_question_relations"]
        if r.get("owner_relation_src_id") in error_ids
    }
    return {
        "primary_skills": skill_ids,
        "answer_evidence": {
            r["_src_id"]
            for r in payload["other_relations"]
            if r.get("question_src_id") == question_id
            and r["relation_kind"] == "ANSWER_EVIDENCE"
        },
        "error_causes": error_ids,
    }


def item_approved(item, required):
    return (
        item.get("content") == "approved"
        and not item.get("issues")
        and all(
            {r["reference"] for r in item.get(field, [])} == refs
            and len(item.get(field, [])) == len(refs)
            and all(r["decision"] == "approved" for r in item.get(field, []))
            for field, refs in required.items()
        )
        and (
            bool(required["error_causes"]) or item.get("empty_errors_confirmed") is True
        )
    )


def save(db, workflow_id, session_id, payload, user, key):
    old, digest, body = w.begin_command(
        db, user.id, "review_save", key, f"{workflow_id}/{session_id}", payload
    )
    if old:
        return old
    workflow, revision, session, _, content = session_context(
        db, workflow_id, session_id, payload, lock=True
    )
    if session.state == "approved":
        raise w.conflict("VERSION_CONFLICT", "已提交审核不可覆盖，请创建新修订")
    questions = {q["_src_id"] for q in content["questions"]}
    if len({r.question_src_id for r in payload.items}) != len(payload.items):
        raise AppError(422, "同一批保存不能重复题目")
    for item in payload.items:
        if item.question_src_id not in questions:
            raise AppError(422, "审核题目不属于当前结果")
        if (
            item.content == "changes_required" or item.issues
        ) and not item.note.strip():
            raise AppError(422, "退回须填写具体原因及问题定位")
        row = db.get(m.ProcessingReviewItem, (session.id, item.question_src_id))
        if not row:
            row = m.ProcessingReviewItem(
                session_id=session.id, question_src_id=item.question_src_id
            )
            db.add(row)
        row.decisions = item.model_dump()
        row.note, row.issues = item.note, item.issues
        row.operator_user_id, row.updated_at = user.id, func.now()
    session.row_version += 1
    session.state = "draft"
    return w.finish_command(
        db,
        workflow,
        revision,
        user.id,
        "review_save",
        key,
        digest,
        body,
        {"session_id": str(session.id), "session_version": session.row_version},
    )


def submit(db, workflow_id, session_id, payload, user, key, settings):
    old, digest, body = w.begin_command(
        db, user.id, "review_submit", key, f"{workflow_id}/{session_id}", payload
    )
    if old:
        return old
    workflow, revision, session, task, content = session_context(
        db, workflow_id, session_id, payload, lock=True
    )
    if session.state == "approved" or not payload.audio_confirmed:
        raise w.conflict("REVIEW_INCOMPLETE", "须明确确认本最终版本的原音核听")
    validate_final(db, content, task.request, revision, settings)
    rows = db.scalars(
        select(m.ProcessingReviewItem).where(
            m.ProcessingReviewItem.session_id == session.id
        )
    ).all()
    questions = {q["_src_id"] for q in content["questions"]}
    if {r.question_src_id for r in rows} != questions or any(
        not item_approved(r.decisions, review_requirements(content, r.question_src_id))
        for r in rows
    ):
        raise w.conflict(
            "REVIEW_INCOMPLETE", "须逐题完整确认内容、技能、答案证据及每条错因证据"
        )
    references = {
        row.question_src_id: row.note or payload.approval_reference for row in rows
    }
    sections = (
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    )
    db.info["workflow_review_session"] = session.id
    tasks.record_review(
        db,
        task.id,
        ReviewRequest(
            result_hash=session.result_hash,
            scope="content",
            decision="approved",
            items=[
                {
                    "entity_type": "questions",
                    "src_id": q,
                    "verdict": "PASS",
                    "reference": references[q],
                }
                for q in questions
            ],
            evidence_refs=[str(session.id)],
            note=payload.approval_reference,
        ),
        user,
    )
    tasks.record_review(
        db,
        task.id,
        ReviewRequest(
            result_hash=session.result_hash,
            scope="annotations",
            decision="approved",
            items=[
                {
                    "entity_type": section,
                    "src_id": row["_src_id"],
                    "verdict": "PASS",
                    "reference": str(session.id),
                }
                for section in sections
                for row in content[section]
            ],
            evidence_refs=[str(session.id)],
            note=payload.approval_reference,
        ),
        user,
    )
    tasks.record_review(
        db,
        task.id,
        ReviewRequest(
            result_hash=session.result_hash,
            scope="audio",
            decision="approved",
            review_basis="user_confirmation",
            approval_reference=payload.approval_reference,
            items=[
                {
                    "entity_type": "audio",
                    "src_id": "original",
                    "verdict": "PASS",
                    "file_hash": content["audio"]["file_hash"],
                    "reference": payload.approval_reference,
                }
            ],
            evidence_refs=[str(session.id)],
            note=payload.approval_reference,
        ),
        user,
    )
    session.state, session.submitted_by, session.submitted_at = (
        "approved",
        user.id,
        tasks.utcnow(),
    )
    session.row_version += 1
    workflow.content_review_state = workflow.error_review_state = "approved"
    workflow.row_version += 1
    return w.finish_command(
        db,
        workflow,
        revision,
        user.id,
        "review_submit",
        key,
        digest,
        body,
        {
            "session_id": str(session.id),
            "session_version": session.row_version,
            "row_version": workflow.row_version,
        },
    )
