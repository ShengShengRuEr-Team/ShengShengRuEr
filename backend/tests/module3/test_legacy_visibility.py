"""Synthetic historical records; never a substitute for real material review."""

import copy
from uuid import UUID

import pytest

from tests.module3.test_processing import approve_fixture


@pytest.fixture
def historical(persisted, client):
    """Model a batch imported/reviewed by the pre-V7 deployment in the test DB."""
    from sqlalchemy import update

    from app.db.base import SessionLocal
    from app.db.models_listening import ContentCheck, ImportBatch
    from app.db.models_processing import ProcessingReview
    from app.module3.contracts import result_hash
    from app.schemas_processing import ActivationRequest
    from app.services.processing import tasks

    c = persisted
    check = approve_fixture(client, c)
    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(c["task_id"]))
        tasks.activate(
            db,
            c["paper_id"],
            ActivationRequest(
                task_id=task.id,
                batch_id=c["batch_id"],
                check_id=check["id"],
                result_hash=c["result_hash"],
                expected_current_batch_id=None,
            ),
            task.created_by,
        )
        # Test-only legacy fixture loading, after the synthetic V1 import.
        # Keep auto_draft immutable; change no workflow or approved review session.
        draft = tasks.get_draft(db, task)
        payload = copy.deepcopy(draft.payload)
        payload.update(
            schema_version="m3.v2",
            rules_manifest={"error_rule_version": "m3.option-errors.v1"},
        )
        digest = result_hash(payload)
        draft.payload, draft.result_hash = payload, digest
        task.result_hash = digest
        db.get(ImportBatch, c["batch_id"]).result_hash = digest
        db.get(ContentCheck, check["id"]).result_hash = digest
        db.execute(
            update(ProcessingReview)
            .where(ProcessingReview.task_id == task.id)
            .values(result_hash=digest)
        )
        db.commit()
    return {**c, "payload": payload, "result_hash": digest}


def test_legacy_visibility_cancel_reopen(historical, client, student_token):
    c = historical
    url = f"/api/v1/admin/listening-papers/{c['paper_id']}/visibility"
    student_url = f"/api/v1/listening-papers/{c['paper_id']}"
    student = {"Authorization": "Bearer " + student_token}
    for action, status in (("confirm", 200), ("cancel", 404), ("confirm", 200)):
        response = client.post(
            url,
            headers=c["headers"],
            json={"expected_batch_id": c["batch_id"], "action": action},
        )
        assert response.status_code == 200, response.text
        result = client.get(student_url, headers=student)
        assert result.status_code == status, result.text
        if status == 200:
            assert '"correct_option"' not in result.text


@pytest.mark.parametrize(
    "fault,kind",
    [
        ("missing_review", "module3_reviews_missing"),
        ("wrong_review_hash", "module3_reviews_missing"),
        ("draft_hash", "module3_result_hash_mismatch"),
        ("payload", "module3_result_hash_mismatch"),
        ("audio", "audio_hash_mismatch"),
        ("question", "option_empty"),
        ("pending", "distractor_assessment_missing"),
        ("v3", "distractor_assessment_missing"),
        ("v2_new_rules", "distractor_assessment_missing"),
    ],
)
def test_legacy_recheck_keeps_safety_gates(historical, fault, kind):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_listening import AudioFile, ExamPaper, ImportBatch, Question
    from app.module3.contracts import result_hash
    from app.services import content_check
    from app.services.processing import tasks

    c = historical
    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(c["task_id"]))
        draft = tasks.get_draft(db, task)
        batch = db.get(ImportBatch, c["batch_id"])
        reviews = tasks.latest_reviews(db, task)
        if fault == "missing_review":
            reviews["audio"].decision = "changes_required"
        elif fault == "wrong_review_hash":
            reviews["audio"].result_hash = "0" * 64
        elif fault == "draft_hash":
            draft.result_hash = "0" * 64
        elif fault == "payload":
            payload = copy.deepcopy(draft.payload)
            payload["questions"][0]["explanation_text"] += " changed"
            draft.payload = payload
        elif fault == "audio":
            audio = db.get(AudioFile, batch.audio_id)
            (c["settings"].audio_storage_path / audio.storage_key).write_bytes(b"bad")
        elif fault == "question":
            question = db.scalar(select(Question).where(Question.batch_id == batch.id))
            question.option_a = ""
        elif fault == "pending":
            batch.status, batch.is_current = "pending", False
        elif fault in {"v3", "v2_new_rules"}:
            payload = copy.deepcopy(draft.payload)
            payload["schema_version"] = "m3.v3" if fault == "v3" else "m3.v2"
            payload["rules_manifest"]["error_rule_version"] = "m3.option-errors.v2"
            digest = result_hash(payload)
            draft.payload, draft.result_hash = payload, digest
            task.result_hash = batch.result_hash = digest
            for review in reviews.values():
                review.result_hash = digest
        db.flush()
        check = content_check.run_check(
            db,
            db.get(ExamPaper, c["paper_id"]),
            batch,
            c["settings"].audio_storage_path,
        )
        assert not check.is_passed
        assert kind in {issue["kind"] for issue in check.issues}


def test_new_validation_cannot_use_legacy_empty_as_v7(context):
    from app.services.processing.validation import validate_result

    payload = context["clone"]()
    payload["schema_version"] = "m3.v2"
    issues = validate_result(payload, context["request"])
    assert "distractor_assessment_missing" in {issue["kind"] for issue in issues}


def test_legacy_contract_still_rejects_correct_option_candidate(context):
    from app.services.processing.validation import validate_result

    payload = context["clone"]()
    payload["schema_version"] = "m3.v2"
    payload["rules_manifest"] = {"error_rule_version": "m3.option-errors.v1"}
    payload["error_question_relations"] = [
        {
            "_src_id": "error:1",
            "relation_kind": "QUESTION_ERROR_CANDIDATE",
            "question_src_id": "q:1",
            "option_letter": "A",
            "error_cause_code": "E4.3",
            "rule_version": "m3.option-errors.v1",
            "business_eligible": True,
        }
    ]
    issues = validate_result(payload, context["request"], allow_legacy_annotations=True)
    assert "option_error_invalid" in {issue["kind"] for issue in issues}
