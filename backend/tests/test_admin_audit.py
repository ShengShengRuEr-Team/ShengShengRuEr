"""审计基础（T02 / AC-09、AC-10、AC-11 的登录与失败通道部分）。

覆盖：四类登录事件、成功事件同事务、失败事件独立事务、DB 故障降级文件、
文件也失败时 stderr+critical、request_id、summary 白名单与 2KiB 上限、
event_id 去重、敏感字段不落库。

`app.*` 一律在用例/夹具内延迟导入（见 tests/conftest.py 约束）。
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from tests.conftest import auth_headers, login


def _session_local():
    from app.db.base import SessionLocal

    return SessionLocal


def _audit():
    from app.services.admin import audit

    return audit


def _models():
    from app.db.models_admin import AdminAuditEvent, AdminLoginEvent

    return AdminLoginEvent, AdminAuditEvent


def _request_id_of(response) -> uuid.UUID:
    return uuid.UUID(response.headers["X-Request-ID"])


def _login_event(request_id: uuid.UUID):
    AdminLoginEvent, _ = _models()
    SessionLocal = _session_local()
    with SessionLocal() as db:
        return db.scalar(
            select(AdminLoginEvent).where(
                AdminLoginEvent.request_id == request_id
            )
        )


def _audit_event(request_id: uuid.UUID):
    _, AdminAuditEvent = _models()
    SessionLocal = _session_local()
    with SessionLocal() as db:
        return db.scalar(
            select(AdminAuditEvent).where(
                AdminAuditEvent.request_id == request_id
            )
        )


def _admin_user_id() -> int:
    from app.db.models import User

    SessionLocal = _session_local()
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.username == "admin"))


@pytest.fixture(autouse=True)
def reset_audit_state(monkeypatch, tmp_path):
    """每个用例重置健康状态与降级目录，避免跨用例污染。"""

    audit = _audit()
    audit.HEALTH.state = "unknown"
    audit.HEALTH.last_error_code = None
    audit.HEALTH.last_error_at = None
    audit.HEALTH.last_db_success_at = None
    audit.HEALTH.last_fallback_at = None
    writer = audit.AuditFallbackWriter(tmp_path / "fallback", uuid.uuid4())
    monkeypatch.setattr(audit, "_writer", writer)
    yield writer


def test_login_success_event_is_committed_with_session(client: TestClient) -> None:
    import jwt

    from app.core.config import get_settings

    response = client.post(
        "/api/v1/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, response.text
    request_id = _request_id_of(response)
    settings = get_settings()
    payload = jwt.decode(
        response.json()["data"]["token"],
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    session_id = uuid.UUID(payload["session_id"])

    row = _login_event(request_id)
    assert row is not None
    assert row.event_type == "LOGIN_SUCCEEDED"
    assert row.result == "SUCCESS"
    assert row.reason_code is None
    assert row.actor_user_id == _admin_user_id()
    assert row.actor_name == "admin"
    assert row.role_snapshot == "admin"
    assert row.occurred_at.tzinfo is not None
    assert row.duration_ms >= 0
    assert set(row.summary) == {"session_id", "auth_version"}
    assert row.summary["session_id"] == str(session_id)
    assert row.summary["auth_version"] == 0
    assert row.event_id != row.request_id

    # 会话与事件同一次提交：都在数据库里。
    SessionLocal = _session_local()
    from app.db.models_admin import AuthSession

    with SessionLocal() as db:
        assert db.get(AuthSession, session_id) is not None


def test_unknown_account_event(client: TestClient) -> None:
    username = f"ghost_{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/login", json={"username": username, "password": "whatever"}
    )
    assert response.status_code == 401, response.text

    row = _login_event(_request_id_of(response))
    assert row is not None
    assert row.event_type == "LOGIN_FAILED"
    assert row.result == "FAILURE"
    assert row.reason_code == "UNKNOWN_ACCOUNT"
    assert row.actor_user_id is None
    assert row.actor_name == ""
    assert row.username_attempted == username
    assert row.summary == {"failure_type": "UNKNOWN_ACCOUNT"}


def test_bad_password_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401, response.text

    row = _login_event(_request_id_of(response))
    assert row is not None
    assert row.result == "FAILURE"
    assert row.reason_code == "BAD_PASSWORD"
    assert row.actor_user_id == _admin_user_id()
    assert row.role_snapshot == "admin"


def test_disabled_account_event(client: TestClient) -> None:
    from app.core.security import hash_password
    from app.db.models import Role, User, UserRole

    SessionLocal = _session_local()
    username = f"t02_disabled_{uuid.uuid4().hex[:8]}"
    password = "T02-password-123"
    with SessionLocal() as db:
        user = User(
            username=username,
            password_hash=hash_password(password),
            nickname="T02 停用用户",
            status="disabled",
        )
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.role_key == "student"))
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()
        user_id = user.id

    try:
        response = client.post(
            "/api/v1/login", json={"username": username, "password": password}
        )
        assert response.status_code == 401, response.text

        row = _login_event(_request_id_of(response))
        assert row is not None
        assert row.result == "FAILURE"
        assert row.reason_code == "DISABLED"
        assert row.actor_user_id == user_id
        assert row.username_attempted == username
    finally:
        with SessionLocal() as db:
            db.execute(
                text("DELETE FROM auth_sessions WHERE user_id = :u"),
                {"u": user_id},
            )
            db.execute(
                text("DELETE FROM user_roles WHERE user_id = :u"), {"u": user_id}
            )
            db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            db.commit()


def test_failure_audit_uses_independent_commit() -> None:
    """服务层失败事件写入后立即对其它连接可见（独立提交）。"""

    audit = _audit()
    event = audit.AuditEvent(
        event_type=audit.EVENT_LOGIN_FAILED,
        result=audit.RESULT_FAILURE,
        reason_code=audit.FAILURE_BAD_PASSWORD,
        summary_values={"failure_type": audit.FAILURE_BAD_PASSWORD},
        username_attempted="independent",
        actor_name="independent",
    )
    audit.persist_login_failure(event)

    row = _login_event(event.request_id)
    assert row is not None
    assert row.event_id == event.event_id
    assert audit.audit_storage_health()["last_db_success_at"] is not None


def test_success_audit_failure_blocks_login(
    client: TestClient, monkeypatch
) -> None:
    """成功审计写不了时：500、不发 token、不留 session。"""

    from app.main import app
    from app.db.models_admin import AuthSession

    audit = _audit()
    SessionLocal = _session_local()

    with SessionLocal() as db:
        before = db.execute(
            text("SELECT count(*) FROM auth_sessions")
        ).scalar()

    def _boom(*args, **kwargs):
        raise OperationalError("INSERT audit", {}, Exception("audit down"))

    monkeypatch.setattr(audit, "enqueue_login_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as broken:
        response = broken.post(
            "/api/v1/login", json={"username": "admin", "password": "admin123"}
        )

    assert response.status_code == 500, response.text
    body = response.json()
    assert body["code"] == 500
    assert body["data"] is None
    assert "X-Request-ID" in response.headers

    with SessionLocal() as db:
        after = db.execute(text("SELECT count(*) FROM auth_sessions")).scalar()
    assert after == before, "登录失败后不得留下会话"


def test_audit_db_down_falls_back_to_file(
    client: TestClient, monkeypatch, reset_audit_state
) -> None:
    audit = _audit()

    def _boom():
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(audit, "SessionLocal", _boom)

    response = client.post(
        "/api/v1/login", json={"username": "admin", "password": "wrong"}
    )
    # 原错误不覆盖：仍 401。
    assert response.status_code == 401, response.text

    request_id = _request_id_of(response)
    files = list(reset_audit_state.directory.glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    record = json.loads(content.strip())
    assert record["request_id"] == str(request_id)
    assert record["event_type"] == "LOGIN_FAILED"
    assert record["reason_code"] == "BAD_PASSWORD"
    assert "wrong" not in content
    # 允许的枚举值 BAD_PASSWORD 不算敏感字段；这里只禁止出现密码字段与秘密值。
    assert '"password"' not in content.lower()
    assert "password_hash" not in content
    assert "jti" not in content

    health = audit.audit_storage_health()
    assert health["state"] == "warning"
    assert health["last_error_code"] == "AUDIT_DB_WRITE_FAILED"
    assert health["last_fallback_at"] is not None


def test_audit_db_and_file_failure_goes_critical(
    client: TestClient, monkeypatch, tmp_path, caplog
) -> None:
    audit = _audit()

    def _boom():
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(audit, "SessionLocal", _boom)
    # 让降级目录不可创建：同名路径先占成文件。
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(
        audit,
        "_writer",
        audit.AuditFallbackWriter(blocked, uuid.uuid4()),
    )

    with caplog.at_level("ERROR"):
        response = client.post(
            "/api/v1/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401, response.text
    assert "AUDIT_STORAGE_CRITICAL" in caplog.text
    assert str(_request_id_of(response)) in caplog.text
    health = audit.audit_storage_health()
    assert health["state"] == "critical"
    assert health["last_error_code"] == "AUDIT_STORAGE_UNAVAILABLE"


def test_request_id_header_on_every_response(client: TestClient) -> None:
    from app.main import app

    ok_response = client.get("/api/v1/getInfo")
    assert ok_response.status_code == 401
    assert uuid.UUID(ok_response.headers["X-Request-ID"])

    login_response = client.post(
        "/api/v1/login", json={"username": "admin", "password": "admin123"}
    )
    assert login_response.status_code == 200
    assert uuid.UUID(login_response.headers["X-Request-ID"])

    invalid = client.post("/api/v1/login", json={"username": "admin"})
    assert invalid.status_code == 422
    assert uuid.UUID(invalid.headers["X-Request-ID"])

    # 不同请求不同 request_id。
    assert (
        ok_response.headers["X-Request-ID"]
        != login_response.headers["X-Request-ID"]
    )

    import app.api.deps as deps

    def _boom():
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    original = deps.SessionLocal
    deps.SessionLocal = _boom
    try:
        with TestClient(app, raise_server_exceptions=False) as broken:
            failed = broken.get(
                "/api/v1/getInfo",
                headers=auth_headers(login_response.json()["data"]["token"]),
            )
    finally:
        deps.SessionLocal = original
    assert failed.status_code == 500
    assert uuid.UUID(failed.headers["X-Request-ID"])


def test_summary_whitelist_and_size_cap() -> None:
    audit = _audit()

    summary = audit.build_summary(
        audit.EVENT_LOGIN_SUCCEEDED,
        {
            "session_id": "x" * 5000,
            "auth_version": 3,
            "password": "P@ssw0rd",
            "token": "jwt-token",
            "jti": "abc",
        },
    )
    assert set(summary) <= {"session_id", "auth_version"}
    assert summary["auth_version"] == 3
    assert "password" not in summary
    assert "token" not in summary
    assert "jti" not in summary
    encoded = json.dumps(summary, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= audit.SUMMARY_MAX_BYTES

    assert audit.build_summary(audit.EVENT_LOGIN_FAILED, {}) == {}

    with pytest.raises(ValueError):
        audit.build_summary("NOT_REGISTERED_EVENT", {"a": 1})


def test_event_id_is_unique_in_database(client: TestClient) -> None:
    audit = _audit()
    AdminLoginEvent, _ = _models()
    SessionLocal = _session_local()

    event = audit.AuditEvent(
        event_type=audit.EVENT_LOGIN_FAILED,
        result=audit.RESULT_FAILURE,
        reason_code=audit.FAILURE_BAD_PASSWORD,
        summary_values={"failure_type": audit.FAILURE_BAD_PASSWORD},
    )
    with SessionLocal() as db:
        db.add(event.login_row())
        db.commit()

    duplicate = event.login_row()
    with SessionLocal() as db:
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    with SessionLocal() as db:
        count = db.execute(
            text(
                "SELECT count(*) FROM admin_login_events "
                "WHERE event_id = :id"
            ),
            {"id": event.event_id},
        ).scalar()
    assert count == 1
    assert AdminLoginEvent.__tablename__ == "admin_login_events"


def test_result_check_constraint_rejects_unknown_value(
    client: TestClient,
) -> None:
    SessionLocal = _session_local()
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO admin_audit_events ("
                    "event_id, request_id, event_type, actor_name, result,"
                    " summary, user_agent, duration_ms, occurred_at) VALUES ("
                    ":event_id, :request_id, 'X', '', 'MAYBE', '{}'::jsonb,"
                    " '', 0, now())"
                ),
                {"event_id": uuid.uuid4(), "request_id": uuid.uuid4()},
            )
            db.commit()
        db.rollback()


def test_no_password_token_or_jti_stored(client: TestClient) -> None:
    import jwt

    from app.core.config import get_settings

    password = "admin123"
    response = client.post(
        "/api/v1/login", json={"username": "admin", "password": password}
    )
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    settings = get_settings()
    jti = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )["jti"]
    session_id = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )["session_id"]

    SessionLocal = _session_local()
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT to_jsonb(t)::text FROM admin_login_events t "
                "WHERE request_id = :rid"
            ),
            {"rid": _request_id_of(response)},
        ).scalars().all()
        audit_rows = db.execute(
            text(
                "SELECT to_jsonb(t)::text FROM admin_audit_events t "
                "WHERE request_id = :rid"
            ),
            {"rid": _request_id_of(response)},
        ).scalars().all()
    dumped = "\n".join([*rows, *audit_rows])
    assert password not in dumped
    assert token not in dumped
    assert jti not in dumped
    # 会话 id 属于允许的摘要字段（仅登录成功事件）。
    assert str(session_id) in dumped


def test_logout_writes_same_transaction_event(client: TestClient) -> None:
    token = login(client, "admin", "admin123")
    response = client.post("/api/v1/logout", headers=auth_headers(token))
    assert response.status_code == 200, response.text

    row = _audit_event(_request_id_of(response))
    assert row is not None
    assert row.event_type == "LOGOUT"
    assert row.result == "SUCCESS"
    assert row.actor_name == "admin"
    assert set(row.summary) == {"session_id"}


def test_logout_audit_failure_rolls_back_revocation(
    client: TestClient, monkeypatch
) -> None:
    from app.main import app

    audit = _audit()
    token = login(client, "admin", "admin123")

    def _boom(*args, **kwargs):
        raise OperationalError("INSERT audit", {}, Exception("audit down"))

    monkeypatch.setattr(audit, "enqueue_audit_event", _boom)

    with TestClient(app, raise_server_exceptions=False) as broken:
        response = broken.post(
            "/api/v1/logout", headers=auth_headers(token)
        )
    assert response.status_code == 500, response.text

    # 事务已回滚：会话未被撤销，旧 token 仍可用。
    assert (
        client.get("/api/v1/getInfo", headers=auth_headers(token)).status_code
        == 200
    )


def test_occurred_at_is_utc_aware(client: TestClient) -> None:
    response = client.post(
        "/api/v1/login", json={"username": "admin", "password": "wrong"}
    )
    row = _login_event(_request_id_of(response))
    assert row is not None
    assert row.occurred_at.tzinfo is not None
    delta = abs(
        (datetime.now(UTC) - row.occurred_at).total_seconds()
    )
    assert delta < 60


def test_fallback_writer_rotates_and_prunes(tmp_path) -> None:
    audit = _audit()
    writer = audit.AuditFallbackWriter(
        tmp_path,
        uuid.uuid4(),
        max_file_bytes=200,
        max_files=3,
        max_total_bytes=10_000,
    )
    for index in range(12):
        assert writer.write({"index": index, "payload": "x" * 80})

    files = sorted(writer.directory.glob("*.jsonl"))
    assert len(files) <= 3
    assert all(path.stat().st_size <= 400 for path in files)
    assert any(path.name == "audit-current.jsonl" for path in files)
    assert Path(writer.directory).exists()


def test_health_snapshot_shape() -> None:
    audit = _audit()
    snapshot = audit.audit_storage_health()
    assert set(snapshot) == {
        "state",
        "last_error_code",
        "last_error_at",
        "last_db_success_at",
        "last_fallback_at",
    }
    assert snapshot["state"] in {"unknown", "ok", "warning", "critical"}
