"""T03 测试支持：临时用户、会话与审计查询。

`app.*` 一律在函数内延迟导入（见 tests/conftest.py 约束）。
"""

import uuid
from datetime import UTC, datetime, timedelta

from tests.conftest import auth_headers

DEFAULT_PASSWORD = "T03-password-123"


def session_local():
    from app.db.base import SessionLocal

    return SessionLocal


def unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def login_token(client, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def create_user(
    client,
    admin_token: str,
    *,
    username: str | None = None,
    password: str = DEFAULT_PASSWORD,
    nickname: str = "T03 临时用户",
    role: str = "student",
):
    payload = {
        "username": username or unique("t03"),
        "password": password,
        "nickname": nickname,
        "role": role,
    }
    response = client.post(
        "/api/v1/admin/users", json=payload, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return data, payload


def cleanup_users(user_ids: list[int]) -> None:
    from sqlalchemy import text

    SessionLocal = session_local()
    with SessionLocal() as db:
        for user_id in user_ids:
            db.execute(
                text("DELETE FROM auth_sessions WHERE user_id = :u"), {"u": user_id}
            )
            db.execute(
                text("DELETE FROM token_revocations WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(
                text("DELETE FROM user_roles WHERE user_id = :u"), {"u": user_id}
            )
            db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        db.commit()


def user_row(user_id: int):
    from sqlalchemy import select

    from app.db.models import User

    SessionLocal = session_local()
    with SessionLocal() as db:
        return db.get(User, user_id)


def set_user(user_id: int, **values) -> None:
    from sqlalchemy import update

    from app.db.models import User

    SessionLocal = session_local()
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == user_id).values(**values))
        db.commit()


def set_session(session_id: uuid.UUID, **values) -> None:
    from sqlalchemy import update

    from app.db.models_admin import AuthSession

    SessionLocal = session_local()
    with SessionLocal() as db:
        db.execute(
            update(AuthSession).where(AuthSession.id == session_id).values(**values)
        )
        db.commit()


def get_session(session_id: uuid.UUID):
    from app.db.models_admin import AuthSession

    SessionLocal = session_local()
    with SessionLocal() as db:
        return db.get(AuthSession, session_id)


def session_of_token(token: str) -> uuid.UUID:
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    return uuid.UUID(payload["session_id"])


def claims_of_token(token: str) -> dict:
    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


def audit_event(request_id: uuid.UUID, *, channel: str = "audit"):
    from sqlalchemy import select

    if channel == "login":
        from app.db.models_admin import AdminLoginEvent as Model
    else:
        from app.db.models_admin import AdminAuditEvent as Model
    SessionLocal = session_local()
    with SessionLocal() as db:
        return db.scalar(select(Model).where(Model.request_id == request_id))


def request_id_of(response) -> uuid.UUID:
    return uuid.UUID(response.headers["X-Request-ID"])


def seconds_ago(seconds: float) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=seconds)
