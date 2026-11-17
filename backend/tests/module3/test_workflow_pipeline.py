"""Synthetic workflow transactions; these do not certify real-material semantics."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

BASE = "/api/v1/admin/processing-workflows"


@pytest.fixture
def pipeline(client, context, monkeypatch):
    from app.db import models_processing as p
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.module3 import llm, worker
    from app.module3.contracts import fingerprint
    from app.services.processing import orchestration, tasks, uploads
    from app.services.processing.validation import load_dictionary

    async def synthetic_probe(*args):
        return None

    monkeypatch.setattr(uploads, "validate_file", synthetic_probe)
    monkeypatch.setattr(orchestration, "environment_ready", lambda _: True)
    headers = context["headers"]
    metadata = {
        "exam_level": "CET4",
        "exam_year": 2100 + uuid4().int % 99,
        "exam_month": 1 + uuid4().int % 12,
        "paper_set": 1 + uuid4().int % 99,
        "document_mode": "text",
        "listening_pages": {"paper": [1], "answer": [1]},
    }
    created = client.post(
        BASE, json=metadata, headers={**headers, "Idempotency-Key": str(uuid4())}
    )
    assert created.status_code == 201, created.text
    workflow_id = created.json()["data"]["workflow_id"]

    def detail():
        response = client.get(f"{BASE}/{workflow_id}", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def preconditions():
        value = detail()
        return {
            "expected_workflow_version": value["row_version"],
            "expected_revision_id": value["revision_id"],
        }

    def post(path, payload=None, key=None):
        return client.post(
            f"{BASE}/{workflow_id}/{path}",
            json={**preconditions(), **(payload or {})},
            headers={**headers, "Idempotency-Key": key or str(uuid4())},
        )

    material_ids = {}
    for kind, path in (
        ("paper", context["paper"]),
        ("answer", context["paper"]),
        ("audio", context["audio"]),
    ):
        content = path.read_bytes()
        response = post(
            "material-uploads",
            {
                "kind": kind,
                "filename": f"{kind}{path.suffix}",
                "declared_size": len(content),
                "expected_upload_version": 0,
            },
        )
        assert response.status_code == 201, response.text
        upload = response.json()["data"]["result"]
        response = client.put(
            f"{BASE}/{workflow_id}/materials/{kind}",
            content=content,
            headers={
                **headers,
                "X-Upload-Id": upload["upload_id"],
                "X-Expected-Revision-Id": detail()["revision_id"],
                "X-Expected-Upload-Version": str(upload["upload_version"]),
            },
        )
        assert response.status_code == 200, response.text
        material_ids[kind] = response.json()["data"]["material_id"]

    source = context["clone"]()
    for section in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        source[section] = []
    source["questions"][0]["source_refs"] = [
        {"material_id": material_ids["answer"], "locator": {"page": 1}}
    ]
    source["audio"]["audio_code"] = "SYN_" + uuid4().hex
    eligible = [
        r
        for table in load_dictionary()["tables"]
        if table["name"] == "skill"
        for r in table["rows"]
        if r["skill_level"] == 3
        and r["status"] == "启用"
        and r.get("usage_scope") == "题目标注"
    ]

    def synthetic_process(task_id, token, settings):
        with SessionLocal() as db:
            task = tasks.fenced_task(db, task_id, token)
            body = copy.deepcopy(source)
            body["exam_paper"] = task.request["exam_paper"]
            if task.request["stop_after"] == "align":
                paper = db.get(p.MaterialSource, material_ids["paper"])
                reference = {
                    "segments": [],
                    "trusted_question_structure": {
                        "source": "original_paper_question_headings",
                        "question_count": len(source["questions"]),
                        "groups": [
                            {
                                "section": "synthetic",
                                "start": 1,
                                "end": len(source["questions"]),
                                "source_sha256": paper.sha256,
                                "source_storage_key": paper.storage_key,
                                "source_page": 1,
                            }
                        ],
                    },
                }
                for stage, value in (
                    ("extract", {"pages": []}),
                    ("normalize", {"duration_ms": 3000}),
                    ("reference", reference),
                    ("align", {"segments": body["transcript_segments"]}),
                ):
                    tasks.save_artifact(db, task_id, token, stage, value, settings)
                task.stage = "align"
            else:
                tasks.store_draft(db, task, body, view="auto_draft")
                tasks.store_draft(db, task, body, view="final")
                task.stage = "assemble"
            task.state, task.lease_token, task.expires_at = (
                "awaiting_confirmation",
                None,
                None,
            )
            db.commit()
        return 0

    monkeypatch.setattr(worker, "process", synthetic_process)

    synthetic_errors = []

    def synthetic_request(task_id, run_key, phase, system, data, settings, **kwargs):
        candidate = {
            "question_src_id": data["question"]["_src_id"],
            "skills": [
                {
                    "skill_code": eligible[0]["skill_code"],
                    "role": "PRIMARY",
                    "rationale": "Synthetic evidence test",
                    "evidence_segment_src_ids": ["s:1"],
                    "quote": "The answer is Alpha.",
                }
            ],
            "answer_evidence": [
                {
                    "evidence_segment_src_ids": ["s:1"],
                    "quote": "The answer is Alpha.",
                    "support_note": "Synthetic source states Alpha, matching option A.",
                }
            ],
            "candidate_errors": copy.deepcopy(synthetic_errors),
            "language_items": [],
            "genre_candidate": None,
        }
        response = {
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(candidate)}}
            ],
            "model": "synthetic-test-only",
            "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        }
        request = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ]
        }
        with SessionLocal() as db:
            tasks.fenced_task(db, task_id, kwargs["execution_token"])
            attempt = p.LlmAttempt(
                task_id=task_id,
                run_key=run_key,
                phase=phase,
                request_hash=fingerprint(request),
                request_payload=request,
                response_payload=response,
                response_model="synthetic-test-only",
                reserved_usd=Decimal("0.01"),
                charged_usd=Decimal("0.001"),
                billing_status="estimated",
                status="succeeded",
            )
            db.add(attempt)
            db.commit()
            return candidate, {
                "attempt_id": attempt.id,
                "request_hash": fingerprint(request),
            }

    monkeypatch.setattr(llm, "request_json", synthetic_request)

    def execute(response, expected_code=0):
        from app.module3.workflow_worker import execute as execute_command

        assert response.status_code == 202, response.text
        operation = response.json()["data"]
        with SessionLocal() as db:
            command = db.get(
                m.ProcessingWorkflowCommand, UUID(operation["operation_id"])
            )
            token = uuid4()
            command.state, command.execution_token = "running", token
            command.lease_expires_at = tasks.utcnow() + timedelta(seconds=120)
            workflow = db.get(m.ProcessingWorkflow, UUID(workflow_id))
            workflow.processing_state = "running"
            if command.result.get("task_id"):
                task = tasks.get_task(db, UUID(command.result["task_id"]))
                task.state, task.lease_token, task.expires_at = (
                    "running",
                    token,
                    command.lease_expires_at,
                )
                task.request = {
                    **task.request,
                    "workflow_stage": command.result["stage"],
                }
            db.commit()
        code = execute_command(
            UUID(operation["operation_id"]), token, context["settings"]
        )
        assert code == expected_code, detail()
        return operation

    def approve(stage):
        value = detail()
        response = client.get(
            f"{BASE}/{workflow_id}/revisions/{value['revision_id']}/stages/{stage}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        stage_data = response.json()["data"]
        refs = [
            row["_src_id"]
            for row in stage_data["items"]
            if stage != "align" or row["segment_type"] == "body"
        ]
        if stage == "sample":
            refs = refs[:5]
        response = post(
            "stage-approvals",
            {
                "stage": stage,
                "artifact_hash": stage_data["artifact_hash"],
                "expected_stage_dependency_hash": stage_data["dependency_hash"],
                "decision": "approved",
                "items": [
                    {
                        "reference": ref,
                        "decision": "approved",
                        "reason": "Synthetic check only",
                    }
                    for ref in refs
                ],
            },
        )
        assert response.status_code == 200, response.text
        execute(
            post(
                "continue",
                {
                    "stage": stage,
                    "expected_stage_dependency_hash": stage_data["dependency_hash"],
                },
            )
        )

    return {
        "detail": detail,
        "pre": preconditions,
        "post": post,
        "execute": execute,
        "approve": approve,
        "headers": headers,
        "id": workflow_id,
        "context": context,
        "source": source,
        "errors": synthetic_errors,
    }


def complete_to_review(c):
    c["execute"](c["post"]("start", {"reason": "Synthetic test only"}))
    for stage in ("align", "source", "sample"):
        c["approve"](stage)


def synthetic_review_publish(client, c, publish=True):
    detail = c["detail"]()
    session = detail["review_session_id"]
    questions = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/questions",
        params={"limit": 100},
        headers=c["headers"],
    ).json()["data"]["items"]
    items = [
        {
            "question_src_id": q["question_src_id"],
            "content": "approved",
            "empty_errors_confirmed": True,
            "note": "Synthetic database verification only",
            "issues": [],
            **{
                field: [{"reference": ref, "decision": "approved"} for ref in refs]
                for field, refs in q["review_requirements"].items()
            },
        }
        for q in questions
    ]
    response = client.patch(
        f"{BASE}/{c['id']}/review-sessions/{session}/items",
        headers={**c["headers"], "Idempotency-Key": str(uuid4())},
        json={
            **c["pre"](),
            "expected_result_hash": detail["result_hash"],
            "expected_session_version": 1,
            "items": items,
        },
    )
    assert response.status_code == 200, response.text
    response = c["post"](
        f"review-sessions/{session}/submit",
        {
            "expected_result_hash": detail["result_hash"],
            "expected_session_version": 2,
            "audio_confirmed": True,
            "approval_reference": "Synthetic technical assertions only",
        },
    )
    assert response.status_code == 200, response.text
    response = c["post"](
        "publish",
        {
            "expected_result_hash": detail["result_hash"],
            "review_session_id": session,
            "expected_current_batch_id": detail["current_batch_id"],
        },
    )
    if publish:
        c["execute"](response)
    return response


def test_pending_publication_failure_keeps_old_batch_and_retry_reuses_pending(
    client, pipeline, monkeypatch
):
    from app.module3.contracts import ProcessingError
    from app.services.processing import publication

    c = pipeline
    complete_to_review(c)
    synthetic_review_publish(client, c)
    original = c["detail"]()
    old = original["current_batch_id"]
    pid = original["exam_paper_id"]
    opened = client.post(
        f"/api/v1/admin/listening-papers/{pid}/visibility",
        headers=c["headers"],
        json={
            "action": "confirm",
            "expected_batch_id": old,
            "reason": "Synthetic visibility preservation test",
        },
    )
    assert opened.status_code == 200, opened.text
    body = {
        "expected_result_hash": original["result_hash"],
        "question_src_ids": ["q:1"],
        "feedback": "Synthetic repair for publication recovery",
    }
    plan = c["post"]("reprocess-preview", body).json()["data"]
    c["execute"](
        c["post"]("reprocess", {**body, "expected_plan_hash": plan["plan_hash"]})
    )
    c["approve"]("sample")
    accepted = synthetic_review_publish(client, c, publish=False)
    real_verify = publication.verify_actual_batch

    def injected_failure(*args):
        raise ProcessingError(
            "BATCH_INCOMPLETE",
            "Synthetic validation interruption after committed pending batch",
        )

    monkeypatch.setattr(publication, "verify_actual_batch", injected_failure)
    c["execute"](accepted, expected_code=2)
    failed = c["detail"]()
    assert (
        failed["publication_state"] == "failed"
        and failed["current_batch_id"] == old
        and failed["is_student_visible"]
    )
    from app.db import models_processing as p
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal

    with SessionLocal() as db:
        revision = db.get(m.ProcessingWorkflowRevision, UUID(failed["revision_id"]))
        pending = revision.batch_id
        assert pending and pending != old
        assert db.get(p.ProcessingTask, revision.final_task_id).state == "completed"
    monkeypatch.setattr(publication, "verify_actual_batch", real_verify)
    c["execute"](
        c["post"](
            "publish",
            {
                "expected_result_hash": failed["result_hash"],
                "review_session_id": failed["review_session_id"],
                "expected_current_batch_id": old,
                "retry_of_operation_id": accepted.json()["data"]["operation_id"],
            },
        )
    )
    after = c["detail"]()
    assert (
        after["current_batch_id"] == pending
        and after["publication_state"] == "published"
    )
    assert after["is_student_visible"] is False
    for endpoint in (
        f"/api/v1/listening-papers/{pid}/audio",
        f"/api/v1/admin/listening-papers/{pid}/companion",
        f"/api/v1/admin/listening-papers/{pid}/annotations",
        f"/api/v1/admin/listening-papers/{pid}/checks",
    ):
        response = client.get(
            endpoint, params={"expected_batch_id": old}, headers=c["headers"]
        )
        assert response.status_code == 409, response.text


def test_option_errors_database_guards_and_formal_read(client, pipeline):
    from sqlalchemy.exc import DBAPIError

    from app.db.base import SessionLocal
    from app.services.processing.validation import load_dictionary

    c = pipeline
    code = next(
        r["error_cause_code"]
        for t in load_dictionary()["tables"]
        if t["name"] == "error_cause"
        for r in t["rows"]
        if r["cause_level"] == 3 and r["status"] == "启用"
    )
    evidence = {
        "evidence_segment_src_ids": ["s:1"],
        "quote": "The answer is Alpha.",
        "support_note": "Synthetic: body explicitly states Alpha, contradicting Beta.",
    }
    c["errors"].extend(
        [
            {
                "error_cause_code": code,
                "option_letter": "B",
                "rationale": "Synthetic distractor mechanism for Beta",
                "evidence": [evidence, evidence],
            },
            {
                "error_cause_code": code,
                "option_letter": "C",
                "rationale": "Synthetic Gamma mechanism",
                "evidence": [evidence],
            },
        ]
    )
    complete_to_review(c)
    synthetic_review_publish(client, c)
    detail = c["detail"]()
    batch = detail["current_batch_id"]
    pid = detail["exam_paper_id"]
    response = client.get(
        f"/api/v1/admin/listening-papers/{pid}/annotations",
        params={"expected_batch_id": batch},
        headers=c["headers"],
    )
    assert response.status_code == 200, response.text
    q = response.json()["data"]["items"][0]
    assert (
        len(q["options"][1]["error_causes"])
        == len(q["options"][2]["error_causes"])
        == 1
    )
    assert len(q["options"][1]["error_causes"][0]["evidence"]) == 1
    assert q["options"][0]["error_causes"] == []
    companion = client.get(
        f"/api/v1/admin/listening-papers/{pid}/companion",
        params={"expected_batch_id": batch},
        headers=c["headers"],
    )
    assert companion.status_code == 200, companion.text
    assert all(
        q["review_status"] == "已通过"
        for passage in companion.json()["data"]["passages"]
        for q in passage["questions"]
    )
    with SessionLocal() as db:
        parent = db.execute(
            text(
                "SELECT id FROM error_question_relations "
                "WHERE batch_id=:b AND option_letter='B'"
            ),
            {"b": batch},
        ).scalar_one()
        for sql in (
            "UPDATE error_question_relations SET option_letter='A' WHERE id=:p",
            "DELETE FROM error_question_relations WHERE owner_relation_id=:p",
            "UPDATE transcript_segments SET segment_type='question' WHERE id IN "
            "(SELECT segment_id FROM evidence_segments WHERE batch_id=:b)",
            "UPDATE processing_review_sessions SET state='draft' WHERE id=:s",
        ):
            with pytest.raises(DBAPIError):
                db.execute(
                    text(sql),
                    {"b": batch, "p": parent, "s": detail["review_session_id"]},
                )
                db.commit()
            db.rollback()
    stale = client.post(
        f"/api/v1/admin/listening-papers/{pid}/visibility",
        headers=c["headers"],
        json={"action": "confirm", "expected_batch_id": batch + 99999},
    )
    assert (
        stale.status_code == 409
        and stale.json()["error_code"] == "CURRENT_BATCH_CHANGED"
    )


def test_stop_revokes_execution_without_advancing_or_charging(pipeline):
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.module3.contracts import ProcessingError
    from app.module3.workflow_worker import fence

    c = pipeline
    response = c["post"]("start", {"reason": "Synthetic stop test"})
    assert response.status_code == 202
    operation = response.json()["data"]
    token = uuid4()
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, UUID(operation["operation_id"]))
        command.state, command.execution_token = "running", token
        from app.services.processing.tasks import utcnow

        command.lease_expires_at = utcnow() + timedelta(seconds=120)
        workflow = db.get(m.ProcessingWorkflow, UUID(c["id"]))
        workflow.processing_state = "running"
        db.commit()
    response = c["post"]("stop", {"reason": "Synthetic explicit stop"})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        with pytest.raises(ProcessingError, match="执行权"):
            fence(db, UUID(operation["operation_id"]), token)
    assert c["detail"]()["usage"]["known_usd"] == "0"


def test_reprocess_plan_preconditions_and_full_review_reset(client, pipeline):
    c = pipeline
    complete_to_review(c)
    before = c["detail"]()
    body = {
        "expected_result_hash": before["result_hash"],
        "question_src_ids": ["q:1"],
        "feedback": "Synthetic returned feedback requiring explicit regeneration",
    }
    preview = c["post"]("reprocess-preview", body)
    assert preview.status_code == 200, preview.text
    plan = preview.json()["data"]
    assert plan["sample_valid"] is False and plan["generation_count"] == 1
    assert c["detail"]()["usage"] == before["usage"]
    bad = c["post"]("reprocess", {**body, "expected_plan_hash": "0" * 64})
    assert bad.status_code == 409 and bad.json()["error_code"] == "PLAN_CHANGED"
    c["execute"](
        c["post"]("reprocess", {**body, "expected_plan_hash": plan["plan_hash"]})
    )
    assert c["detail"]()["processing_state"] == "awaiting_sample"
    c["approve"]("sample")
    after = c["detail"]()
    assert after["review_session_id"] != before["review_session_id"]
    assert (
        after["content_review_state"] == "pending"
        and after["review_session_version"] == 1
    )
    session = client.get(
        f"{BASE}/{c['id']}/review-sessions/{after['review_session_id']}",
        headers=c["headers"],
    ).json()["data"]
    assert session["items"] == []
    assert after["usage"]["known_usd"] == "0.00200000"


def test_source_correction_forbids_labels_and_keeps_parent_immutable(client, pipeline):
    c = pipeline
    complete_to_review(c)
    before = c["detail"]()
    material = next(row for row in before["materials"] if row["kind"] == "answer")
    change = {
        "question_src_id": "q:1",
        "field": "explanation_text",
        "expected_value": "The body explicitly states Alpha.",
        "value": "Synthetic corrected source explanation: Alpha.",
        "material_id": material["material_id"],
        "page": 1,
        "locator": "Synthetic PDF page 1",
    }
    body = {
        "expected_result_hash": before["result_hash"],
        "reason": "Synthetic correction with original source",
        "changes": [change],
    }
    denied = c["post"](
        "source-corrections",
        {**body, "changes": [{**change, "field": "error_cause_code"}]},
    )
    assert denied.status_code == 422
    stale = c["post"](
        "source-corrections",
        {**body, "changes": [{**change, "expected_value": "wrong previous value"}]},
    )
    assert stale.status_code == 409
    response = c["post"]("source-corrections", body)
    assert response.status_code == 201, response.text
    current = c["detail"]()
    assert (
        current["revision_id"] != before["revision_id"]
        and current["processing_state"] == "awaiting_source"
    )
    assert current["review_session_id"] is None
    c["approve"]("source")
    c["approve"]("sample")
    final = c["detail"]()
    assert final["result_hash"] != before["result_hash"]
    assert final["review_session_id"] != before["review_session_id"]


def test_question_twelve_reuses_sample_and_only_regenerates_target(client, pipeline):
    c = pipeline
    source = c["source"]
    for index in range(2, 13):
        q = copy.deepcopy(source["questions"][0])
        q.update(_src_id=f"q:{index}", question_code=f"Q{index}", question_index=index)
        source["questions"].append(q)
        pr = copy.deepcopy(source["presentations"][0])
        pr.update(
            _src_id=f"pr:{index}", question_src_id=f"q:{index}", question_no=index
        )
        source["presentations"].append(pr)
    complete_to_review(c)
    before = c["detail"]()
    body = {
        "expected_result_hash": before["result_hash"],
        "question_src_ids": ["q:12"],
        "feedback": "Synthetic distractor feedback for Q12",
    }
    response = c["post"]("reprocess-preview", body)
    assert response.status_code == 200, response.text
    plan = response.json()["data"]
    assert (
        plan["sample_valid"]
        and plan["generation_count"] == 1
        and plan["review_count"] == 12
    )
    c["execute"](
        c["post"]("reprocess", {**body, "expected_plan_hash": plan["plan_hash"]})
    )
    after = c["detail"]()
    assert after["processing_state"] == "awaiting_review"
    assert after["review_session_id"] != before["review_session_id"]
    assert after["usage"]["known_usd"] == "0.01300000"
    synthetic_review_publish(client, c)
    assert c["detail"]()["publication_state"] == "published"
    assert (
        after["gates"][
            next(i for i, g in enumerate(after["gates"]) if g["kind"] == "sample")
        ]["state"]
        == "approved"
    )


def test_missing_source_is_correctable_before_any_generation(client, pipeline):
    c = pipeline
    c["source"]["questions"][0]["explanation_text"] = ""
    c["execute"](c["post"]("start", {"reason": "Synthetic missing source"}))
    c["approve"]("align")
    detail = c["detail"]()
    projection = detail["stages"]["source"]
    denied = c["post"](
        "stage-approvals",
        {
            "stage": "source",
            "expected_stage_dependency_hash": projection["dependency_hash"],
            "artifact_hash": projection["artifact_hash"],
            "decision": "approved",
            "items": [
                {"reference": "q:1", "decision": "approved", "reason": "synthetic"}
            ],
        },
    )
    assert (
        denied.status_code == 409 and denied.json()["error_code"] == "SOURCE_REQUIRED"
    )
    stage = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/stages/source",
        headers=c["headers"],
    ).json()["data"]
    answer = next(row for row in detail["materials"] if row["kind"] == "answer")
    response = c["post"](
        "source-corrections",
        {
            "expected_result_hash": stage["result_hash"],
            "reason": "Synthetic source correction",
            "changes": [
                {
                    "question_src_id": "q:1",
                    "field": "explanation_text",
                    "expected_value": "",
                    "value": "Synthetic restored source says Alpha.",
                    "material_id": answer["material_id"],
                    "page": 1,
                    "locator": "Synthetic original p1",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert c["detail"]()["usage"]["known_usd"] == "0"
    c["approve"]("source")
    c["approve"]("sample")
    assert c["detail"]()["processing_state"] == "awaiting_review"


def test_reference_correction_realigns_and_rejects_manual_times(client, pipeline):
    from app.db.base import SessionLocal
    from app.db.models_processing import MaterialSource

    c = pipeline
    c["execute"](c["post"]("start", {"reason": "Synthetic reference correction"}))
    before = c["detail"]()
    material = next(row for row in before["materials"] if row["kind"] == "answer")
    with SessionLocal() as db:
        source = db.get(MaterialSource, material["material_id"])
        row = {
            "segment_id": "s:1",
            "text": "Synthetic corrected original sentence.",
            "segment_type": "body",
            "passage_key": "p:1",
            "source_storage_key": source.storage_key,
            "source_sha256": source.sha256,
            "source_pages": [1],
            "search_start_ms": 0,
            "search_end_ms": 2000,
        }
    body = {
        "expected_alignment_artifact_hash": before["stages"]["align"]["artifact_hash"],
        "reason": "Synthetic original OCR correction",
        "source_basis": "Synthetic original page1 locator",
        "reference_segments": [row],
    }
    denied = c["post"](
        "alignment-corrections",
        {**body, "reference_segments": [{**row, "start_ms": 0, "end_ms": 2000}]},
    )
    assert denied.status_code == 422
    c["execute"](c["post"]("alignment-corrections", body))
    after = c["detail"]()
    assert (
        after["revision_id"] != before["revision_id"]
        and after["processing_state"] == "awaiting_alignment"
    )
    assert set(after["stages"]) == {"align"}


def test_alignment_audio_is_authenticated_revision_bound_and_read_only(
    client, pipeline, monkeypatch
):
    from app.services.processing import media

    c = pipeline
    c["execute"](c["post"]("start", {"reason": "Synthetic audio contract check"}))
    before = c["detail"]()
    stage_url = f"{BASE}/{c['id']}/revisions/{before['revision_id']}"
    stage = client.get(stage_url + "/stages/align", headers=c["headers"]).json()["data"]
    segment = next(row for row in stage["items"] if row["segment_type"] == "body")
    calls = []

    def clip(source, audio_hash, start_ms, end_ms, settings):
        calls.append((audio_hash, start_ms, end_ms))
        return c["context"]["audio"]

    monkeypatch.setattr(media, "evidence_clip", clip)
    url = stage_url + f"/segments/{segment['_src_id']}/audio"
    assert client.get(url).status_code == 401
    token = client.post(
        "/api/v1/login", json={"username": "student", "password": "student123"}
    )
    assert token.status_code == 200, token.text
    assert (
        client.get(
            url,
            headers={"Authorization": "Bearer " + token.json()["data"]["token"]},
        ).status_code
        == 403
    )
    response = client.get(url, headers=c["headers"])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-source-start-ms"] == str(segment["start_ms"])
    assert response.headers["x-source-end-ms"] == str(segment["end_ms"])
    assert calls == [(calls[0][0], segment["start_ms"], segment["end_ms"])]
    assert len(calls[0][0]) == 64
    assert (
        client.get(
            stage_url + "/segments/absent/audio", headers=c["headers"]
        ).status_code
        == 404
    )
    stale = url.replace(before["revision_id"], str(uuid4()))
    assert client.get(stale, headers=c["headers"]).status_code == 409
    after = c["detail"]()
    assert after["row_version"] == before["row_version"]
    assert after["gates"] == before["gates"]
    assert after["usage"] == before["usage"]
    assert after["processing_state"] == "awaiting_alignment"


def test_upload_fencing_and_recovery(client, pipeline):
    from app.db.base import SessionLocal
    from app.services.processing import uploads

    c = pipeline
    before = c["detail"]()
    old_audio = next(row for row in before["materials"] if row["kind"] == "audio")
    response = c["post"](
        "material-uploads",
        {
            "kind": "audio",
            "filename": "new.wav",
            "declared_size": 100,
            "expected_upload_version": old_audio["upload_version"],
        },
    )
    assert response.status_code == 201
    upload = response.json()["data"]["result"]
    with SessionLocal() as db:
        db.execute(
            text(
                "UPDATE processing_workflow_materials "
                "SET lease_expires_at=now()-interval '1 second' WHERE id=:id"
            ),
            {"id": upload["upload_id"]},
        )
        db.commit()
        assert uploads.expire_uploads(db) == 1
        db.commit()
    detail = c["detail"]()
    assert {row["kind"]: row["state"] for row in detail["materials"]} == {
        "paper": "ready",
        "answer": "ready",
        "audio": "failed",
    }
    response = client.put(
        f"{BASE}/{c['id']}/materials/audio",
        content=b"x",
        headers={
            **c["headers"],
            "X-Upload-Id": old_audio["upload_id"],
            "X-Expected-Revision-Id": detail["revision_id"],
            "X-Expected-Upload-Version": str(old_audio["upload_version"]),
        },
    )
    assert response.status_code == 409
    assert c["post"]("start", {"reason": "synthetic"}).status_code == 409


def test_complete_synthetic_pipeline_and_empty_error_review(client, pipeline):
    c = pipeline
    c["execute"](c["post"]("start", {"reason": "synthetic technical run"}))
    assert c["detail"]()["processing_state"] == "awaiting_alignment"
    projection = c["detail"]()["stages"]["align"]
    assert (
        c["post"](
            "continue",
            {
                "stage": "align",
                "expected_stage_dependency_hash": projection["dependency_hash"],
            },
        ).status_code
        == 409
    )
    c["approve"]("align")
    c["approve"]("source")
    c["approve"]("sample")
    detail = c["detail"]()
    assert detail["processing_state"] == "awaiting_review"
    assert detail["usage"]["known_usd"] == "0.00100000"
    session_id = detail["review_session_id"]
    endpoint = f"{BASE}/{c['id']}/review-sessions/{session_id}"
    submit = {
        **c["pre"](),
        "expected_result_hash": detail["result_hash"],
        "expected_session_version": 1,
        "audio_confirmed": True,
        "approval_reference": "Synthetic assertion, not human audio acceptance",
    }
    assert (
        client.post(
            endpoint + "/submit",
            headers={**c["headers"], "Idempotency-Key": str(uuid4())},
            json=submit,
        ).status_code
        == 409
    )
    questions = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/questions",
        headers=c["headers"],
    ).json()["data"]
    question = questions["items"][0]
    assert question["generation_state"] == "generated_empty"
    item = {
        "question_src_id": question["question_src_id"],
        "content": "approved",
        "empty_errors_confirmed": True,
        "note": "Synthetic confirmation",
        "issues": [],
        **{
            field: [{"reference": ref, "decision": "approved"} for ref in refs]
            for field, refs in question["review_requirements"].items()
        },
    }
    response = client.patch(
        endpoint + "/items",
        headers={**c["headers"], "Idempotency-Key": str(uuid4())},
        json={
            **c["pre"](),
            "expected_result_hash": detail["result_hash"],
            "expected_session_version": 1,
            "items": [item],
        },
    )
    assert response.status_code == 200, response.text
    response = client.post(
        endpoint + "/submit",
        headers={**c["headers"], "Idempotency-Key": str(uuid4())},
        json={**submit, "expected_session_version": 2},
    )
    assert response.status_code == 200, response.text
    detail = c["detail"]()
    publication = c["execute"](
        c["post"](
            "publish",
            {
                "expected_result_hash": detail["result_hash"],
                "review_session_id": session_id,
                "expected_current_batch_id": None,
            },
        )
    )
    detail = c["detail"]()
    assert detail["publication_state"] == "published"
    assert (
        detail["current_batch_id"] is not None and detail["is_student_visible"] is False
    )
    response = client.get(
        f"{BASE}/{c['id']}/operations/{publication['operation_id']}",
        headers=c["headers"],
    )
    assert response.json()["data"]["state"] == "succeeded"


def test_live_progress_timer_and_expired_lease_are_read_only(client, pipeline):
    from app.db import models_processing as p
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.services.processing.tasks import utcnow

    c = pipeline
    response = c["post"]("start", {"reason": "Synthetic progress check"})
    assert response.status_code == 202, response.text
    operation = response.json()["data"]
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, UUID(operation["operation_id"]))
        task = db.get(p.ProcessingTask, UUID(operation["result"]["task_id"]))
        command.state = "running"
        command.execution_token = task.lease_token = uuid4()
        command.lease_expires_at = task.expires_at = utcnow() + timedelta(seconds=120)
        task.state, task.stage = "running", "reuse"
        task.created_at = utcnow() - timedelta(seconds=60)
        workflow = db.get(m.ProcessingWorkflow, UUID(c["id"]))
        workflow.processing_state = "running"
        root = (
            c["context"]["settings"].m3_path("m3_artifacts_dir")
            / str(task.id)
            / "assembly-documents"
        )
        root.mkdir(parents=True)
        material_id = task.request["material_ids"][1]
        (root / "input-manifest.json").write_text(
            json.dumps(
                {
                    "task_id": str(task.id),
                    "files": [{"material_id": material_id, "page_numbers": [2, 3]}],
                }
            ),
            encoding="utf-8",
        )
        db.commit()
    first = c["detail"]()
    value = first["progress"]
    assert value["active"] is True
    assert value["stage"] == "assembly_extract"
    assert value["unit"] == "页" and value["total_count"] == 2
    assert value["elapsed_ms"] >= 60000
    assert value["started_at"] and value["observed_at"]
    assert first["gates"] == []
    assert c["detail"]()["row_version"] == first["row_version"]
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, UUID(operation["operation_id"]))
        command.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    value = c["detail"]()["progress"]
    assert value["active"] is False
    assert "心跳已过期" in value["description"]
    with SessionLocal() as db:
        assert (
            db.scalars(
                select(m.ProcessingStageApproval).where(
                    m.ProcessingStageApproval.revision_id == UUID(first["revision_id"])
                )
            ).all()
            == []
        )


def test_source_projection_before_annotation_preserves_frozen_payload(client, pipeline):
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.services.processing import orchestration

    c = pipeline
    for section in (
        "evidences",
        "skill_question_relations",
        "error_question_relations",
        "other_relations",
    ):
        c["source"].pop(section, None)
    c["execute"](c["post"]("start", {"reason": "Synthetic source projection check"}))
    c["approve"]("align")
    detail = c["detail"]()
    assert detail["processing_state"] == "awaiting_source"
    assert detail["issues"] == []
    response = client.get(
        f"{BASE}/{c['id']}/revisions/{detail['revision_id']}/questions",
        headers=c["headers"],
    )
    assert response.status_code == 200, response.text
    value = response.json()["data"]
    assert value["items"][0]["generation_state"] == "not_generated"
    assert value["items"][0]["review_requirements"] == {
        "primary_skills": [],
        "answer_evidence": [],
        "error_causes": [],
    }
    with SessionLocal() as db:
        revision = db.get(m.ProcessingWorkflowRevision, UUID(detail["revision_id"]))
        payload, _ = orchestration.stage_payload(
            db, revision, "source", c["context"]["settings"]
        )
        assert "skill_question_relations" not in payload


def test_waiting_progress_duration_is_frozen(pipeline):
    c = pipeline
    c["execute"](c["post"]("start", {"reason": "Synthetic paused clock check"}))
    first, second = c["detail"]()["progress"], c["detail"]()["progress"]
    assert first["active"] is False
    assert first["elapsed_ms"] == second["elapsed_ms"]
    assert "等待核听确认" in first["description"]


def test_runtime_retry_reuses_valid_responses_and_revalidates_full_review(
    client, pipeline, monkeypatch
):
    from app.db import models_processing as p
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.module3 import llm
    from app.module3.contracts import fingerprint

    c = pipeline
    for index in range(2, 6):
        question = copy.deepcopy(c["source"]["questions"][0])
        question.update(
            _src_id=f"q:{index}", question_code=f"Q{index}", question_index=index
        )
        c["source"]["questions"].append(question)
        presentation = copy.deepcopy(c["source"]["presentations"][0])
        presentation.update(
            _src_id=f"pr:{index}", question_src_id=f"q:{index}", question_no=index
        )
        c["source"]["presentations"].append(presentation)
    original = llm.request_json
    calls = []

    def model(*args, **kwargs):
        raw, call = original(*args, **kwargs)
        calls.append(raw["question_src_id"])
        if raw["question_src_id"] == "q:3" and calls.count("q:3") == 1:
            raw["skills"][0]["evidence_segment_src_ids"] = ["absent"]
            with SessionLocal() as db:
                attempt = db.get(p.LlmAttempt, call["attempt_id"])
                response = copy.deepcopy(attempt.response_payload)
                response["choices"][0]["message"]["content"] = json.dumps(raw)
                attempt.response_payload = response
                db.commit()
        return raw, call

    monkeypatch.setattr(llm, "request_json", model)
    c["execute"](c["post"]("start", {"reason": "Synthetic runtime recovery"}))
    c["approve"]("align")
    before = c["detail"]()
    stage = before["stages"]["source"]
    approved = c["post"](
        "stage-approvals",
        {
            "stage": "source",
            "artifact_hash": stage["artifact_hash"],
            "expected_stage_dependency_hash": stage["dependency_hash"],
            "decision": "approved",
            "items": [
                {
                    "reference": q["_src_id"],
                    "decision": "approved",
                    "reason": "Synthetic source check",
                }
                for q in c["source"]["questions"]
            ],
        },
    )
    assert approved.status_code == 200, approved.text
    failed = c["execute"](
        c["post"](
            "continue",
            {
                "stage": "source",
                "expected_stage_dependency_hash": stage["dependency_hash"],
            },
        ),
        expected_code=2,
    )
    assert c["detail"]()["issues"][-1]["code"] == "ANNOTATION_EVIDENCE_INVALID"
    # Simulate a new runtime deployment without mutating frozen DB identities,
    # source content, the prompt or the dictionary.
    with SessionLocal() as db:
        revision = db.get(m.ProcessingWorkflowRevision, UUID(before["revision_id"]))
        manifest = copy.deepcopy(revision.rules_manifest)
        manifest["implementation"]["app/module3/workflow_worker.py"] = "0" * 64
        manifest["manifest_hash"] = fingerprint(
            {k: v for k, v in manifest.items() if k != "manifest_hash"}
        )
    from app.services.processing import orchestration, reviewing, workflows

    for module in (orchestration, reviewing, workflows):
        monkeypatch.setattr(module, "rules_manifest", lambda: copy.deepcopy(manifest))
    c["execute"](
        c["post"](
            "retries",
            {
                "reason": "Explicit runtime repair",
                "retry_of_operation_id": failed["operation_id"],
            },
        )
    )
    after = c["detail"]()
    assert after["revision_id"] != before["revision_id"]
    assert after["processing_state"] == "awaiting_sample"
    assert calls == ["q:1", "q:2", "q:3", "q:3", "q:4", "q:5"]
    assert all(
        g["state"] == "approved"
        for g in after["gates"]
        if g["kind"] in {"align", "source"}
    )
    c["approve"]("sample")
    synthetic_review_publish(client, c)
    assert c["detail"]()["publication_state"] == "published"
    assert len(calls) == 6


def test_standalone_worker_registers_models_and_renews_task_lease(pipeline):
    import os
    import subprocess
    import sys

    from app.db import models_processing as p
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.services.processing.tasks import utcnow

    c = pipeline
    response = c["post"]("start", {"reason": "Synthetic standalone heartbeat"})
    operation = response.json()["data"]
    token = uuid4()
    with SessionLocal() as db:
        command = db.get(m.ProcessingWorkflowCommand, UUID(operation["operation_id"]))
        task = db.get(p.ProcessingTask, UUID(operation["result"]["task_id"]))
        command.state, task.state = "running", "running"
        command.execution_token = task.lease_token = token
        command.lease_expires_at = task.expires_at = utcnow() + timedelta(seconds=120)
        db.commit()
    code = """
import sys
from uuid import UUID
from types import SimpleNamespace
from app.module3.workflow_worker import heartbeat
from app.db.base import Base
assert 'users' in Base.metadata.tables
class OneRenewal:
    count = 0
    def wait(self, seconds):
        self.count += 1
        return self.count > 1
heartbeat(UUID(sys.argv[1]), UUID(sys.argv[2]),
          SimpleNamespace(m3_heartbeat_seconds=1, m3_lease_seconds=120),
          OneRenewal())
"""
    # No API bootstrap imports may mask a standalone ORM registry gap.
    result = subprocess.run(
        [sys.executable, "-c", code, operation["operation_id"], str(token)],
        env={**os.environ, "DEEPSEEK_API_KEY": ""},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    with SessionLocal() as db:
        task = db.get(p.ProcessingTask, UUID(operation["result"]["task_id"]))
        assert task.heartbeat_at is not None
