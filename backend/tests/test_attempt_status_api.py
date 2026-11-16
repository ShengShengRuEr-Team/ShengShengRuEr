"""API-3 提交状态：权限、字段白名单、只读、单快照一致性与语义不变量。"""

import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from tests.attempt_support import (
    create_hidden_paper,
    create_student,
    create_visible_paper,
    set_visibility,
)
from tests.conftest import auth_headers, login

STATUS_URL = "/api/v1/listening-papers/{paper_id}/attempt-status"
SUBMIT_URL = "/api/v1/listening-papers/{paper_id}/attempts"


def _status(client, token, paper_id):
    return client.get(STATUS_URL.format(paper_id=paper_id), headers=auth_headers(token))


def _submit(client, token, paper):
    return client.post(
        SUBMIT_URL.format(paper_id=paper.paper_id),
        headers={**auth_headers(token), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "loaded_question_ids": list(paper.question_ids),
            "answers": [
                {
                    "question_id": paper.question_ids[0],
                    "selected_option": paper.correct_letters[0],
                }
            ],
        },
    )


def test_status_missing_token_401(client: TestClient) -> None:
    paper = create_visible_paper(code="T_A3_401")
    response = client.get(STATUS_URL.format(paper_id=paper.paper_id))
    assert response.status_code == 401


def test_status_admin_403(client: TestClient, admin_token: str) -> None:
    paper = create_visible_paper(code="T_A3_403")
    response = _status(client, admin_token, paper.paper_id)
    assert response.status_code == 403


def test_status_hidden_404(client: TestClient, student_token: str) -> None:
    paper_id = create_hidden_paper(code="T_A3_404H")
    response = _status(client, student_token, paper_id)
    assert response.status_code == 404


def test_status_missing_paper_404(client: TestClient, student_token: str) -> None:
    response = _status(client, student_token, 987_654_321)
    assert response.status_code == 404
    assert response.headers.get("Cache-Control") == "no-store"


def test_status_false_without_submission(
    client: TestClient, student_token: str
) -> None:
    from app.schemas_attempt_status import MSG_STATUS_SUCCESS

    paper = create_visible_paper(code="T_A3_FALSE")
    response = _status(client, student_token, paper.paper_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["msg"] == MSG_STATUS_SUCCESS
    assert body["data"] == {
        "exam_paper_id": paper.paper_id,
        "submitted": False,
        "attempt_count": 0,
        "latest_attempt": None,
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_status_true_matches_api1_summary(
    client: TestClient, student_token: str
) -> None:
    paper = create_visible_paper(code="T_A3_TRUE")
    submitted = _submit(client, student_token, paper)
    assert submitted.status_code == 200, submitted.text
    summary = submitted.json()["data"]

    response = _status(client, student_token, paper.paper_id)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["submitted"] is True
    assert data["attempt_count"] == 1
    assert data["latest_attempt"] == summary
    assert data["latest_attempt"]["exam_paper_id"] == paper.paper_id
    assert response.headers["Cache-Control"] == "no-store"


def test_status_is_student_scoped(client: TestClient, student_token: str) -> None:
    paper = create_visible_paper(code="T_A3_SCOPE")
    assert _submit(client, student_token, paper).status_code == 200

    create_student("attempt_student_b")
    other_token = login(client, "attempt_student_b", "attempt123")
    response = _status(client, other_token, paper.paper_id)
    assert response.status_code == 200
    assert response.json()["data"]["submitted"] is False
    assert response.json()["data"]["attempt_count"] == 0


def test_status_field_whitelist(client: TestClient, student_token: str) -> None:
    paper = create_visible_paper(code="T_A3_FIELDS")
    _submit(client, student_token, paper)

    response = _status(client, student_token, paper.paper_id)
    data = response.json()["data"]
    assert set(data) == {
        "exam_paper_id",
        "submitted",
        "attempt_count",
        "latest_attempt",
    }
    assert set(data["latest_attempt"]) == {
        "attempt_code",
        "exam_paper_id",
        "submitted_at",
        "question_count",
        "correct_count",
        "correct_rate",
        "practice_score",
    }
    assert set(data["latest_attempt"]["practice_score"]) == {
        "available",
        "value",
        "max",
        "label",
        "reason",
    }
    raw = response.text
    for forbidden in (
        "correct_option",
        "explanation",
        "transcript",
        "question_id",
        "selected_option",
        "can_attempt",
        "attempt_limit",
    ):
        assert forbidden not in raw, forbidden


def test_status_does_not_write(client: TestClient, student_token: str) -> None:
    from sqlalchemy import func, select

    from app.db.base import SessionLocal
    from app.db.models_attempt import Attempt, AttemptAnswer, AttemptRejection

    paper = create_visible_paper(code="T_A3_NOWRITE")
    _submit(client, student_token, paper)

    def counts() -> tuple[int, int, int]:
        with SessionLocal() as db:
            return (
                db.scalar(select(func.count()).select_from(Attempt)),
                db.scalar(select(func.count()).select_from(AttemptAnswer)),
                db.scalar(select(func.count()).select_from(AttemptRejection)),
            )

    before = counts()
    for _ in range(3):
        assert _status(client, student_token, paper.paper_id).status_code == 200
    assert counts() == before


def test_status_offline_then_restore(
    client: TestClient, student_token: str
) -> None:
    paper = create_visible_paper(code="T_A3_OFF")
    submitted = _submit(client, student_token, paper)
    attempt_code = submitted.json()["data"]["attempt_code"]

    set_visibility(paper.paper_id, False)
    offline = _status(client, student_token, paper.paper_id)
    assert offline.status_code == 404
    assert offline.headers.get("Cache-Control") == "no-store"

    set_visibility(paper.paper_id, True)
    restored = _status(client, student_token, paper.paper_id)
    assert restored.status_code == 200
    assert restored.json()["data"]["latest_attempt"]["attempt_code"] == attempt_code


def test_status_schema_invariants_rejected() -> None:
    from pydantic import ValidationError

    from app.schemas_attempt_status import AttemptStatusData
    from app.schemas_attempts import AttemptSubmitData, PracticeScoreData

    summary = AttemptSubmitData(
        attempt_code=str(uuid.uuid4()),
        exam_paper_id=1,
        submitted_at="2026-11-14T06:30:00Z",
        question_count=1,
        correct_count=1,
        correct_rate=100,
        practice_score=PracticeScoreData(available=True, value=10, max=10),
    )
    invalid_cases = [
        {"submitted": False, "attempt_count": 1, "latest_attempt": None},
        {"submitted": True, "attempt_count": 0, "latest_attempt": None},
        {"submitted": False, "attempt_count": 0, "latest_attempt": summary},
        {"submitted": True, "attempt_count": 1, "latest_attempt": summary.model_copy(
            update={"exam_paper_id": 2}
        )},
    ]
    for case in invalid_cases:
        try:
            AttemptStatusData(exam_paper_id=1, **case)
        except ValidationError:
            continue
        raise AssertionError(f"矛盾状态未被拒绝：{case}")

    valid = AttemptStatusData(
        exam_paper_id=1, submitted=True, attempt_count=1, latest_attempt=summary
    )
    assert valid.latest_attempt is not None
    summary_only = AttemptStatusData(
        exam_paper_id=1, submitted=True, attempt_count=1, latest_attempt=None
    )
    assert summary_only.latest_attempt is None


def test_status_uses_single_window_statement(
    client: TestClient, student_token: str
) -> None:
    """AC-43：状态查询实际只发一条 SQL，且带窗口计数与 LIMIT（同快照）。"""

    from sqlalchemy import event

    from app.db.base import engine

    paper = create_visible_paper(code="T_A3_SQL1")
    assert _submit(client, student_token, paper).status_code == 200

    statements: list[str] = []

    def capture(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        if "FROM attempts" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert _status(client, student_token, paper.paper_id).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert len(statements) == 1, statements
    normalized = " ".join(statements[0].split()).lower()
    assert "count(*) over" in normalized
    assert "limit" in normalized


def test_status_concurrent_with_submit_is_consistent(
    client: TestClient, student_token: str
) -> None:
    paper = create_visible_paper(code="T_A3_CONC")

    def submit() -> int:
        return _submit(client, student_token, paper).status_code

    def status_ok() -> bool:
        response = _status(client, student_token, paper.paper_id)
        if response.status_code != 200:
            return False
        data = response.json()["data"]
        if data["submitted"] != (data["attempt_count"] > 0):
            return False
        if data["submitted"]:
            latest = data["latest_attempt"]
            return (
                data["attempt_count"] == 1
                and latest is not None
                and latest["exam_paper_id"] == paper.paper_id
            )
        return data["attempt_count"] == 0 and data["latest_attempt"] is None

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(submit)] + [
            pool.submit(status_ok) for _ in range(8)
        ]
        results = [future.result() for future in futures]

    assert results[0] == 200
    assert all(results[1:]), results
