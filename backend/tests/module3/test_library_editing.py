"""Library transaction regressions in the disposable pytest database."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

P = "/api/v1/admin/listening-papers"
W = "/api/v1/admin/processing-workflows"
YEARS = count(2100)


@pytest.fixture
def library(client, admin_token):
    headers = {
        "Authorization": "Bearer " + admin_token,
        "Idempotency-Key": str(uuid4()),
    }
    payload = {
        "exam_level": "CET4",
        "exam_year": next(YEARS),
        "exam_month": 6,
        "paper_set": 1,
        "expected_question_count_source": "Synthetic 25-question paper; no real review",
    }
    response = client.post(P, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    result = response.json()["data"]["result"]
    result.update(headers=headers, create_payload=payload)
    return result


def draft(client, library):
    response = client.get(
        f"{W}/{library['workflow_id']}/edit-draft", headers=library["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def body_for(data, name="Synthetic passage"):
    snapshot = deepcopy(data["snapshot"])
    snapshot["passages"] = [{"_src_id": "passage-1", "topic": name}]
    return {
        "snapshot": snapshot,
        "expected_row_version": data["row_version"],
        "expected_content_hash": data["content_hash"],
        "reason": "Synthetic explicit save",
    }


def save(client, library, body, headers=None):
    return client.put(
        f"{W}/{library['workflow_id']}/edit-draft",
        headers=headers or {**library["headers"], "Idempotency-Key": str(uuid4())},
        json=body,
    )


def test_permission_pagination_and_manual_draft_visibility(
    client, library, student_token
):
    for suffix in ("", f"/{library['exam_paper_id']}/archive-preview"):
        method = client.post if suffix else client.get
        assert method(P + suffix).status_code == 401
        assert (
            method(
                P + suffix, headers={"Authorization": "Bearer " + student_token}
            ).status_code
            == 403
        )
    response = client.get(
        P,
        headers=library["headers"],
        params={"keyword": str(library["create_payload"]["exam_year"]), "page_size": 1},
    )
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["current_batch_id"] is None
    assert data["items"][0]["is_visible"] is False
    from app.db.base import SessionLocal
    from app.repositories.listening import student_access

    with SessionLocal() as db:
        assert not student_access(db, library["exam_paper_id"])[0]


def test_create_replay_and_identity_conflict(client, library):
    replay = client.post(P, headers=library["headers"], json=library["create_payload"])
    assert replay.status_code == 201
    assert replay.json()["data"]["result"]["exam_paper_id"] == library["exam_paper_id"]
    duplicate = client.post(
        P,
        headers={**library["headers"], "Idempotency-Key": str(uuid4())},
        json=library["create_payload"],
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error_code"] == "PAPER_IDENTITY_CONFLICT"


def test_explicit_save_replay_conflict_and_noop(client, library):
    initial = draft(client, library)
    body = body_for(initial)
    headers = {**library["headers"], "Idempotency-Key": str(uuid4())}
    first = save(client, library, body, headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["result"]["issues"]
    assert first.json()["data"]["result"]["version_no"] == 1
    assert save(client, library, body, headers).json() == first.json()
    assert (
        save(client, library, {**body, "reason": "different"}, headers).status_code
        == 409
    )
    assert save(client, library, body).status_code == 409
    current = draft(client, library)
    noop = save(client, library, body_for(current))
    assert noop.status_code == 200
    assert noop.json()["data"]["result"]["changed"] is False
    assert noop.json()["data"]["result"]["version_no"] == 1


def test_parallel_save_one_winner(client, library):
    body = body_for(draft(client, library))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(client, library, body), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]


def test_versions_restore_and_reconstruct(client, library):
    first = save(client, library, body_for(draft(client, library))).json()["data"][
        "result"
    ]
    second = save(client, library, body_for(draft(client, library), "Changed topic"))
    assert second.status_code == 200, second.text
    current = draft(client, library)
    body = {
        "source_version_id": first["save_version_id"],
        "expected_row_version": current["row_version"],
        "expected_content_hash": current["content_hash"],
        "reason": "Restore earlier topic",
    }
    url = f"{W}/{library['workflow_id']}"
    preview = client.post(
        url + "/restore-preview", headers=library["headers"], json=body
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["changes"]
    restored = client.post(url + "/restores", headers=library["headers"], json=body)
    assert restored.status_code == 200, restored.text
    assert draft(client, library)["version_no"] == 3
    from app.db.base import SessionLocal
    from app.services.processing import library_editing as service

    with SessionLocal() as db:
        _, _, head, version, snapshot = service.context(
            db, UUID(library["workflow_id"])
        )
        assert service.reconstruct(db, head, version) == snapshot


def test_seven_days_from_loss_of_previous_protection_and_prune(client, library):
    ids = []
    for i in range(5):
        result = save(client, library, body_for(draft(client, library), f"Topic {i}"))
        assert result.status_code == 200, result.text
        ids.append(UUID(result.json()["data"]["result"]["save_version_id"]))
    from app.db.base import SessionLocal
    from app.db.models_library import LibrarySaveVersion
    from app.services.processing.library_versions import prune

    with SessionLocal() as db:
        v3 = db.get(LibrarySaveVersion, ids[2])
        v5 = db.get(LibrarySaveVersion, ids[4])
        assert v3.unprotected_at == v5.saved_at
        assert (
            prune(
                db, ids[2], v5.saved_at + timedelta(days=7) - timedelta(microseconds=1)
            )
            == "skipped"
        )
        assert prune(db, ids[2], v5.saved_at + timedelta(days=7)) == "pruned"
        assert prune(db, ids[3], datetime.now(UTC) + timedelta(days=30)) == "skipped"
        assert prune(db, ids[2]) == "already_pruned"
    current = draft(client, library)
    response = client.post(
        f"{W}/{library['workflow_id']}/restore-preview",
        headers=library["headers"],
        json={
            "source_version_id": str(ids[2]),
            "expected_row_version": current["row_version"],
            "expected_content_hash": current["content_hash"],
            "reason": "Unavailable restore",
        },
    )
    assert response.status_code == 410


def test_archive_restore_never_opens_and_replay(client, library):
    url = f"{P}/{library['exam_paper_id']}"
    state = client.post(url + "/archive-preview", headers=library["headers"]).json()[
        "data"
    ]
    payload = {
        "expected_row_version": 1,
        "expected_content_hash": state["content_hash"],
        "reason": "Synthetic archive",
    }
    response = client.post(url + "/archive", headers=library["headers"], json=payload)
    assert response.status_code == 200, response.text
    assert (
        client.post(url + "/archive", headers=library["headers"], json=payload).json()
        == response.json()
    )
    blocked = save(client, library, body_for(draft(client, library)))
    assert blocked.status_code == 409
    state = client.post(url + "/archive-preview", headers=library["headers"]).json()[
        "data"
    ]
    restored = client.post(
        url + "/restore",
        headers=library["headers"],
        json={
            "expected_row_version": 2,
            "expected_content_hash": state["content_hash"],
            "reason": "Restore",
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["result"]["is_visible"] is False


def test_cross_paper_restore_rejected(client, library, admin_token):
    source = save(client, library, body_for(draft(client, library))).json()["data"][
        "result"
    ]
    second = {**library["create_payload"], "exam_year": next(YEARS)}
    response = client.post(
        P, headers={**library["headers"], "Idempotency-Key": str(uuid4())}, json=second
    )
    other = {**response.json()["data"]["result"], "headers": library["headers"]}
    current = draft(client, other)
    request = {
        "source_version_id": source["save_version_id"],
        "expected_row_version": current["row_version"],
        "expected_content_hash": current["content_hash"],
        "reason": "Cross-paper forbidden",
    }
    assert (
        client.post(
            f"{W}/{other['workflow_id']}/restore-preview",
            headers=library["headers"],
            json=request,
        ).status_code
        == 404
    )


def test_snapshot_and_audit_are_immutable_in_database(client, library):
    result = save(client, library, body_for(draft(client, library))).json()["data"][
        "result"
    ]
    from app.db.base import SessionLocal

    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            db.execute(
                text("UPDATE library_save_versions SET reason='forged' WHERE id=:id"),
                {"id": result["save_version_id"]},
            )
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(
                text("DELETE FROM library_edit_changes WHERE save_version_id=:id"),
                {"id": result["save_version_id"]},
            )
        db.rollback()


def test_metadata_forgery_and_dangling_reference_rejected(client, library):
    initial = draft(client, library)
    body = body_for(initial)
    body["snapshot"]["generation_receipts"] = [{"fake": True}]
    assert save(client, library, body).status_code == 422
    body = body_for(initial)
    body["snapshot"]["questions"] = [
        {"_src_id": "q-1", "passage_src_id": "foreign-passage"}
    ]
    assert save(client, library, body).status_code == 422


def test_legacy_paper_opens_one_edit_head_without_changing_formal_batch(
    client, admin_token
):
    from app.db.base import SessionLocal
    from app.db.models_listening import (
        ExamPaper,
        ImportBatch,
        Passage,
        Presentation,
        Question,
    )

    with SessionLocal() as db:
        paper = ExamPaper(
            exam_paper_code="LEGACY_" + uuid4().hex[:16],
            exam_level="CET6",
            exam_year=next(YEARS),
            exam_month=6,
            paper_set=1,
            expected_question_count=25,
            expected_question_count_source={"locator": "Synthetic legacy source"},
            review_status="已通过",
        )
        db.add(paper)
        db.flush()
        batch = ImportBatch(
            exam_paper_id=paper.id,
            batch_code="LEGACY_" + uuid4().hex[:16],
            status="active",
            is_current=True,
        )
        db.add(batch)
        db.flush()
        passage = Passage(
            batch_id=batch.id,
            exam_paper_id=paper.id,
            passage_code="LEGACY_P",
            passage_index=1,
            start_ms=0,
            body_end_ms=3000,
            end_ms=5000,
        )
        db.add(passage)
        db.flush()
        for number in range(1, 26):
            question = Question(
                batch_id=batch.id,
                passage_id=passage.id,
                question_code=f"LEGACY_Q{number}",
                question_index=number,
                question_text="Synthetic original question",
                option_a="Alpha",
                option_b="Beta",
                option_c="Gamma",
                option_d="Delta",
                correct_option="A",
                explanation_text="Synthetic legacy explanation",
                explanation_source="Synthetic original source",
            )
            db.add(question)
            db.flush()
            db.add(
                Presentation(
                    batch_id=batch.id,
                    exam_paper_id=paper.id,
                    question_id=question.id,
                    question_no=number,
                    option_mapping_state="已知",
                    option_letter_mapping=dict(zip("ABCD", "ABCD", strict=True)),
                )
            )
        db.commit()
        paper_id, batch_id = paper.id, batch.id
    headers = {
        "Authorization": "Bearer " + admin_token,
        "Idempotency-Key": str(uuid4()),
    }
    opened = client.post(
        f"{P}/{paper_id}/edit-draft",
        headers=headers,
        json={"expected_row_version": 1, "reason": "Edit synthetic legacy paper"},
    )
    assert opened.status_code == 200, opened.text
    workflow_id = opened.json()["data"]["workflow_id"]
    current = draft(client, {"workflow_id": workflow_id, "headers": headers})
    assert len(current["snapshot"]["questions"]) == 25
    assert current["issues"]
    reopened = client.post(
        f"{P}/{paper_id}/edit-draft",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_row_version": 2,
            "reason": "Second administrator opens shared head",
        },
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["data"]["workflow_id"] == workflow_id
    with SessionLocal() as db:
        assert db.get(ImportBatch, batch_id).is_current is True
        assert db.get(ExamPaper, paper_id).review_status == "已通过"
