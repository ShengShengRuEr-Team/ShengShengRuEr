"""Manual labels are audited edits, never model responses or receipts."""

from copy import deepcopy

from pydantic import ValidationError

from app.db import models_processing_workflows as m
from app.module3.distractor_annotations import (
    check_option_candidate,
    merge_option_candidate,
)
from app.services.processing import library_content as c
from app.services.processing import library_editing as e
from app.services.processing import workflows as w


def replace_question_annotations(snapshot, qid):
    result = deepcopy(snapshot)
    owners = {
        r["_src_id"]
        for name in ("skill_question_relations", "error_question_relations")
        for r in result[name]
        if r.get("question_src_id") == qid
    }
    for section in (
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
        "distractor_assessments",
    ):
        result[section] = [
            r
            for r in result[section]
            if r.get("question_src_id") != qid
            and r.get("owner_relation_src_id") not in owners
        ]
    return result


def manual_save(db, workflow_id, payload, user_id, key):
    old, digest, body = w.begin_command(
        db, user_id, "library_manual_annotation", key, workflow_id, payload
    )
    if old:
        return old
    paper, workflow, head, current, before = e.context(db, workflow_id, lock=True)
    e.available(db, workflow, paper)
    e.preconditions(head, before, payload)
    qid = payload.candidate.get("question_src_id")
    question = next((q for q in before["questions"] if q["_src_id"] == qid), None)
    if not question:
        raise c.invalid("标注题目不属于当前试卷")
    merged = c.build_payload(replace_question_annotations(before, qid), head.baseline)
    try:
        check_option_candidate(merged, question, payload.candidate)
    except ValidationError:
        raise c.invalid("人工标注结构不完整或含非法字段") from None
    merge_option_candidate(merged, question, payload.candidate)
    evidences = {}
    for row in merged["evidences"]:
        previous = evidences.get(row["_src_id"])
        if previous and previous != row:
            raise c.invalid("共享证据身份冲突")
        evidences[row["_src_id"]] = row
    merged["evidences"] = list(evidences.values())
    after = c.canonical_snapshot(c.projection(merged))
    issues = c.validate_snapshot(
        after, head.baseline, e.request_for(paper, head.baseline)
    )
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
            "type": "MANUAL",
            "question_src_id": qid,
            "annotation_input": payload.candidate,
        },
    )
    return w.finish_command(
        db,
        workflow,
        db.get(m.ProcessingWorkflowRevision, head.revision_id),
        user_id,
        "library_manual_annotation",
        key,
        digest,
        body,
        {
            "save_version_id": str(version.id) if version else None,
            "row_version": head.row_version,
            "issues": issues,
            "impact": effect,
        },
    )
