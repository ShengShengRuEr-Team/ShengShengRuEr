"""Unresolved sample recovery uses explicit, versioned commands, not fake empties."""

import json
from uuid import UUID

from tests.module3.test_workflow_pipeline import BASE
from tests.module3.test_workflow_pipeline import pipeline as pipeline


def test_bounded_failure_restarts_from_source_without_empty_sample(
    client, pipeline, monkeypatch
):
    from app.db import models_processing as p
    from app.db.base import SessionLocal
    from app.module3 import llm

    c, original = pipeline, llm.request_json
    c["execute"](c["post"]("start", {"reason": "Synthetic bounded failure"}))
    c["approve"]("align")
    assert c["detail"]()["reprocess_result_hash"] is None
    detail = c["detail"]()
    stage = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/stages/source",
        headers=c["headers"],
    ).json()["data"]
    response = c["post"](
        "stage-approvals",
        {
            "stage": "source",
            "artifact_hash": stage["artifact_hash"],
            "expected_stage_dependency_hash": stage["dependency_hash"],
            "decision": "approved",
            "items": [
                {
                    "reference": row["_src_id"],
                    "decision": "approved",
                    "reason": "Synthetic source check",
                }
                for row in stage["items"]
            ],
        },
    )
    assert response.status_code == 200, response.text

    def invalid(*args, **kwargs):
        raw, call = original(*args, **kwargs)
        raw["answer_evidence"][0]["quote"] = "Not in the source."
        return raw, call

    monkeypatch.setattr(llm, "request_json", invalid)
    c["execute"](
        c["post"](
            "continue",
            {
                "stage": "source",
                "expected_stage_dependency_hash": stage["dependency_hash"],
            },
        ),
        expected_code=2,
    )
    failed = c["detail"]()
    assert failed["processing_state"] == "failed"
    assert failed["result_hash"] is None and failed["sample_result_hash"] is None
    assert failed["reprocess_result_hash"] == stage["result_hash"]
    body = {
        "expected_result_hash": failed["reprocess_result_hash"],
        "question_src_ids": ["q:1"],
        "feedback": "Synthetic explicit restart after bounded quote failure.",
    }
    preview = c["post"]("reprocess-preview", body)
    assert preview.status_code == 200, preview.text
    plan = preview.json()["data"]
    assert not plan["sample_valid"] and not plan["reusable_question_ids"]
    monkeypatch.setattr(llm, "request_json", original)
    c["execute"](
        c["post"]("reprocess", {**body, "expected_plan_hash": plan["plan_hash"]})
    )
    after = c["detail"]()
    assert after["processing_state"] == "awaiting_sample"
    assert after["revision_id"] != failed["revision_id"]
    assert after["review_session_id"] is None
    with SessionLocal() as db:
        assert db.get(p.ProcessingTask, UUID(failed["task_id"])).state == "failed"


def test_unresolved_sample_blocks_approval_and_can_be_reprocessed(
    client, pipeline, monkeypatch
):
    from app.db import models_processing as p
    from app.db.base import SessionLocal
    from app.module3 import llm

    c = pipeline
    original = llm.request_json

    def unresolved(*args, **kwargs):
        raw, call = original(*args, **kwargs)
        raw["distractor_assessments"][0].update(
            status="INSUFFICIENT_EVIDENCE",
            unresolved_points=["Synthetic missing antecedent"],
        )
        with SessionLocal() as db:
            attempt = db.get(p.LlmAttempt, call["attempt_id"])
            response = dict(attempt.response_payload)
            response["choices"] = [
                {"finish_reason": "stop", "message": {"content": json.dumps(raw)}}
            ]
            attempt.response_payload = response
            db.commit()
        return raw, call

    monkeypatch.setattr(llm, "request_json", unresolved)
    c["execute"](c["post"]("start", {"reason": "Synthetic unresolved sample"}))
    c["approve"]("align")
    c["approve"]("source")
    detail = c["detail"]()
    assert detail["processing_state"] == "awaiting_sample"
    assert detail["error_generation_summary"]["resolved"] == 2
    assert detail["sample_result_hash"] is not None
    stage = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/stages/sample",
        headers=c["headers"],
    ).json()["data"]
    rejected = c["post"](
        "stage-approvals",
        {
            "stage": "sample",
            "artifact_hash": stage["artifact_hash"],
            "expected_stage_dependency_hash": stage["dependency_hash"],
            "decision": "approved",
            "items": [
                {
                    "reference": r["_src_id"],
                    "decision": "approved",
                    "reason": "Synthetic review",
                }
                for r in stage["items"]
            ],
        },
    )
    assert rejected.status_code in {409, 422}, rejected.text
    returned = c["post"](
        "stage-approvals",
        {
            "stage": "sample",
            "artifact_hash": stage["artifact_hash"],
            "expected_stage_dependency_hash": stage["dependency_hash"],
            "decision": "changes_required",
            "reviewer_kind": "codex",
            "items": [
                {
                    "reference": r["_src_id"],
                    "decision": "changes_required",
                    "reason": "Synthetic unresolved source requires reprocessing",
                }
                for r in stage["items"]
            ],
        },
    )
    assert returned.status_code == 200, returned.text
    body = {
        "expected_result_hash": detail["sample_result_hash"],
        "question_src_ids": ["q:1"],
        "feedback": (
            "Synthetic review: recheck the antecedent; keep unresolved if still absent."
        ),
    }
    preview = c["post"]("reprocess-preview", body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["sample_valid"] is False
    monkeypatch.setattr(llm, "request_json", original)
    response = c["post"](
        "reprocess", {**body, "expected_plan_hash": preview.json()["data"]["plan_hash"]}
    )
    c["execute"](response)
    after = c["detail"]()
    assert after["revision_id"] != detail["revision_id"]
    assert after["error_generation_summary"]["resolved"] == 3
    assert after["review_session_id"] is None
    # The original incomplete response remains stored under its original task.
    with SessionLocal() as db:
        assert db.get(p.ProcessingTask, UUID(detail["task_id"])) is not None
