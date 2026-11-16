"""Technical scenarios use synthetic fixtures and real isolated PostgreSQL/HTTP."""

import copy
from uuid import UUID

import pytest


def test_a01_duplicate_material_and_persistent_task(context, client):
    c = context
    response = client.get(
        f"/api/v1/admin/materials/{c['materials'][0]['id']}", headers=c["headers"]
    )
    assert response.status_code == 200
    assert response.json()["data"]["sha256"] == c["materials"][0]["sha256"]
    task = client.get(
        f"/api/v1/admin/processing-tasks/{c['task_id']}", headers=c["headers"]
    ).json()["data"]
    assert task["state"] == "pending" and task["batch_id"] is None
    assert "lease_token" not in task


@pytest.mark.parametrize(
    "key",
    [
        "../x.pdf",
        "D:/x.pdf",
        "//server/x.pdf",
        "x.pdf:secret",
        "sub/../x.pdf",
        "file. ",
    ],
)
def test_a02_path_escape_rejected(context, client, key):
    c = context
    request = {
        "exam_paper_code": c["request"]["exam_paper"]["exam_paper_code"],
        "source_kind": "paper_text",
        "storage_key": key,
        "expected_sha256": "0" * 64,
        "source_locator": "test",
    }
    assert (
        client.post(
            "/api/v1/admin/materials", json=request, headers=c["headers"]
        ).status_code
        == 422
    )


def test_a02_changed_source_does_not_start(context, client):
    context["paper"].write_bytes(b"%PDF-1.4\nchanged")
    response = client.post(
        "/api/v1/admin/processing-tasks",
        json=context["request"],
        headers=context["headers"],
    )
    assert (
        response.status_code == 422
        and response.json()["data"]["issue_code"] == "SOURCE_CHANGED"
    )


def test_a03_authentication_and_student_forbidden(context, client, student_token):
    url = f"/api/v1/admin/processing-tasks/{context['task_id']}"
    assert client.get(url).status_code == 401
    assert (
        client.get(
            url, headers={"Authorization": "Bearer " + student_token}
        ).status_code
        == 403
    )


def test_a04_missing_material_waits(context, client):
    req = copy.deepcopy(context["request"])
    req["material_ids"] = req["material_ids"][:1]
    response = client.post(
        "/api/v1/admin/processing-tasks", json=req, headers=context["headers"]
    )
    assert response.status_code == 202
    assert response.json()["data"]["state"] == "awaiting_confirmation"


def test_a06_a07_lease_loss_and_stale_write(context):
    from datetime import timedelta

    from app.db.base import SessionLocal
    from app.module3.contracts import ProcessingError
    from app.services.processing import tasks

    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(context["task_id"]), lock=True)
        task.state = "running"
        task.lease_token = UUID(int=13)
        task.expires_at = tasks.utcnow() - timedelta(seconds=1)
        db.commit()
        assert tasks.expire_leases(db) >= 1
        db.commit()
        with pytest.raises(ProcessingError, match="worker"):
            tasks.fenced_task(db, task.id, UUID(int=13))
        db.rollback()
        task = tasks.get_task(db, task.id)
        assert task.state == "failed" and task.issues[-1]["issue_code"] == "WORKER_LOST"


@pytest.mark.parametrize(
    "change,code",
    [
        ("count", "QUESTION_COUNT_MISMATCH"),
        ("mapping", "OPTION_MAPPING_INVALID"),
        ("quote", "EVIDENCE_QUOTE_INVALID"),
        ("question_evidence", "EVIDENCE_INVALID"),
        ("skill", "SKILL_INVALID"),
        ("skill_evidence", "SKILL_EVIDENCE_MISSING"),
        ("answer_evidence", "ANSWER_EVIDENCE_MISSING"),
        ("alignment", "ALIGNMENT_UNVERIFIED"),
        ("duplicate", "SRC_ID_DUPLICATE"),
    ],
)
def test_a09_a10_a15_a18_a19_a22_reject_invalid_results(context, change, code):
    from app.services.processing.validation import validate_result

    p = context["clone"]()
    if change == "count":
        p["questions"] = []
    if change == "mapping":
        p["presentations"][0]["option_letter_mapping"]["A"] = "Z"
    if change == "quote":
        p["evidences"][0]["evidence_text"] = "Invented quote."
    if change == "question_evidence":
        p["evidences"][0]["segment_src_ids"] = ["s:2"]
    if change == "skill":
        p["skill_question_relations"][0]["skill_code"] = "FAKE"
    if change == "skill_evidence":
        p["skill_question_relations"].pop()
    if change == "answer_evidence":
        p["other_relations"] = []
    if change == "alignment":
        p["transcript_segments"][0]["alignment_status"] = "interpolated"
    if change == "duplicate":
        p["questions"].append(copy.deepcopy(p["questions"][0]))
    assert code in {i["issue_code"] for i in validate_result(p, context["request"])}


def test_a20_a25_pending_business_rows_not_current(persisted, client):
    from app.db.base import SessionLocal
    from app.db.models_listening import ExamPaper, ImportBatch

    c = persisted
    with SessionLocal() as db:
        batch = db.get(ImportBatch, c["batch_id"])
        paper = db.get(ExamPaper, c["paper_id"])
        assert batch.status == "pending" and not batch.is_current
        assert paper.playback_audio_id is None
    assert (
        client.get(
            f"/api/v1/listening-papers/{c['paper_id']}", headers=c["headers"]
        ).status_code
        == 404
    )


def approve_fixture(client, c):
    url = f"/api/v1/admin/processing-tasks/{c['task_id']}"
    response = client.post(
        url + "/checks",
        json={"expected_result_hash": c["result_hash"]},
        headers=c["headers"],
    )
    assert response.status_code == 200, response.text
    check = response.json()["data"]
    assert check["is_passed"], check["issues"]
    for scope in ("content", "audio", "annotations"):
        payload = c["payload"]
        if scope == "content":
            items = [
                {"entity_type": "questions", "src_id": q["_src_id"]}
                for q in payload["questions"]
            ]
        elif scope == "audio":
            items = [
                {
                    "entity_type": "transcript_segments",
                    "src_id": s["_src_id"],
                    "reference_start_ms": s["start_ms"],
                    "reference_end_ms": s["end_ms"],
                }
                for s in payload["transcript_segments"]
                if s["segment_type"] == "body"
            ]
            items.append(
                {
                    "entity_type": "audio",
                    "src_id": "original",
                    "file_hash": payload["audio"]["file_hash"],
                    "listened_to_end": True,
                }
            )
        else:
            items = [
                {"entity_type": section, "src_id": row["_src_id"]}
                for section in (
                    "skill_question_relations",
                    "error_question_relations",
                    "other_relations",
                )
                for row in payload.get(section, [])
            ]
        for item in items:
            item.update(
                verdict="PASS",
                reference="known synthetic fixture, not real listening acceptance",
            )
        r = client.post(
            url + "/reviews",
            headers=c["headers"],
            json={
                "result_hash": c["result_hash"],
                "scope": scope,
                "decision": "approved",
                "items": items,
                "evidence_refs": ["synthetic:test_processing.py"],
                "note": "Synthetic technical test; separate from content acceptance",
            },
        )
        assert r.status_code == 200, r.text
    return check


def test_a26_a27_a36_activation_review_gate_and_replay(
    persisted, client, student_token
):
    c = persisted
    url = f"/api/v1/admin/listening-papers/{c['paper_id']}/current-batch"
    body = {
        "task_id": c["task_id"],
        "batch_id": c["batch_id"],
        "check_id": 1,
        "result_hash": c["result_hash"],
        "expected_current_batch_id": None,
    }
    assert client.post(url, json=body, headers=c["headers"]).status_code == 409
    check = approve_fixture(client, c)
    body["check_id"] = check["id"]
    response = client.post(url, json=body, headers=c["headers"])
    assert (
        response.status_code == 200 and response.json()["data"]["is_visible"] is False
    )
    visible = f"/api/v1/admin/listening-papers/{c['paper_id']}/visibility"
    assert (
        client.post(
            visible,
            json={"action": "confirm", "reason": "synthetic technical test"},
            headers=c["headers"],
        ).status_code
        == 200
    )
    repeat = client.post(url, json=body, headers=c["headers"])
    assert repeat.json()["data"]["is_visible"] is True
    student = {"Authorization": "Bearer " + student_token}
    response = client.get(f"/api/v1/listening-papers/{c['paper_id']}", headers=student)
    assert response.status_code == 200
    assert (
        '"correct_option"' not in response.text
        and "explanation_text" not in response.text
    )
    assert (
        client.post(
            visible,
            json={"action": "cancel", "reason": "synthetic"},
            headers=c["headers"],
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/listening-papers/{c['paper_id']}", headers=student
        ).status_code
        == 404
    )


def test_a32_correction_keeps_auto_draft_immutable(persisted, client):
    c = persisted
    url = f"/api/v1/admin/processing-tasks/{c['task_id']}"
    before = client.get(url + "/result?view=auto_draft", headers=c["headers"]).json()[
        "data"
    ]
    r = client.post(
        url + "/corrections",
        headers=c["headers"],
        json={
            "expected_result_hash": c["result_hash"],
            "reason": "synthetic typo fix",
            "source_refs": ["synthetic reference"],
            "changes": [
                {
                    "entity": "questions",
                    "src_id": "q:1",
                    "field": "explanation_text",
                    "value": "Corrected synthetic explanation",
                }
            ],
        },
    )
    assert r.status_code == 202, r.text
    assert r.json()["data"]["result_hash"] != c["result_hash"]
    after = client.get(url + "/result?view=auto_draft", headers=c["headers"]).json()[
        "data"
    ]
    assert before == after
