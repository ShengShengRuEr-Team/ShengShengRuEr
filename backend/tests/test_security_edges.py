"""鉴权边界与错误码用例。"""

from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_login_failures_share_one_message(client: TestClient) -> None:
    cases = (
        {"username": "admin", "password": "wrong-password"},
        {"username": "not-exist-user", "password": "whatever"},
    )
    messages: set[str] = set()
    for payload in cases:
        response = client.post("/api/v1/login", json=payload)
        assert response.status_code == 401, response.text
        messages.add(response.json()["msg"])
    assert len(messages) == 1, f"登录失败提示不一致：{messages}"


def test_missing_request_fields_422(client: TestClient) -> None:
    response = client.post("/api/v1/login", json={"username": "admin"})
    assert response.status_code == 422, response.text


def test_tampered_token_returns_401(client: TestClient, admin_token: str) -> None:
    tampered = admin_token[:-3] + "xyz"
    response = client.get("/api/v1/getInfo", headers=auth_headers(tampered))
    assert response.status_code == 401, response.text


def test_invalid_authorization_scheme_returns_401(
    client: TestClient, admin_token: str
) -> None:
    headers = {"Authorization": f"Basic {admin_token}"}
    response = client.get("/api/v1/getInfo", headers=headers)
    assert response.status_code == 401, response.text


def test_admin_endpoint_without_token_returns_401_not_403(
    client: TestClient,
) -> None:
    """顺序固定：先判 401，再判 403。"""

    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 401, response.text
