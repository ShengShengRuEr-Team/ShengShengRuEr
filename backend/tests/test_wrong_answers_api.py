"""Notebook coverage through the student submission and review APIs."""

from uuid import uuid4

import pytest

from tests.attempt_support import create_student, create_visible_paper, set_visibility
from tests.conftest import auth_headers, login

NOTEBOOK = "/api/v1/wrong-answers"


def _student_headers(client):
    username = f"notebook_{uuid4().hex[:12]}"
    create_student(username)
    return auth_headers(login(client, username, "attempt123"))


def _assert_no_store(response, status_code):
    assert response.status_code == status_code, response.text
    assert response.headers["Cache-Control"] == "no-store"


@pytest.fixture
def submitted_paper(client):
    paper = create_visible_paper(
        code=f"NOTEBOOK_{uuid4().hex[:12]}", correct_letters=("A", "B", "C")
    )
    student = _student_headers(client)
    submit_url = f"/api/v1/listening-papers/{paper.paper_id}/attempts"
    headers = {**student, "Idempotency-Key": str(uuid4())}
    payload = {
        "loaded_question_ids": list(paper.question_ids),
        "answers": [
            {"question_id": paper.question_ids[0], "selected_option": "B"},
            {"question_id": paper.question_ids[1], "selected_option": "B"},
        ],
    }
    response = client.post(submit_url, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["correct_count"] == 1
    return paper, student, summary


def test_notebook_list_filters_and_private_gates(client, admin_token, submitted_paper):
    paper, student, summary = submitted_paper
    entry_url = f"{NOTEBOOK}/{summary['attempt_code']}/1"
    admin = auth_headers(admin_token)
    other = _student_headers(client)

    _assert_no_store(client.get(NOTEBOOK), 401)
    _assert_no_store(client.get(NOTEBOOK, headers=admin), 403)
    _assert_no_store(client.get(entry_url), 401)
    _assert_no_store(client.get(entry_url, headers=admin), 403)
    _assert_no_store(
        client.patch(entry_url, headers=admin, json={"learning_status": "mastered"}),
        403,
    )

    response = client.get(NOTEBOOK, headers=student, params={"limit": 1, "page": 2})
    _assert_no_store(response, 200)
    page = response.json()["data"]
    assert page["total"] == 2
    assert page["state_writes_enabled"] is False
    (unanswered,) = page["items"]
    assert unanswered["exam_paper_id"] == paper.paper_id
    assert unanswered["question_no"] == 3 and unanswered["selected_option"] is None
    assert unanswered["learning_status"] == "pending"
    assert unanswered["is_hidden"] is False
    assert unanswered["reviewed_at"] is None
    assert {
        "correct_option",
        "explanation_text",
        "audio_url",
        "transcript",
        "options",
    }.isdisjoint(unanswered)

    filtered = client.get(
        NOTEBOOK,
        headers=student,
        params={
            "exam_paper_id": paper.paper_id,
            "answer_type": "incorrect",
            "learning_status": "pending",
        },
    ).json()["data"]
    assert filtered["total"] == 1 and filtered["items"][0]["question_no"] == 1
    only_unanswered = client.get(
        NOTEBOOK, headers=student, params={"answer_type": "unanswered"}
    ).json()["data"]
    assert only_unanswered["total"] == 1
    assert only_unanswered["items"][0] == unanswered
    other_paper = create_visible_paper(code=f"NOTEBOOK_OTHER_{uuid4().hex[:12]}")
    filtered = client.get(
        NOTEBOOK, headers=student, params={"exam_paper_id": other_paper.paper_id}
    ).json()["data"]
    assert filtered["total"] == 0
    assert client.get(NOTEBOOK, headers=other).json()["data"]["total"] == 0
    _assert_no_store(client.get(entry_url, headers=other), 404)
    _assert_no_store(
        client.patch(entry_url, headers=other, json={"is_hidden": True}), 404
    )
    _assert_no_store(
        client.get(f"{NOTEBOOK}/{summary['attempt_code']}/2", headers=student), 404
    )

    unavailable = client.get(entry_url, headers=student)
    _assert_no_store(unavailable, 503)
    assert unavailable.json()["msg"] == "错题详情暂未开放"
    assert unavailable.json()["data"] is None
    unavailable = client.patch(
        entry_url, headers=student, json={"learning_status": "mastered"}
    )
    _assert_no_store(unavailable, 503)
    assert unavailable.json()["msg"] == "错题管理暂未开放"
    assert unavailable.json()["data"] is None

    set_visibility(paper.paper_id, False)
    assert client.get(NOTEBOOK, headers=student).json()["data"]["total"] == 0
    _assert_no_store(client.get(entry_url, headers=student), 404)
    _assert_no_store(
        client.patch(entry_url, headers=student, json={"is_hidden": True}), 404
    )


def test_review_status_hide_and_restore_preserve_submission(
    client, monkeypatch, submitted_paper
):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "wrong_answers_state_writes_enabled", True)
    paper, student, summary = submitted_paper
    attempt_code = summary["attempt_code"]
    entry_url = f"{NOTEBOOK}/{attempt_code}/1"
    assert client.get(NOTEBOOK, headers=student).json()["data"]["state_writes_enabled"]
    _assert_no_store(client.get(entry_url, headers=student), 503)
    _assert_no_store(client.patch(entry_url, headers=student, json={}), 422)

    mastered = client.patch(
        entry_url, headers=student, json={"learning_status": "mastered"}
    )
    _assert_no_store(mastered, 200)
    mastered_item = mastered.json()["data"]
    assert mastered_item["learning_status"] == "mastered"
    assert mastered_item["reviewed_at"] is not None
    repeated = client.patch(
        entry_url, headers=student, json={"learning_status": "mastered"}
    )
    assert repeated.json()["data"] == mastered_item
    assert client.get(
        NOTEBOOK, headers=student, params={"learning_status": "mastered"}
    ).json()["data"]["items"] == [mastered_item]

    for _ in range(2):
        hidden = client.patch(entry_url, headers=student, json={"is_hidden": True})
        _assert_no_store(hidden, 200)
        hidden_item = hidden.json()["data"]
        assert hidden_item["is_hidden"] is True
        assert hidden_item["learning_status"] == "mastered"
        assert hidden_item["reviewed_at"] == mastered_item["reviewed_at"]
    assert client.get(NOTEBOOK, headers=student).json()["data"]["total"] == 1
    assert client.get(
        NOTEBOOK, headers=student, params={"visibility": "hidden"}
    ).json()["data"]["items"] == [hidden_item]
    _assert_no_store(client.get(entry_url, headers=student), 404)

    set_visibility(paper.paper_id, False)
    assert (
        client.get(NOTEBOOK, headers=student, params={"visibility": "hidden"}).json()[
            "data"
        ]["total"]
        == 0
    )
    _assert_no_store(
        client.patch(entry_url, headers=student, json={"is_hidden": False}), 404
    )
    set_visibility(paper.paper_id, True)

    restored = client.patch(entry_url, headers=student, json={"is_hidden": False})
    _assert_no_store(restored, 200)
    assert restored.json()["data"] == mastered_item
    assert (
        client.get(NOTEBOOK, headers=student, params={"visibility": "hidden"}).json()[
            "data"
        ]["total"]
        == 0
    )

    pending = client.patch(
        entry_url, headers=student, json={"learning_status": "pending"}
    )
    _assert_no_store(pending, 200)
    assert pending.json()["data"]["learning_status"] == "pending"
    assert client.get(NOTEBOOK, headers=student).json()["data"]["total"] == 2

    status = client.get(
        f"/api/v1/listening-papers/{paper.paper_id}/attempt-status", headers=student
    )
    assert status.json()["data"]["latest_attempt"] == summary


def test_opted_in_detail_preserves_snapshot_and_reuses_current_audio(
    client, monkeypatch, submitted_paper
):
    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_listening import (
        ExamPaper,
        ImportBatch,
        Question,
        TranscriptSegment,
    )
    from tests.attempt_support import _add_batch

    monkeypatch.setattr(get_settings(), "wrong_answers_protected_details_enabled", True)
    paper, student, summary = submitted_paper
    attempt_code = summary["attempt_code"]
    question_no = 1
    entry_url = f"{NOTEBOOK}/{attempt_code}/{question_no}"

    with SessionLocal() as db:
        question = db.get(Question, paper.question_ids[0])
        db.add(
            TranscriptSegment(
                batch_id=paper.batch_id,
                passage_id=question.passage_id,
                segment_index=1,
                segment_type="body",
                text="Protected transcript content.",
                start_ms=0,
                end_ms=1000,
            )
        )
        original_batch = db.get(ImportBatch, paper.batch_id)
        original_batch.is_current = False
        db.flush()
        current_batch, new_questions = _add_batch(
            db,
            paper=db.get(ExamPaper, paper.paper_id),
            batch_code=f"NOTEBOOK_SWITCH_{uuid4().hex[:12]}",
            current=True,
            correct_letters=("D", "B", "C"),
        )
        new_question = db.get(Question, new_questions[0])
        new_question.question_text = "Edited question"
        new_question.explanation_text = "Edited explanation"
        db.commit()
        current_batch_id = current_batch.id

    response = client.get(entry_url, headers=student)
    _assert_no_store(response, 200)
    detail = response.json()["data"]
    assert detail["question_text"] == "Question 1?"
    assert detail["selected_option"] == "B" and detail["correct_option"] == "A"
    assert detail["explanation_text"] == "测试解析"
    assert detail["snapshot_note"]
    assert detail["personal_cause_status"] == "unconfirmed"
    assert detail["skills"] == detail["candidate_causes"] == []
    assert "transcript" not in detail
    assert "Protected transcript content." not in response.text

    audio_url = detail["audio_url"]
    assert audio_url == (
        f"/api/v1/listening-papers/{paper.paper_id}/audio"
        f"?expected_batch_id={current_batch_id}"
    )
    audio = client.get(audio_url, headers={**student, "Range": "bytes=0-3"})
    assert audio.status_code == 206 and audio.content == b"ssre"
    _assert_no_store(
        client.patch(entry_url, headers=student, json={"is_hidden": True}), 503
    )

    set_visibility(paper.paper_id, False)
    _assert_no_store(client.get(entry_url, headers=student), 404)
    assert client.get(audio_url, headers=student).status_code == 404
    assert client.get(NOTEBOOK, headers=student).json()["data"]["total"] == 0
