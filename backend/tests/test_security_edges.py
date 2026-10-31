"""鉴权边界与错误码用例（对应开发文档 6.2 T7–T14）。"""

from datetime import timedelta

import jwt
from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def test_login_failures_share_one_message(client: TestClient) -> None:
    messages = []
    for username, password in [
        ("admin", "wrong-password"),
        ("not-exists", "whatever"),
    ]:
        response = client.post(
            "/api/v1/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == 401
        messages.append(body["msg"])

    from app.core.security import hash_password
    from app.db.base import SessionLocal
    from app.db.models import User

    with SessionLocal() as db:
        if db.query(User).filter(User.username == "disabled_user").first() is None:
            db.add(
                User(
                    username="disabled_user",
                    password_hash=hash_password("disabled123"),
                    nickname="停用账号",
                    status="disabled",
                )
            )
            db.commit()

    response = client.post(
        "/api/v1/login",
        json={"username": "disabled_user", "password": "disabled123"},
    )
    assert response.status_code == 401
    messages.append(response.json()["msg"])
    assert len(set(messages)) == 1


def test_missing_request_fields_422(client: TestClient) -> None:
    response = client.post("/api/v1/login", json={"username": "admin"})
    assert response.status_code == 422
    assert response.json()["code"] == 422
    assert response.json()["msg"] == "请求参数校验失败"


def test_tampered_and_expired_token_401(
    client: TestClient, admin_token: str
) -> None:
    tampered = client.get(
        "/api/v1/getInfo",
        headers={"Authorization": f"Bearer {admin_token}x"},
    )
    assert tampered.status_code == 401
    assert tampered.json()["code"] == 401

    from app.core.config import get_settings
    from app.core.security import utc_now

    settings = get_settings()
    now = utc_now()
    expired_payload = {
        "sub": "1",
        "username": "admin",
        "jti": "expired-token-for-test",
        "type": "access",
        "iat": now - timedelta(hours=3),
        "exp": now - timedelta(hours=1),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    expired = client.get(
        "/api/v1/getInfo",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired.status_code == 401

    missing_claim_payload = {
        "sub": "1",
        "username": "admin",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    missing_claim_token = jwt.encode(
        missing_claim_payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    missing_claim = client.get(
        "/api/v1/getInfo",
        headers={"Authorization": f"Bearer {missing_claim_token}"},
    )
    assert missing_claim.status_code == 401


def test_task_paper_not_found_404(
    client: TestClient, admin_token: str
) -> None:
    response = client.post(
        "/api/v1/admin/processing-tasks",
        headers=auth_headers(admin_token),
        json={"paper_id": 999999},
    )
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_task_invalid_status_400(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/processing-tasks?status=bogus",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == 400
