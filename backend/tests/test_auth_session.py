"""持久会话与共享认证（T01 / AC-28、AC-35 后端部分）。

覆盖：登录建会话且只存 jti 指纹、旧 token 401、新 token 200、
停用/版本递增/会话撤销/会话过期/会话不存在 → 401、DB 异常 → 500、
两独立 TestClient 跨实例失效、登出后 401。

注意：按 `tests/conftest.py` 约定，`app.*` 一律在夹具/用例内延迟导入，
避免收集阶段把 SQLAlchemy engine 绑到开发库。
"""

import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from tests.conftest import auth_headers, login


def _settings():
    from app.core.config import get_settings

    return get_settings()


def _session_local():
    from app.db.base import SessionLocal

    return SessionLocal


def _auth_session():
    from app.db.models_admin import AuthSession

    return AuthSession


def _decode(token: str) -> dict:
    settings = _settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


def _sign(payload: dict) -> str:
    settings = _settings()
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def _claim(token: str) -> SimpleNamespace:
    payload = _decode(token)
    return SimpleNamespace(
        user_id=int(payload["sub"]),
        username=payload["username"],
        jti=payload["jti"],
        session_id=uuid.UUID(payload["session_id"]),
        auth_version=payload["auth_version"],
        exp=payload["exp"],
    )


def _set_user(user_id: int, **values) -> None:
    from app.db.models import User

    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == user_id).values(**values))
        db.commit()


def _set_session(session_id: uuid.UUID, **values) -> None:
    AuthSession = _auth_session()
    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id)
            .values(**values)
        )
        db.commit()


def _delete_session(session_id: uuid.UUID) -> None:
    SessionLocal = _session_local()
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM auth_sessions WHERE id = :id"),
            {"id": session_id},
        )
        db.commit()


@pytest.fixture
def temp_user(client: TestClient):
    """创建临时用户（默认 student），测试结束按外键顺序清理。"""

    from app.core.security import hash_password
    from app.db.models import Role, User, UserRole

    SessionLocal = _session_local()
    created: list[int] = []

    def _make(role_key: str = "student", suffix: str = "") -> SimpleNamespace:
        username = f"t01_{suffix}{uuid.uuid4().hex[:8]}"
        password = "T01-password-123"
        with SessionLocal() as db:
            user = User(
                username=username,
                password_hash=hash_password(password),
                nickname="T01 临时用户",
            )
            db.add(user)
            db.flush()
            role = db.scalar(select(Role).where(Role.role_key == role_key))
            assert role is not None
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.commit()
            user_id = user.id
        created.append(user_id)
        return SimpleNamespace(
            user_id=user_id,
            username=username,
            password=password,
            token=login(client, username, password),
        )

    yield _make

    with SessionLocal() as db:
        for user_id in created:
            db.execute(
                text("DELETE FROM auth_sessions WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(
                text("DELETE FROM token_revocations WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(
                text("DELETE FROM user_roles WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        db.commit()


def test_login_creates_session_and_stores_only_jti_hash(
    client: TestClient, admin_token: str
) -> None:
    from app.db.models import TokenRevocation

    AuthSession = _auth_session()
    SessionLocal = _session_local()
    claims = _claim(admin_token)

    assert claims.auth_version == 0

    with SessionLocal() as db:
        session = db.get(AuthSession, claims.session_id)
        assert session is not None
        assert session.user_id == claims.user_id
        assert session.jti_hash == sha256(claims.jti.encode("utf-8")).hexdigest()
        # 原始 jti 不落库。
        assert claims.jti not in session.jti_hash
        assert session.auth_version == 0
        assert session.revoked_at is None
        assert session.revoke_reason is None
        assert session.ip is None or isinstance(session.ip, str)
        assert session.expires_at > session.issued_at

        # T01 登录不写审计：本期也无审计表；旧撤销表同样不写。
        revoked = db.scalar(
            select(TokenRevocation.id).where(
                TokenRevocation.jti == claims.jti
            )
        )
        assert revoked is None


def test_valid_new_token_returns_200(
    client: TestClient, admin_token: str
) -> None:
    response = client.get("/api/v1/getInfo", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text


def test_legacy_token_without_new_claims_returns_401(
    client: TestClient,
) -> None:
    """存量 token 缺 auth_version/session_id，一律 401（部署后需重新登录）。"""

    from app.db.models import User

    SessionLocal = _session_local()
    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        user_id = user.id

    legacy = _sign(
        {
            "sub": str(user_id),
            "username": "admin",
            "jti": uuid.uuid4().hex,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=10),
        }
    )
    response = client.get("/api/v1/getInfo", headers=auth_headers(legacy))
    assert response.status_code == 401, response.text

    # 只缺 session_id 也无效。
    partial = _sign(
        {
            "sub": str(user_id),
            "username": "admin",
            "jti": uuid.uuid4().hex,
            "type": "access",
            "auth_version": 0,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        }
    )
    assert (
        client.get("/api/v1/getInfo", headers=auth_headers(partial)).status_code
        == 401
    )


def test_bool_auth_version_is_rejected(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "bool")
    payload = _decode(info.token)
    payload["auth_version"] = True
    forged = _sign(payload)
    response = client.get("/api/v1/getInfo", headers=auth_headers(forged))
    assert response.status_code == 401, response.text


def test_disabled_user_token_returns_401(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "disabled")
    assert (
        client.get("/api/v1/getInfo", headers=auth_headers(info.token))
    ).status_code == 200

    try:
        _set_user(info.user_id, status="disabled")
        response = client.get("/api/v1/getInfo", headers=auth_headers(info.token))
        assert response.status_code == 401, response.text
        # 重新登录同样被拒（统一 401）。
        retry = client.post(
            "/api/v1/login",
            json={"username": info.username, "password": info.password},
        )
        assert retry.status_code == 401
    finally:
        _set_user(info.user_id, status="active")


def test_auth_version_bump_invalidates_token(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "version")
    claims = _claim(info.token)

    try:
        _set_user(info.user_id, auth_version=claims.auth_version + 1)
        response = client.get("/api/v1/getInfo", headers=auth_headers(info.token))
        assert response.status_code == 401, response.text
    finally:
        _set_user(info.user_id, auth_version=claims.auth_version)


def test_revoked_session_returns_401(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "revoked")
    claims = _claim(info.token)

    _set_session(
        claims.session_id,
        revoked_at=datetime.now(UTC),
        revoke_reason="kicked",
    )
    response = client.get("/api/v1/getInfo", headers=auth_headers(info.token))
    assert response.status_code == 401, response.text


def test_expired_session_returns_401(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "expired")
    claims = _claim(info.token)

    _set_session(
        claims.session_id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    response = client.get("/api/v1/getInfo", headers=auth_headers(info.token))
    assert response.status_code == 401, response.text


def test_missing_session_row_returns_401(
    client: TestClient, temp_user
) -> None:
    info = temp_user("student", "nosession")
    claims = _claim(info.token)

    _delete_session(claims.session_id)
    response = client.get("/api/v1/getInfo", headers=auth_headers(info.token))
    assert response.status_code == 401, response.text


def test_logout_revokes_session_and_token(
    client: TestClient, temp_user
) -> None:
    from app.db.models import TokenRevocation

    AuthSession = _auth_session()
    SessionLocal = _session_local()
    info = temp_user("student", "logout")
    claims = _claim(info.token)
    headers = auth_headers(info.token)

    assert client.post("/api/v1/logout", headers=headers).status_code == 200

    with SessionLocal() as db:
        session = db.get(AuthSession, claims.session_id)
        assert session is not None
        assert session.revoked_at is not None
        assert session.revoke_reason == "logout"
        # 旧撤销表仍写入，保持既有失效语义。
        assert (
            db.scalar(
                select(TokenRevocation.id).where(
                    TokenRevocation.jti == claims.jti
                )
            )
            is not None
        )

    replay = client.get("/api/v1/getInfo", headers=headers)
    assert replay.status_code == 401, replay.text


def test_cross_instance_revocation(
    client: TestClient, temp_user
) -> None:
    """两个独立 TestClient 共享同一数据库事实：A 签发被撤销后 B 也拒绝。"""

    from app.main import app

    info = temp_user("student", "cross")
    headers = auth_headers(info.token)
    claims = _claim(info.token)

    with TestClient(app) as other:
        assert other.get("/api/v1/getInfo", headers=headers).status_code == 200

        _set_session(
            claims.session_id,
            revoked_at=datetime.now(UTC),
            revoke_reason="kicked",
        )

        assert other.get("/api/v1/getInfo", headers=headers).status_code == 401

    assert client.get("/api/v1/getInfo", headers=headers).status_code == 401


def test_database_error_is_500_not_401(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    """认证期数据库异常必须 500，不得伪装成 401。"""

    from app.api import deps
    from app.main import app

    def _boom():
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(deps, "SessionLocal", _boom)

    with TestClient(app, raise_server_exceptions=False) as broken:
        response = broken.get(
            "/api/v1/getInfo", headers=auth_headers(admin_token)
        )

    assert response.status_code == 500, response.text
    body = response.json()
    assert body["code"] == 500
    assert body["msg"] == "服务器内部错误"
    assert body["data"] is None
