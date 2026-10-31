"""模块一 10 条验收用例（对应开发文档 2.2）。"""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def _body(response) -> dict:
    return response.json()


def _assert_envelope(response, status_code: int) -> dict:
    assert response.status_code == status_code, response.text
    body = _body(response)
    assert body["code"] == status_code, response.text
    assert "msg" in body and "data" in body
    return body


def _paper_id(client: TestClient, token: str) -> int:
    response = client.get("/api/v1/papers", headers=auth_headers(token))
    body = _assert_envelope(response, 200)
    return body["data"]["items"][0]["id"]


def test_01_admin_getinfo(client: TestClient, admin_token: str) -> None:
    body = _assert_envelope(
        client.get("/api/v1/getInfo", headers=auth_headers(admin_token)), 200
    )
    assert "admin" in body["data"]["roles"]
    assert body["data"]["is_admin"] is True
    assert set(body["data"]["permissions"]) == {
        "paper:read",
        "question:read",
        "question:read_sensitive",
        "task:start",
        "task:read",
    }


def test_02_student_getinfo(client: TestClient, student_token: str) -> None:
    body = _assert_envelope(
        client.get("/api/v1/getInfo", headers=auth_headers(student_token)), 200
    )
    assert body["data"]["roles"] == ["student"]
    assert body["data"]["is_admin"] is False
    assert body["data"]["permissions"] == ["paper:read", "question:read"]


def test_03_student_admin_endpoints_403(
    client: TestClient, student_token: str
) -> None:
    headers = auth_headers(student_token)
    checks = [
        client.get("/api/v1/admin/papers/1/questions", headers=headers),
        client.post(
            "/api/v1/admin/processing-tasks",
            headers=headers,
            json={"paper_id": 1},
        ),
        client.get("/api/v1/admin/processing-tasks", headers=headers),
        client.get("/api/v1/admin/processing-tasks/1", headers=headers),
    ]
    for response in checks:
        _assert_envelope(response, 403)


def test_04_student_questions_hide_sensitive(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    paper_id = _paper_id(client, admin_token)
    response = client.get(
        f"/api/v1/papers/{paper_id}/questions",
        headers=auth_headers(student_token),
    )
    body = _assert_envelope(response, 200)
    items = body["data"]["items"]
    assert items
    expected_fields = {
        "id",
        "question_no",
        "prompt_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
    }
    for item in items:
        assert set(item) == expected_fields
    assert "correct_option" not in response.text
    assert "explanation_text" not in response.text
    assert "transcript_text" not in response.text


def test_04b_admin_questions_include_sensitive(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    paper_id = _paper_id(client, admin_token)
    admin_response = client.get(
        f"/api/v1/admin/papers/{paper_id}/questions",
        headers=auth_headers(admin_token),
    )
    admin_body = _assert_envelope(admin_response, 200)
    admin_items = admin_body["data"]["items"]
    assert admin_items
    expected_fields = {
        "id",
        "question_no",
        "prompt_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_option",
        "explanation_text",
        "transcript_text",
    }
    assert set(admin_items[0]) == expected_fields
    assert admin_items[0]["correct_option"]
    assert admin_items[0]["explanation_text"]
    assert admin_items[0]["transcript_text"]

    student_response = client.get(
        f"/api/v1/papers/{paper_id}/questions",
        headers=auth_headers(student_token),
    )
    for item in admin_items:
        assert item["explanation_text"] not in student_response.text
        assert item["transcript_text"] not in student_response.text


def test_05_without_token_all_business_endpoints_401(
    client: TestClient,
) -> None:
    checks = [
        client.post("/api/v1/logout"),
        client.get("/api/v1/getInfo"),
        client.get("/api/v1/papers"),
        client.get("/api/v1/papers/1/questions"),
        client.get("/api/v1/admin/papers/1/questions"),
        client.post("/api/v1/admin/processing-tasks", json={"paper_id": 1}),
        client.get("/api/v1/admin/processing-tasks"),
        client.get("/api/v1/admin/processing-tasks/1"),
    ]
    for response in checks:
        _assert_envelope(response, 401)


def test_06_logout_replay_token_401(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    _assert_envelope(client.post("/api/v1/logout", headers=headers), 200)
    _assert_envelope(client.get("/api/v1/getInfo", headers=headers), 401)
    _assert_envelope(client.get("/api/v1/papers", headers=headers), 401)


def test_07_admin_start_task_pending(
    client: TestClient, admin_token: str
) -> None:
    paper_id = _paper_id(client, admin_token)
    response = client.post(
        "/api/v1/admin/processing-tasks",
        headers=auth_headers(admin_token),
        json={"paper_id": paper_id},
    )
    body = _assert_envelope(response, 200)
    task = body["data"]
    assert task["status"] == "pending"
    assert task["progress"] == 0
    assert task["paper_id"] == paper_id
    assert task["message"] is None
    assert task["result"] is None
    assert task["started_at"] is None
    assert task["finished_at"] is None


def test_07b_admin_task_list_and_detail(
    client: TestClient, admin_token: str
) -> None:
    paper_id = _paper_id(client, admin_token)
    created = client.post(
        "/api/v1/admin/processing-tasks",
        headers=auth_headers(admin_token),
        json={"paper_id": paper_id},
    )
    task_id = _assert_envelope(created, 200)["data"]["id"]

    list_response = client.get(
        "/api/v1/admin/processing-tasks", headers=auth_headers(admin_token)
    )
    list_body = _assert_envelope(list_response, 200)
    item = next(
        item for item in list_body["data"]["items"] if item["id"] == task_id
    )
    assert set(item) == {
        "id",
        "paper_id",
        "task_type",
        "status",
        "progress",
        "message",
        "created_at",
    }

    detail = client.get(
        f"/api/v1/admin/processing-tasks/{task_id}",
        headers=auth_headers(admin_token),
    )
    task = _assert_envelope(detail, 200)["data"]
    assert set(task) == {
        "id",
        "paper_id",
        "task_type",
        "status",
        "progress",
        "message",
        "result",
        "created_by",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    }
    assert task["status"] == "pending"
    assert task["progress"] == 0


def test_08_student_task_endpoints_403(
    client: TestClient, student_token: str
) -> None:
    headers = auth_headers(student_token)
    checks = [
        client.post(
            "/api/v1/admin/processing-tasks",
            headers=headers,
            json={"paper_id": 1},
        ),
        client.get("/api/v1/admin/processing-tasks", headers=headers),
        client.get("/api/v1/admin/processing-tasks/1", headers=headers),
    ]
    for response in checks:
        _assert_envelope(response, 403)
