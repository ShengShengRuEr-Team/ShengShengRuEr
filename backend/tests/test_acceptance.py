"""模块一验收用例（对应开发文档 2.2）。"""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_01_admin_getinfo_has_admin_role(
    client: TestClient, admin_token: str
) -> None:
    response = client.get("/api/v1/getInfo", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["roles"] == ["admin"]
    assert body["data"]["is_admin"] is True


def test_02_student_getinfo_has_student_role(
    client: TestClient, student_token: str
) -> None:
    response = client.get("/api/v1/getInfo", headers=auth_headers(student_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["roles"] == ["student"]
    assert body["data"]["is_admin"] is False


def test_03_student_forbidden_on_admin_endpoint(
    client: TestClient, student_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/overview", headers=auth_headers(student_token)
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == 403


def test_04_admin_allowed_on_admin_endpoint(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/overview", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["role"] == "admin"
    assert "管理员" in body["data"]["message"]


def test_05_without_token_returns_401(client: TestClient) -> None:
    assert client.get("/api/v1/getInfo").status_code == 401
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.post("/api/v1/logout").status_code == 401


def test_06_logout_revokes_old_token(
    client: TestClient, admin_token: str
) -> None:
    headers = auth_headers(admin_token)
    assert client.post("/api/v1/logout", headers=headers).status_code == 200
    replay = client.get("/api/v1/getInfo", headers=headers)
    assert replay.status_code == 401, replay.text
