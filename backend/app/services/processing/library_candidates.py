"""Immutable model outputs, dependency-pinned previews and selective adoption."""

import json
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select

from app.db import models_library as l
from app.db import models_processing as p
from app.db import models_processing_workflows as m
from app.module3.annotation_identity import question_input_hash
from app.module3.contracts import fingerprint
from app.module3.distractor_annotations import (
    check_option_candidate,
    merge_option_candidate,
    normalize_candidate,
)
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import orchestration as o
from app.services.processing import workflows as w
from app.services.processing.library_annotations import replace_question_annotations


def checkpoint(db, task, revision, question, payload, raw, receipt):
    digest = fingerprint(raw)
    existing = db.scalar(
        select(l.AnnotationCandidate).where(
            l.AnnotationCandidate.revision_id == revision.id,
            l.AnnotationCandidate.question_src_id == question["_src_id"],
            l.AnnotationCandidate.candidate_hash == digest,
        )
    )
    if existing:
        return existing
    row = l.AnnotationCandidate(
        id=uuid4(),
        workflow_id=revision.workflow_id,
        revision_id=revision.id,
        question_src_id=question["_src_id"],
        method_hash=task.method_hash,
        dependency_hash=question_input_hash(payload, question),
        candidate_hash=digest,
        payload=raw,
        receipt=receipt,
        validation={"state": "validated"},
    )
    db.add(row)
    db.flush()
    return row


def candidates(db, workflow_id):
    workflow = w.get_workflow(db, workflow_id)
    rows = db.scalars(
        select(l.AnnotationCandidate)
        .where(l.AnnotationCandidate.workflow_id == workflow.id)
        .order_by(
            l.AnnotationCandidate.created_at.desc(), l.AnnotationCandidate.id.desc()
        )
        .limit(100)
    ).all()
    revisions = {
        row.id: row
        for row in db.scalars(
            select(m.ProcessingWorkflowRevision).where(
                m.ProcessingWorkflowRevision.id.in_({r.revision_id for r in rows})
            )
        ).all()
    }
    attempts = {
        row.id: row
        for row in db.scalars(
            select(p.LlmAttempt).where(
                p.LlmAttempt.id.in_(
                    {
                        r.receipt["attempt_id"]
                        for r in rows
                        if r.receipt.get("attempt_id")
                    }
                )
            )
        ).all()
    }

    def identity(row):
        revision = revisions.get(row.revision_id)
        method = (revision.origin_manifest or {}).get("provider_method", {})
        attempt = attempts.get(row.receipt.get("attempt_id"))
        frozen = (attempt.provider_manifest if attempt else None) or method
        return {
            "evaluation_only": bool(revision.origin_manifest.get("evaluation_only")),
            "provider": attempt.provider
            if attempt
            else frozen.get("provider", "deepseek"),
            "requested_model": frozen.get("requested_model", "deepseek-flash"),
            "response_model": attempt.response_model if attempt else None,
            "region": frozen.get("region", "official"),
        }

    return {
        "items": [
            {
                "id": str(r.id),
                "revision_id": str(r.revision_id),
                "question_src_id": r.question_src_id,
                "method_hash": r.method_hash,
                "dependency_hash": r.dependency_hash,
                "candidate_hash": r.candidate_hash,
                "payload": r.payload,
                "validation": r.validation,
                "created_at": r.created_at,
                **identity(r),
            }
            for r in rows
        ]
    }


def verify_receipt(db, row, payload, question, settings):
    receipt = row.receipt
    original, artifact = o.artifact_payload(db, receipt["artifact_id"], settings)
    attempt = db.get(p.LlmAttempt, receipt["attempt_id"])
    from app.module3.distractor_annotations import SYSTEM_PROMPT_V7
    from app.module3.workflow_worker import generation_input
    from app.services.processing.candidate_recovery import response_task_matches

    generation_task = db.get(p.ProcessingTask, artifact.task_id)
    revision = db.get(m.ProcessingWorkflowRevision, row.revision_id)
    if revision and revision.origin_manifest.get("evaluation_only"):
        raise w.conflict(
            "EVALUATION_CANDIDATE_READ_ONLY", "评测候选仅用于对比报告，不能直接采纳"
        )
    if (
        not generation_task
        or generation_task.workflow_id != row.workflow_id
        or generation_task.revision_id != row.revision_id
        or generation_task.method_hash != row.method_hash
        or not attempt
        or not response_task_matches(
            db, artifact, attempt, original, revision, settings
        )
        or receipt.get("question_input_hash") != row.dependency_hash
        or original.get("question_input_hash") != row.dependency_hash
        or original["call"]["attempt_id"] != attempt.id
        or original["call"]["request_hash"] != fingerprint(attempt.request_payload)
        or json.loads(attempt.request_payload["messages"][1]["content"])
        != generation_input(payload, question, generation_task.request)
        or not attempt.request_payload["messages"][0]["content"].startswith(
            SYSTEM_PROMPT_V7
        )
    ):
        raise w.conflict(
            "CANDIDATE_PROVENANCE_INVALID", "候选原始请求、执行或来源不匹配"
        )
    method = generation_task.method.get("provider_manifest")
    if method and any(
        attempt.request_payload.get(k) != v for k, v in method["parameters"].items()
    ):
        raise w.conflict("CANDIDATE_PROVENANCE_INVALID", "模型实际请求与冻结方法不一致")
    if (
        not attempt
        or attempt.status != "succeeded"
        or row.payload != original.get("candidate")
        or fingerprint(row.payload) != row.candidate_hash
        or receipt["candidate_hash"] != fingerprint(normalize_candidate(row.payload))
        or artifact.artifact_hash != receipt["artifact_hash"]
        or attempt.response_payload.get("choices", [{}])[0].get("finish_reason")
        != "stop"
        or receipt["response_hash"] != fingerprint(attempt.response_payload)
        or json.loads(attempt.response_payload["choices"][0]["message"]["content"])
        != row.payload
        or row.dependency_hash != question_input_hash(payload, question)
    ):
        raise w.conflict(
            "CANDIDATE_DEPENDENCY_CONFLICT", "候选来源或题目依赖变化，请重新生成"
        )
    check_option_candidate(payload, question, row.payload)


def selected_rows(snapshot, section, qid, scopes):
    if section == "skill_question_relations":
        if "skills" not in scopes:
            return []
        owners = {
            r["_src_id"] for r in snapshot[section] if r.get("question_src_id") == qid
        }
        return [
            r
            for r in snapshot[section]
            if r.get("question_src_id") == qid
            or r.get("owner_relation_src_id") in owners
        ]
    if section == "other_relations":
        return (
            [
                r
                for r in snapshot[section]
                if r.get("question_src_id") == qid
                and r.get("relation_kind") == "ANSWER_EVIDENCE"
            ]
            if "answer_evidence" in scopes
            else []
        )
    letters = {
        scope.split(":", 1)[1] for scope in scopes if scope.startswith("errors:")
    }
    owners = {
        r["_src_id"]
        for r in snapshot["error_question_relations"]
        if r.get("question_src_id") == qid and r.get("option_letter") in letters
    }
    return [
        r
        for r in snapshot[section]
        if (r.get("question_src_id") == qid and r.get("option_letter") in letters)
        or r.get("owner_relation_src_id") in owners
    ]


def adopt(db, workflow_id, payload, user_id, settings, key=None):
    if key:
        old, digest, body = w.begin_command(
            db, user_id, "library_adopt", key, workflow_id, payload
        )
        if old:
            return old
    paper, workflow, head, current, before = e.context(
        db, workflow_id, lock=key is not None
    )
    e.preconditions(head, before, payload)
    allowed = {
        "skills",
        "answer_evidence",
        "errors:A",
        "errors:B",
        "errors:C",
        "errors:D",
    }
    if set(payload.scopes) - allowed or len(set(payload.candidate_ids)) != len(
        payload.candidate_ids
    ):
        raise c.invalid("候选或采纳范围无效/重复")
    after = deepcopy(before)
    chosen = set()
    for candidate_id in payload.candidate_ids:
        row = db.get(l.AnnotationCandidate, candidate_id)
        if not row or row.workflow_id != workflow.id or row.question_src_id in chosen:
            raise c.invalid("候选不属于当前试卷或同题重复采纳")
        q = next(
            (q for q in before["questions"] if q["_src_id"] == row.question_src_id),
            None,
        )
        if not q:
            raise w.conflict("CANDIDATE_DEPENDENCY_CONFLICT", "候选题目已删除")
        full = c.build_payload(
            replace_question_annotations(before, q["_src_id"]), head.baseline
        )
        verify_receipt(db, row, full, q, settings)
        merge_option_candidate(full, q, row.payload)
        for section in (
            "skill_question_relations",
            "error_question_relations",
            "other_relations",
            "distractor_assessments",
        ):
            removed = {
                r["_src_id"]
                for r in selected_rows(after, section, q["_src_id"], payload.scopes)
            }
            after[section] = [
                r for r in after[section] if r["_src_id"] not in removed
            ] + selected_rows(full, section, q["_src_id"], payload.scopes)
        existing = {r["_src_id"]: r for r in after["evidences"]}
        required = {
            r["evidence_src_id"]
            for section in (
                "skill_question_relations",
                "error_question_relations",
                "other_relations",
            )
            for r in after[section]
            if r.get("evidence_src_id")
        }
        required |= {
            r["evidence_src_id"]
            for a in after["distractor_assessments"]
            for r in a.get("comparison_evidence_refs", [])
        }
        for evidence in full["evidences"]:
            if evidence["_src_id"] in required:
                existing[evidence["_src_id"]] = evidence
        after["evidences"] = list(existing.values())
        chosen.add(q["_src_id"])
    after = c.canonical_snapshot(after)
    issues = c.validate_snapshot(
        after, head.baseline, e.request_for(paper, head.baseline)
    )
    changes = c.differences(before, after)
    effect = c.impact(changes, before, after)
    if not key:
        return {
            "changes": changes,
            "impact": effect,
            "issues": issues,
            "scopes": payload.scopes,
            "row_version": head.row_version,
            "content_hash": fingerprint(before),
        }
    e.available(db, workflow, paper)
    version, _, effect = e.append_save(
        db,
        paper,
        workflow,
        head,
        current,
        before,
        after,
        user_id,
        payload.reason,
        provenance={
            "type": "AI_ADOPTION",
            "candidate_ids": [str(i) for i in payload.candidate_ids],
            "scopes": payload.scopes,
        },
    )
    return w.finish_command(
        db,
        workflow,
        db.get(m.ProcessingWorkflowRevision, head.revision_id),
        user_id,
        "library_adopt",
        key,
        digest,
        body,
        {
            "save_version_id": str(version.id) if version else None,
            "row_version": head.row_version,
            "impact": effect,
            "issues": issues,
        },
    )
