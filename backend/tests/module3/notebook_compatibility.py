"""Notebook assertions against published synthetic MANUAL/MIXED library batches."""

from uuid import uuid4

from sqlalchemy import select


def assert_notebook_supplements(client, context, monkeypatch):
    from app.core.config import get_settings
    from app.db.base import SessionLocal
    from app.db.models_attempt import Attempt, AttemptAnswer
    from app.db.models_listening import AudioFile, ExamPaper, ImportBatch, Question
    from tests.attempt_support import _add_batch, create_student
    from tests.conftest import login

    monkeypatch.setattr(get_settings(), "wrong_answers_protected_details_enabled", True)
    detail = context["detail"]()
    pid, batch = detail["exam_paper_id"], detail["current_batch_id"]
    opened = client.post(
        f"/api/v1/admin/listening-papers/{pid}/visibility",
        headers=context["headers"],
        json={"action": "confirm", "expected_batch_id": batch},
    )
    assert opened.status_code == 200, opened.text
    username = "compat_" + uuid4().hex[:12]
    create_student(username)
    headers = {"Authorization": "Bearer " + login(client, username, "attempt123")}
    paper = client.get(f"/api/v1/listening-papers/{pid}", headers=headers).json()[
        "data"
    ]
    questions = [q for passage in paper["passages"] for q in passage["questions"]]
    submitted = client.post(
        f"/api/v1/listening-papers/{pid}/attempts",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "loaded_question_ids": [q["question_id"] for q in questions],
            "answers": [
                {"question_id": questions[0]["question_id"], "selected_option": "A"}
            ],
        },
    )
    assert submitted.status_code == 200, submitted.text
    code = submitted.json()["data"]["attempt_code"]
    url = f"/api/v1/wrong-answers/{code}/1"
    current = client.get(url, headers=headers).json()["data"]
    assert current["skills"] and current["candidate_causes"]
    assert current["candidate_causes"][0]["option_letter"] == "A"
    assert current["correct_option"] == "D"
    assert current["review_materials_source"] == "submission_batch"
    fields = [
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_option",
        "selected_option",
        "explanation_text",
        "is_correct",
    ]
    with SessionLocal() as db:
        attempt = db.scalar(select(Attempt).where(Attempt.attempt_code == code))
        answers = db.scalars(
            select(AttemptAnswer)
            .where(AttemptAnswer.attempt_id == attempt.id)
            .order_by(AttemptAnswer.question_no)
        ).all()
        old, ids = _add_batch(
            db,
            paper=db.get(ExamPaper, pid),
            batch_code="OLD_COMPAT_" + uuid4().hex[:12],
            current=False,
            correct_letters=tuple(a.correct_option for a in answers),
        )
        old_id = old.id
        attempt.import_batch_id = old_id
        for answer, question_id in zip(answers, ids, strict=True):
            answer.question_id = question_id
            question = db.get(Question, question_id)
            for field in fields[:6]:
                setattr(question, field, getattr(answer, field))
        answer = answers[0]
        answer.question_text = "  " + answer.question_text + "\n"
        answer_id, attempt_id = answer.id, attempt.id
        grade = (attempt.correct_count, attempt.correct_rate)
        baseline = {field: getattr(answer, field) for field in fields}
        db.commit()
    supplement = client.get(url, headers=headers).json()["data"]
    assert supplement["review_materials_source"] == "matched_current_batch"
    assert supplement["skills"] == current["skills"]
    assert supplement["candidate_causes"] == current["candidate_causes"]
    assert supplement["audio"]["status"] == "available"
    assert supplement["audio"]["url"].endswith(f"expected_batch_id={batch}")
    assert "交卷快照和成绩保持原样" in supplement["annotation_source_note"]
    assert "相同的原音" in supplement["audio_source_note"]
    assert supplement["personal_cause_status"] == "unconfirmed"
    for field, value in [
        ("question_text", "Different historical question"),
        ("option_a", "Different option"),
        ("correct_option", "B"),
    ]:
        with SessionLocal() as db:
            setattr(db.get(AttemptAnswer, answer_id), field, value)
            db.commit()
        rejected = client.get(url, headers=headers).json()["data"]
        assert rejected["skills"] == rejected["candidate_causes"] == []
        assert rejected["audio"]["status"] == "batch_mismatch"
        with SessionLocal() as db:
            setattr(db.get(AttemptAnswer, answer_id), field, baseline[field])
            db.commit()
    with SessionLocal() as db:
        original_audio = db.get(AudioFile, db.get(ImportBatch, old_id).audio_id)
        different = AudioFile(
            audio_code="DIFFERENT_" + uuid4().hex,
            storage_key=uuid4().hex + ".m4a",
            duration_ms=original_audio.duration_ms,
            format="m4a",
            mime_type="audio/mp4",
            file_hash="f" * 64,
        )
        db.add(different)
        db.flush()
        db.get(ImportBatch, old_id).audio_id = different.id
        db.commit()
    rejected = client.get(url, headers=headers).json()["data"]
    assert rejected["skills"] == rejected["candidate_causes"] == []
    assert rejected["audio"]["status"] == "batch_mismatch"
    with SessionLocal() as db:
        attempt = db.get(Attempt, attempt_id)
        assert (attempt.correct_count, attempt.correct_rate) == grade
        answer = db.get(AttemptAnswer, answer_id)
        assert {field: getattr(answer, field) for field in baseline} == baseline
