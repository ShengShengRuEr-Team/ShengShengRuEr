"""Notebook integration through the student submission and review APIs."""

from uuid import uuid4

from tests.attempt_support import create_student, create_visible_paper, set_visibility
from tests.conftest import auth_headers, login

NOTEBOOK = "/api/v1/wrong-answers"


def test_wrong_answers_are_owned_reviewable_and_independently_removable(
    client, admin_token
):
    from app.db.base import SessionLocal
    from app.db.models_listening import Question, TranscriptSegment

    paper = create_visible_paper(code="NOTEBOOK_TEST", correct_letters=("A", "B", "C"))
    username = "notebook_student_a"
    create_student(username)
    student = auth_headers(login(client, username, "attempt123"))
    assert client.get(NOTEBOOK).status_code == 401
    assert client.get(NOTEBOOK, headers=auth_headers(admin_token)).status_code == 403

    with SessionLocal() as db:
        question = db.get(Question, paper.question_ids[0])
        db.add(
            TranscriptSegment(
                batch_id=paper.batch_id,
                passage_id=question.passage_id,
                segment_index=1,
                segment_type="body",
                text="Original listening transcript.",
                start_ms=0,
                end_ms=1000,
            )
        )
        db.commit()

    submit_url = f"/api/v1/listening-papers/{paper.paper_id}/attempts"
    response = client.post(
        submit_url,
        headers={**student, "Idempotency-Key": str(uuid4())},
        json={
            "loaded_question_ids": list(paper.question_ids),
            "answers": [
                {"question_id": paper.question_ids[0], "selected_option": "B"},
                {"question_id": paper.question_ids[1], "selected_option": "B"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["correct_count"] == 1

    answer_url = f"{NOTEBOOK}/{summary['attempt_code']}"
    response = client.get(NOTEBOOK, headers=student, params={"limit": 1, "page": 2})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 2
    assert response.json()["data"]["items"][0]["question_no"] == 3
    filtered = client.get(NOTEBOOK, headers=student, params={"keyword": "question 1"})
    assert filtered.json()["data"]["total"] == 1
    assert client.get(f"{answer_url}/2", headers=student).status_code == 404

    set_visibility(paper.paper_id, False)
    response = client.get(f"{answer_url}/1", headers=student)
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert detail["selected_option"] == "B"
    assert detail["correct_option"] == "A"
    assert detail["explanation_text"] == "测试解析"
    assert detail["transcript"] == ["Original listening transcript."]
    assert detail["personal_cause_status"] == "unconfirmed"
    assert detail["candidate_causes"] == []

    other_user = "notebook_student_b"
    create_student(other_user)
    other = auth_headers(login(client, other_user, "attempt123"))
    assert client.get(NOTEBOOK, headers=other).json()["data"]["total"] == 0
    assert client.get(f"{answer_url}/1", headers=other).status_code == 404
    assert client.get(detail["audio_url"], headers=other).status_code == 404
    assert client.delete(f"{answer_url}/1", headers=other).status_code == 404

    audio = client.get(detail["audio_url"], headers={**student, "Range": "bytes=0-3"})
    assert audio.status_code == 206
    assert audio.content == b"ssre"

    assert client.delete(f"{answer_url}/1", headers=student).status_code == 200
    assert client.delete(f"{answer_url}/1", headers=student).status_code == 200
    assert client.get(f"{answer_url}/1", headers=student).status_code == 404
    assert client.get(detail["audio_url"], headers=student).status_code == 404
    assert client.get(NOTEBOOK, headers=student).json()["data"]["total"] == 1
    set_visibility(paper.paper_id, True)
    status = client.get(
        f"/api/v1/listening-papers/{paper.paper_id}/attempt-status", headers=student
    )
    assert status.json()["data"]["latest_attempt"] == summary
