"""Explicit reviewed import and auditable user confirmation, on synthetic data."""

import copy
from uuid import UUID

import pytest


def completed_request(context):
    value = copy.deepcopy(context["request"])
    value.update(
        text_source="reference",
        reference_preparation="auto",
        stop_after="completed",
        reuse_alignment_task_id=str(UUID(int=101)),
        reuse_assembly_task_id=str(UUID(int=102)),
        reuse_annotation_task_id=str(UUID(int=103)),
        sample_review={},
        reuse_full_annotation_task_id=str(UUID(int=104)),
        annotation_review={"decision": "approved"},
    )
    return value


@pytest.mark.parametrize(
    "missing",
    [
        "reuse_alignment_task_id",
        "reuse_assembly_task_id",
        "reuse_annotation_task_id",
        "reuse_full_annotation_task_id",
        "annotation_review",
    ],
)
def test_auto_import_requires_all_reviewed_sources(context, missing):
    from pydantic import ValidationError

    from app.schemas_processing import TaskRequest

    request = completed_request(context)
    request.pop(missing)
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(request)


def test_auto_import_rejects_changes_required(context):
    from pydantic import ValidationError

    from app.schemas_processing import TaskRequest

    request = completed_request(context)
    assert TaskRequest.model_validate(request).stop_after == "completed"
    request["annotation_review"]["decision"] = "changes_required"
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(request)


def audio_confirmation(context):
    return {
        "result_hash": context["result_hash"],
        "scope": "audio",
        "decision": "approved",
        "review_basis": "user_confirmation",
        "approval_reference": "synthetic:user-confirmation:test",
        "items": [
            {
                "entity_type": "audio",
                "src_id": "original",
                "verdict": "PASS",
                "file_hash": context["audio_hash"],
                "reference": "Synthetic explicit user approval, not real acceptance",
            }
        ],
        "evidence_refs": ["synthetic:test_full_pipeline.py"],
        "note": "Synthetic confirmation path; no numeric measurements",
    }


def test_user_confirmation_records_basis_without_fabricated_times(persisted, client):
    c = persisted
    url = f"/api/v1/admin/processing-tasks/{c['task_id']}"
    response = client.post(
        url + "/reviews", headers=c["headers"], json=audio_confirmation(c)
    )
    assert response.status_code == 200, response.text
    item = response.json()["data"]["items"][0]
    assert item["review_basis"] == "user_confirmation"
    assert item["approval_reference"] == "synthetic:user-confirmation:test"
    assert item["millisecond_measurement"] == "not_claimed"
    assert not any(k.startswith("reference_") for k in item)
    state = client.get(url, headers=c["headers"]).json()["data"]
    assert state["state"] == "awaiting_confirmation"  # Other reviews still required.
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import TranscriptSegment

    with SessionLocal() as db:
        segments = db.scalars(
            select(TranscriptSegment).where(TranscriptSegment.batch_id == c["batch_id"])
        ).all()
        assert all(s.review_status == "已通过" for s in segments)


@pytest.mark.parametrize(
    "mutation",
    [
        "no_source",
        "wrong_scope",
        "wrong_hash",
        "fake_measurement",
        "itemized_incomplete",
        "stale_result",
        "invalid_basis",
    ],
)
def test_audio_confirmation_does_not_bypass_review_contract(
    persisted, client, mutation
):
    c = persisted
    body = audio_confirmation(c)
    if mutation == "no_source":
        body.pop("approval_reference")
    elif mutation == "wrong_scope":
        body["scope"] = "content"
    elif mutation == "wrong_hash":
        body["items"][0]["file_hash"] = "0" * 64
    elif mutation == "fake_measurement":
        body["items"][0]["reference_start_ms"] = 0
    elif mutation == "itemized_incomplete":
        body["review_basis"] = "itemized"
    elif mutation == "stale_result":
        body["result_hash"] = "0" * 64
    else:
        body["review_basis"] = "auto_pass"
    response = client.post(
        f"/api/v1/admin/processing-tasks/{c['task_id']}/reviews",
        headers=c["headers"],
        json=body,
    )
    assert response.status_code == (409 if mutation == "stale_result" else 422)


@pytest.mark.parametrize(
    "mode", ["valid", "wrong_source", "missing_question", "conflict"]
)
def test_import_freezes_independent_count_before_hashing(context, monkeypatch, mode):
    from app.core.errors import AppError
    from app.db.base import SessionLocal
    from app.module3 import reuse
    from app.module3.contracts import fingerprint
    from app.schemas_processing import TaskRequest
    from app.services.processing import tasks

    request = completed_request(context)
    request.update(
        expected_question_count=None,
        expected_question_count_source=None,
        expected_question_ranges=[],
    )
    paper = context["materials"][0]
    structure = {
        "source": "original_paper_question_headings",
        "question_count": 1,
        "groups": [
            {
                "section": "synthetic",
                "start": 1,
                "end": 1,
                "source_sha256": paper["sha256"],
                "source_storage_key": paper["storage_key"],
                "source_page": 1,
            }
        ],
    }
    if mode == "wrong_source":
        structure["groups"][0]["source_sha256"] = "0" * 64
    elif mode == "missing_question":
        structure["groups"] = []
    elif mode == "conflict":
        request.update(
            expected_question_count=2,
            expected_question_count_source=context["request"][
                "expected_question_count_source"
            ],
            expected_question_ranges=[{"section": "synthetic", "start": 1, "end": 2}],
        )
    monkeypatch.setattr(
        reuse,
        "load",
        lambda *a: (
            {"reference": {"trusted_question_structure": structure}},
            {},
        ),
    )
    with SessionLocal() as db:
        if mode != "valid":
            with pytest.raises(AppError) as error:
                tasks.create_task(
                    db, TaskRequest.model_validate(request), 1, context["settings"]
                )
            assert error.value.status_code == 409
            return
        task = tasks.create_task(
            db, TaskRequest.model_validate(request), 1, context["settings"]
        )
        db.refresh(task)
        assert task.request["expected_question_count"] == 1
        assert (
            task.request["expected_question_count_source"]["sha256"] == paper["sha256"]
        )
        materials = tasks.task_materials(db, task.id)
        assert task.input_hash == fingerprint(
            {
                "request": {
                    k: v for k, v in task.request.items() if k != "material_ids"
                },
                "materials": sorted((m.source_kind, m.sha256) for m in materials),
                "method": task.method,
            }
        )


def test_speakers_survive_real_business_persistence(context, request):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import TranscriptSegment

    context["payload"]["transcript_segments"][0]["speaker"] = "M"
    context["payload"]["transcript_segments"][1]["speaker"] = "W"
    c = request.getfixturevalue("persisted")
    with SessionLocal() as db:
        rows = db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.batch_id == c["batch_id"])
            .order_by(TranscriptSegment.segment_index)
        ).all()
        assert [s.speaker_code for s in rows] == ["M", "W"]
