"""Synthetic full-paper technical loop. No real listening or paid inference."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from tests.module3.test_workflow_pipeline import pipeline, synthetic_review_publish  # noqa: F401

BASE = "/api/v1/admin/processing-workflows"
pytestmark = pytest.mark.usefixtures("pipeline")


def library_post(client, c, suffix, body):
    return client.post(
        f"{BASE}/{c['id']}/{suffix}",
        headers={**c["headers"], "Idempotency-Key": str(uuid4())},
        json=body,
    )


def library_draft(client, c):
    response = client.get(f"{BASE}/{c['id']}/edit-draft", headers=c["headers"])
    assert response.status_code == 200, response.text
    return response.json()["data"]


def edit_pre(draft):
    return {
        "expected_row_version": draft["row_version"],
        "expected_content_hash": draft["content_hash"],
        "reason": "Synthetic technical verification only",
    }


def source_ready(client, c):
    c["execute"](c["post"]("start", {"reason": "Synthetic library route"}))
    assert c["detail"]()["processing_state"] == "queued"
    from app.db.base import SessionLocal
    from app.db.models_processing_workflows import ProcessingWorkflowCommand
    from app.services.processing.workflows import command_data

    with SessionLocal() as db:
        command = db.scalar(
            select(ProcessingWorkflowCommand).where(
                ProcessingWorkflowCommand.workflow_id == UUID(c["id"]),
                ProcessingWorkflowCommand.action == "auto_assemble",
            )
        )
        from fastapi.encoders import jsonable_encoder

        data = jsonable_encoder(command_data(command))
    c["execute"](SimpleNamespace(status_code=202, text="", json=lambda: {"data": data}))
    assert c["detail"]()["processing_state"] == "awaiting_source"
    assert "sample" not in c["detail"]()["stages"]


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
@pytest.mark.parametrize("waiver", [False, True])
def test_library_candidates_adoption_local_review_and_publication(
    client, request, waiver, monkeypatch
):
    c = request.getfixturevalue("pipeline")
    c["source"]["presentations"][0]["option_letter_mapping"] = dict(
        zip("ABCD", "BCDA", strict=True)
    )
    source_ready(client, c)
    c["errors"].append(
        {
            "error_cause_code": "E4.3",
            "option_letter": "B",
            "rationale": "Synthetic Beta differs from stated Alpha",
            "evidence": [
                {
                    "evidence_segment_src_ids": ["s:1"],
                    "quote": "The answer is Alpha.",
                    "support_note": "Synthetic source states Alpha, not Beta.",
                }
            ],
        }
    )
    c["approve"]("source")
    assert c["detail"]()["processing_state"] == "candidate_ready"
    assert c["detail"]()["result_hash"] is None
    generated = client.get(f"{BASE}/{c['id']}/candidates", headers=c["headers"]).json()[
        "data"
    ]["items"]
    assert len(generated) == 25
    draft = library_draft(client, c)
    assert draft["version_no"] == 0
    body = {
        **edit_pre(draft),
        "candidate_ids": [r["id"] for r in generated],
        "scopes": ["skills", "answer_evidence", "errors:B", "errors:C", "errors:D"],
    }
    preview = library_post(client, c, "candidate-adoption-preview", body)
    assert preview.status_code == 200, preview.text
    adopted = library_post(client, c, "candidate-adoptions", body)
    assert adopted.status_code == 200, adopted.text
    draft = library_draft(client, c)
    assert draft["version_no"] == 1
    assert not draft["issues"]
    if waiver:
        from copy import deepcopy

        candidate = deepcopy(
            next(r["payload"] for r in generated if r["question_src_id"] == "q:1")
        )
        candidate["skills"][0]["rationale"] += " Synthetic manual review."
        response = library_post(
            client,
            c,
            "manual-annotations",
            {
                **edit_pre(draft),
                "candidate": candidate,
            },
        )
        assert response.status_code == 200, response.text
        draft = library_draft(client, c)
    source = library_post(client, c, "prepare-source-review", edit_pre(draft))
    assert source.status_code == 200, source.text
    if waiver:
        stage = c["detail"]()["stages"]["source"]
        response = c["post"](
            "stage-approvals",
            {
                "stage": "source",
                "artifact_hash": stage["artifact_hash"],
                "expected_stage_dependency_hash": stage["dependency_hash"],
                "decision": "approved",
                "reviewer_kind": "codex",
                "listening_waiver_reference": "Synthetic waiver; not listened",
                "items": [
                    {
                        "reference": q["_src_id"],
                        "decision": "approved",
                        "reason": "Synthetic content check",
                    }
                    for q in c["source"]["questions"]
                ],
            },
        )
        assert response.status_code == 200, response.text
    else:
        c["approve"]("source", continue_after=False)
    frozen = library_post(client, c, "prepare-final-review", edit_pre(draft))
    assert frozen.status_code == 200, frozen.text
    if waiver:
        original_post = c["post"]

        def explicit_waiver(action, body):
            if action.endswith("/submit"):
                assert (
                    original_post(
                        action,
                        {
                            **body,
                            "audio_confirmed": False,
                            "audio_waiver_reference": "Different source authorization",
                        },
                    ).status_code
                    == 409
                )
                body = {
                    **body,
                    "audio_confirmed": False,
                    "audio_waiver_reference": "Synthetic waiver; not listened",
                }
            return original_post(action, body)

        c["post"] = explicit_waiver
    synthetic_review_publish(client, c)
    if waiver:
        from app.db.base import SessionLocal
        from app.db.models_processing import ProcessingReview
        from app.db.models_processing_workflows import ProcessingStageApproval

        with SessionLocal() as db:
            approval = db.scalar(
                select(ProcessingStageApproval)
                .where(
                    ProcessingStageApproval.revision_id
                    == UUID(c["detail"]()["revision_id"])
                )
                .order_by(ProcessingStageApproval.created_at.desc())
            )
            assert approval.items["listening_items"] == []
            assert (
                approval.items["listening_review"]["actual_listening_performed"]
                is False
            )
            audio = db.scalar(
                select(ProcessingReview).where(
                    ProcessingReview.task_id == UUID(c["detail"]()["task_id"]),
                    ProcessingReview.scope == "audio",
                )
            )
            assert audio.items[0]["verdict"] == "WAIVED"
            assert audio.items[0]["actual_listening_performed"] is False
            assert audio.items[0]["review_basis"] == "user_waiver"
    detail = c["detail"]()
    assert detail["publication_state"] == "published"
    assert detail["is_student_visible"] is False
    response = client.get(
        f"/api/v1/admin/listening-papers/{detail['exam_paper_id']}/annotations",
        headers=c["headers"],
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["data"]["items"]) == 25
    from tests.module3.notebook_compatibility import assert_notebook_supplements

    assert_notebook_supplements(client, c, monkeypatch)


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_library_rejects_sample_and_missing_actual_listening(client, request):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    detail = c["detail"]()
    projection = detail["stages"]["source"]
    response = c["post"](
        "stage-approvals",
        {
            "stage": "source",
            "artifact_hash": projection["artifact_hash"],
            "expected_stage_dependency_hash": projection["dependency_hash"],
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
    assert response.status_code == 409
    assert response.json()["error_code"] == "LISTENING_REVIEW_REQUIRED"
    unsupported = c["post"](
        "continue",
        {
            "stage": "sample",
            "expected_stage_dependency_hash": projection["dependency_hash"],
        },
    )
    assert unsupported.status_code == 409
    assert unsupported.json()["error_code"] == "STAGE_NOT_SUPPORTED"


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_regeneration_is_independent_and_keeps_edit_head(client, request, monkeypatch):
    c = request.getfixturevalue("pipeline")
    from pydantic import SecretStr

    monkeypatch.setattr(
        c["context"]["settings"], "deepseek_api_key", SecretStr("synthetic-only")
    )
    source_ready(client, c)
    c["approve"]("source", continue_after=False)
    before = library_draft(client, c)
    workflow_before = c["detail"]()
    body = {**edit_pre(before), "provider": "deepseek", "question_src_ids": ["q:12"]}
    queued = library_post(client, c, "candidate-generations", body)
    assert queued.status_code == 202, queued.text
    from app.module3 import workflow_worker

    annotate = workflow_worker.annotate

    def observe_generation(*args, **kwargs):
        running = c["detail"]()
        assert running["progress"]["active"] is True
        assert running["progress"]["stage"] == "annotate"
        assert running["progress"]["total_count"] == 1
        assert running["revision_id"] == workflow_before["revision_id"]
        result = annotate(*args, **kwargs)
        assert c["detail"]()["progress"]["completed_count"] == 1
        return result

    monkeypatch.setattr(workflow_worker, "annotate", observe_generation)
    c["execute"](queued)
    after = library_draft(client, c)
    assert after == before
    current = c["detail"]()
    assert current["revision_id"] == workflow_before["revision_id"]
    assert current["content_review_state"] == workflow_before["content_review_state"]
    generated = client.get(f"{BASE}/{c['id']}/candidates", headers=c["headers"]).json()[
        "data"
    ]["items"]
    assert [r["question_src_id"] for r in generated] == ["q:12"]
    assert generated[0]["provider"] == "deepseek"
    assert generated[0]["requested_model"] == "deepseek-flash"


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_auto_assembly_progress_tracks_its_own_running_task(
    client, request, monkeypatch
):
    c = request.getfixturevalue("pipeline")
    from app.db.base import SessionLocal
    from app.module3 import worker
    from app.services.processing import tasks

    original = worker.process
    observations = []

    def observe_source(task_id, token, settings):
        with SessionLocal() as db:
            stage = tasks.get_task(db, task_id).request["workflow_stage"]
        if stage == "assemble":
            progress = c["detail"]()["progress"]
            assert progress["active"] is True
            assert progress["stage"] == "assemble"
            observations.append(progress)
        return original(task_id, token, settings)

    monkeypatch.setattr(worker, "process", observe_source)
    source_ready(client, c)
    assert len(observations) == 1


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_missing_credentials_does_not_queue_or_change_the_edit_head(
    client, request, monkeypatch
):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    c["approve"]("source", continue_after=False)
    before = library_draft(client, c)
    state = c["detail"]()
    monkeypatch.setattr(c["context"]["settings"], "deepseek_api_key", None)
    response = library_post(
        client,
        c,
        "candidate-generations",
        {**edit_pre(before), "provider": "deepseek", "question_src_ids": ["q:12"]},
    )
    assert response.status_code == 422
    assert response.json()["data"]["issue_code"] == "CREDENTIALS_MISSING"
    assert library_draft(client, c) == before
    after = c["detail"]()
    assert after["revision_id"] == state["revision_id"]
    assert after["processing_state"] == state["processing_state"]


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
@pytest.mark.parametrize("keep_head", [True, False])
def test_evaluation_waiver_is_audited_read_only_and_unavailable_to_normal_http(
    client, request, monkeypatch, keep_head
):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    from fastapi.encoders import jsonable_encoder
    from pydantic import SecretStr

    from app.db import models_library as l
    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper
    from app.schemas_library import EvaluationCandidates
    from app.services.processing.library_generation import generate
    from app.services.processing.workflows import command_data

    settings = c["context"]["settings"]
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-only"))
    before = library_draft(client, c)
    source = c["detail"]()["stages"]["source"]
    body = {
        **edit_pre(before),
        "provider": "deepseek",
        "question_src_ids": ["q:1"],
        "evaluation_id": str(uuid4()),
        "evaluation_source_hash": source["dependency_hash"],
        "evaluation_source_revision_id": c["detail"]()["revision_id"],
        "listening_waiver_reference": "Synthetic user waiver; no actual listening",
    }
    assert library_post(client, c, "candidate-generations", body).status_code == 422
    normal = {
        k: v
        for k, v in body.items()
        if not k.startswith("evaluation_") and k != "listening_waiver_reference"
    }
    assert library_post(client, c, "candidate-generations", normal).status_code == 409
    with SessionLocal() as db:
        paper = db.get(ExamPaper, before["exam_paper_id"])
        body["expected_row_version"] = paper.library_row_version
        if not keep_head:
            db.delete(db.get(l.LibraryEditHead, paper.id))
            db.commit()
        command = generate(
            db,
            UUID(c["id"]),
            EvaluationCandidates.model_validate(body),
            1,
            uuid4(),
            settings,
        )
        data = jsonable_encoder(command_data(command))
        db.commit()
    c["execute"](SimpleNamespace(status_code=202, text="", json=lambda: {"data": data}))
    if keep_head:
        assert library_draft(client, c) == before
    with SessionLocal() as db:
        if not keep_head:
            assert db.get(l.LibraryEditHead, before["exam_paper_id"]) is None
        revision = db.get(m.ProcessingWorkflowRevision, UUID(data["revision_id"]))
        assert revision.origin_manifest["evaluation_only"] is True
        assert (
            revision.origin_manifest["listening_review"]["actual_listening_performed"]
            is False
        )
        assert not db.scalar(
            select(m.ProcessingStageApproval.id)
            .join(
                m.ProcessingWorkflowRevision,
                m.ProcessingWorkflowRevision.id
                == m.ProcessingStageApproval.revision_id,
            )
            .where(m.ProcessingWorkflowRevision.workflow_id == UUID(c["id"]))
            .limit(1)
        )
    generated = client.get(f"{BASE}/{c['id']}/candidates", headers=c["headers"]).json()[
        "data"
    ]["items"]
    assert generated[0]["evaluation_only"] is True
    preview = library_post(
        client,
        c,
        "candidate-adoption-preview",
        {
            **edit_pre(before),
            "candidate_ids": [generated[0]["id"]],
            "scopes": ["skills"],
        },
    )
    assert preview.status_code == 409
    assert preview.json()["error_code"] == (
        "EVALUATION_CANDIDATE_READ_ONLY" if keep_head else "EDIT_HEAD_REQUIRED"
    )


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_pure_manual_full_paper_has_no_model_receipts_or_calls(client, request):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    dictionary = client.get(
        "/api/v1/admin/library-dictionary", headers=c["headers"]
    ).json()["data"]
    skill = dictionary["skills"][0]["code"]
    for question in c["source"]["questions"]:
        evidence = {
            "evidence_segment_src_ids": ["s:1"],
            "quote": "The answer is Alpha.",
            "support_note": "Synthetic local evidence only",
        }
        candidate = {
            "question_src_id": question["_src_id"],
            "skills": [
                {
                    **evidence,
                    "skill_code": skill,
                    "role": "PRIMARY",
                    "rationale": "Synthetic direct source check",
                }
            ],
            "answer_evidence": [evidence],
            "distractor_assessments": [
                {
                    "option_letter": letter,
                    "status": "NO_SUPPORTED_CANDIDATE",
                    "reason": f"Synthetic {letter} does not match source Alpha.",
                    "comparison_evidence": [evidence],
                    "candidates": [],
                    "unresolved_points": [],
                }
                for letter in "BCD"
            ],
            "uncertainties": [],
            "language_items": [],
            "genre_candidate": None,
        }
        saved = library_post(
            client,
            c,
            "manual-annotations",
            {**edit_pre(library_draft(client, c)), "candidate": candidate},
        )
        assert saved.status_code == 200, saved.text
    draft = library_draft(client, c)
    assert draft["version_no"] == 25
    assert not draft["issues"]
    assert (
        library_post(client, c, "prepare-source-review", edit_pre(draft)).status_code
        == 200
    )
    c["approve"]("source", continue_after=False)
    frozen = library_post(client, c, "prepare-final-review", edit_pre(draft))
    assert frozen.status_code == 200, frozen.text
    synthetic_review_publish(client, c)
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt, ProcessingTask
    from app.db.models_processing_workflows import ProcessingWorkflowRevision
    from app.services.processing import tasks

    with SessionLocal() as db:
        assert not db.scalar(
            select(LlmAttempt.id)
            .join(ProcessingTask)
            .where(ProcessingTask.workflow_id == UUID(c["id"]))
            .limit(1)
        )
        revision = db.get(
            ProcessingWorkflowRevision, UUID(c["detail"]()["revision_id"])
        )
        payload = tasks.get_draft(
            db, tasks.get_task(db, revision.final_task_id)
        ).payload
        assert payload["generation_receipts"] == []
        assert payload["library_provenance"]["origin_type"] == "MANUAL"


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_independent_candidate_budget_failure_preserves_parent_state(
    client, request, monkeypatch
):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    c["approve"]("source", continue_after=False)
    from pydantic import SecretStr

    from app.module3 import llm
    from app.module3.contracts import ProcessingError

    monkeypatch.setattr(
        c["context"]["settings"], "deepseek_api_key", SecretStr("synthetic-only")
    )

    def deny(*args, **kwargs):
        raise ProcessingError("BUDGET_LIMIT", "Synthetic exhausted budget")

    monkeypatch.setattr(llm, "request_json", deny)
    before = library_draft(client, c)
    state = c["detail"]()["processing_state"]
    queued = library_post(
        client,
        c,
        "candidate-generations",
        {
            **edit_pre(before),
            "provider": "deepseek",
            "question_src_ids": ["q:1"],
        },
    )
    assert queued.status_code == 202
    c["execute"](queued, expected_code=2)
    assert library_draft(client, c) == before
    assert c["detail"]()["processing_state"] == state


@pytest.mark.parametrize("pipeline", ["library"], indirect=True)
def test_executor_recovers_single_question_schema_failure_from_immutable_artifacts(
    client, request, monkeypatch
):
    c = request.getfixturevalue("pipeline")
    source_ready(client, c)
    import json
    from copy import deepcopy
    from uuid import uuid5

    from fastapi.encoders import jsonable_encoder
    from pydantic import SecretStr

    from app.db import models_processing_workflows as m
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm
    from app.schemas_library import EvaluationCandidates
    from app.services.processing import orchestration as o
    from app.services.processing.library_generation import generate
    from app.services.processing.workflows import command_data
    from scripts.compare_library_models import (
        fatal_reason,
        observations,
        recover_records,
    )

    settings = c["context"]["settings"]
    monkeypatch.setattr(settings, "deepseek_api_key", SecretStr("synthetic-only"))
    original = llm.request_json

    def invalid(*args, **kwargs):
        candidate, call = original(*args, **kwargs)
        candidate["distractor_assessments"][0].update(
            status="SUPPORTED", candidates=[], unresolved_points=[]
        )
        with SessionLocal() as db:
            attempt = db.get(LlmAttempt, call["attempt_id"])
            response = deepcopy(attempt.response_payload)
            response["choices"][0]["message"]["content"] = json.dumps(candidate)
            attempt.response_payload = response
            db.commit()
        return candidate, call

    monkeypatch.setattr(llm, "request_json", invalid)
    before = library_draft(client, c)
    detail = c["detail"]()
    evaluation_id = uuid4()
    with SessionLocal() as db:
        revision = db.get(m.ProcessingWorkflowRevision, UUID(detail["revision_id"]))
        source, projection = o.stage_payload(db, revision, "source", settings)
        paper = db.get(ExamPaper, before["exam_paper_id"])
        payload = EvaluationCandidates(
            **{
                **edit_pre(before),
                "expected_row_version": paper.library_row_version,
                "question_src_ids": ["q:1"],
                "provider": "deepseek",
                "evaluation_id": evaluation_id,
                "evaluation_source_revision_id": revision.id,
                "evaluation_source_hash": projection["dependency_hash"],
                "listening_waiver_reference": "Synthetic explicit waiver",
            }
        )
        command = generate(
            db,
            UUID(c["id"]),
            payload,
            1,
            uuid5(evaluation_id, "deepseek:q:1"),
            settings,
        )
        data = jsonable_encoder(command_data(command))
        db.commit()
    c["execute"](
        SimpleNamespace(status_code=202, text="", json=lambda: {"data": data}),
        expected_code=2,
    )
    record = observations(
        UUID(data["operation_id"]), source, source["questions"][0], settings
    )
    assert record["reason"] == "PROCESSING_FAILED"
    assert record["failure_classification"] == "ANNOTATION_SCHEMA_INVALID"
    assert fatal_reason(record) is None
    assert record["correction_count"] == 2
    stored = {
        "deepseek": {"q:1": {**record, "raw": {"tampered": "not a model response"}}},
        "bailian": {},
    }
    recovered = recover_records(
        source,
        {
            "evaluation_id": str(evaluation_id),
            "workflow_id": c["id"],
            "operator_user_id": 1,
        },
        stored,
        settings,
    )
    assert recovered["deepseek"]["q:1"]["raw"] == record["raw"]
    assert recovered["deepseek"]["q:1"]["raw"] != {"tampered": "not a model response"}
