"""CSV 导出接口（AC-31/AC-32，主文档 §11.1）。"""

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, text

from tests.admin_support import (
    audit_event,
    cleanup_users,
    create_user,
    request_id_of,
    session_local,
)
from tests.conftest import auth_headers


def _decode(response) -> str:
    assert response.content[:3] == b"\xef\xbb\xbf", "缺少 UTF-8 BOM"
    return response.content.decode("utf-8-sig")


def _rows(text_value: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text_value)))


def _bulk_login_events(count: int, *, username_prefix: str) -> list[uuid.UUID]:
    from app.db.models_admin import AdminLoginEvent

    ids = [uuid.uuid4() for _ in range(count)]
    now = datetime.now(UTC)
    payload = [
        {
            "event_id": event_id,
            "request_id": uuid.uuid4(),
            "event_type": "LOGIN_FAILED",
            "actor_user_id": None,
            "actor_name": "",
            "role_snapshot": None,
            "target_type": None,
            "target_id": None,
            "result": "FAILURE",
            "reason_code": "BAD_PASSWORD",
            "summary": {},
            "ip": None,
            "user_agent": "bulk",
            "duration_ms": 0,
            "occurred_at": now,
            "username_attempted": f"{username_prefix}{event_id.hex[:6]}",
        }
        for event_id in ids
    ]
    SessionLocal = session_local()
    with SessionLocal() as db:
        db.execute(insert(AdminLoginEvent), payload)
        db.commit()
    return ids


def _bulk_operation_events(count: int, *, actor: str, summary_size: int) -> list[uuid.UUID]:
    from app.db.models_admin import AdminAuditEvent

    ids = [uuid.uuid4() for _ in range(count)]
    now = datetime.now(UTC)
    payload = []
    for event_id in ids:
        payload.append(
            {
                "event_id": event_id,
                "request_id": uuid.uuid4(),
                "event_type": "EXPORT_COMPLETED",
                "actor_user_id": None,
                "actor_name": f"{actor}{event_id.hex[:6]}",
                "role_snapshot": "admin",
                "target_type": "export",
                "target_id": "bulk",
                "result": "SUCCESS",
                "reason_code": None,
                "summary": {"export_type": "x" * summary_size},
                "ip": None,
                "user_agent": "bulk",
                "duration_ms": 0,
                "occurred_at": now,
                "run_id": None,
            }
        )
    SessionLocal = session_local()
    with SessionLocal() as db:
        db.execute(insert(AdminAuditEvent), payload)
        db.commit()
    return ids


def _cleanup_event_ids(event_ids: list[uuid.UUID]) -> None:
    SessionLocal = session_local()
    with SessionLocal() as db:
        for event_id in event_ids:
            db.execute(
                text("DELETE FROM admin_login_events WHERE event_id = :i"),
                {"i": event_id},
            )
            db.execute(
                text("DELETE FROM admin_audit_events WHERE event_id = :i"),
                {"i": event_id},
            )
        db.commit()


def test_users_export_content_and_headers(
    client: TestClient, admin_token: str
) -> None:
    data, payload = create_user(
        client, admin_token, nickname='=1+1,"引号"', username=f"csv_{uuid.uuid4().hex[:6]}"
    )
    try:
        response = client.get(
            f"/api/v1/admin/exports/users?username={payload['username']}",
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        disposition = response.headers["content-disposition"]
        assert disposition.startswith('attachment; filename="admin-users-')
        assert disposition.endswith('.csv"')
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"

        body = _decode(response)
        assert "\r\n" in body
        rows = _rows(body)
        assert rows[0] == [
            "用户ID",
            "用户名",
            "昵称",
            "角色",
            "状态",
            "创建时间",
            "更新时间",
        ]
        assert len(rows) == 2
        row = rows[1]
        assert row[0] == str(data["id"])
        assert row[1] == payload["username"]
        # 公式前缀防护：前置单引号，库值不变。
        assert row[2].startswith("'=1+1")
        assert row[3] == "学生"
        assert row[4] == "启用"
        assert row[5].endswith("+08:00")
    finally:
        cleanup_users([data["id"]])


def test_login_export_filters_and_escaping(
    client: TestClient, admin_token: str
) -> None:
    prefix = f"ev_{uuid.uuid4().hex[:6]}_"
    event_ids = _bulk_login_events(2, username_prefix=prefix)
    try:
        response = client.get(
            "/api/v1/admin/exports/login-logs",
            params={"username": prefix},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200, response.text
        rows = _rows(_decode(response))
        assert rows[0] == [
            "事件ID",
            "时间",
            "声明用户名",
            "识别ID",
            "操作者名称",
            "角色快照",
            "结果",
            "原因",
            "IP",
            "UA摘要",
        ]
        assert len(rows) == 3
        assert all(row[2].startswith(prefix) for row in rows[1:])
        assert rows[1][6] == "失败"
        assert rows[1][7] == "密码错误"
        assert rows[1][1].endswith("+08:00")

        # 过滤条件同样生效：不同 username 不出现。
        empty = client.get(
            "/api/v1/admin/exports/login-logs?username=no-such-user-xyz",
            headers=auth_headers(admin_token),
        )
        assert empty.status_code == 200
        empty_rows = _rows(_decode(empty))
        assert empty_rows == [rows[0]]
    finally:
        _cleanup_event_ids(event_ids)


def test_operation_export_columns_and_summary(
    client: TestClient, admin_token: str
) -> None:
    actor = f"op_{uuid.uuid4().hex[:6]}"
    SessionLocal = session_local()
    from app.db.models_admin import AdminAuditEvent

    event_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(
            AdminAuditEvent(
                event_id=event_id,
                request_id=uuid.uuid4(),
                event_type="SESSION_REVOKED",
                actor_user_id=None,
                actor_name=actor,
                role_snapshot="admin",
                target_type="session",
                target_id="abc",
                result="SUCCESS",
                reason_code=None,
                summary={"session_id": "s-1", "target_user_id": 3},
                ip=None,
                user_agent="pytest",
                duration_ms=1,
                occurred_at=datetime.now(UTC),
                run_id=None,
            )
        )
        db.commit()

    try:
        response = client.get(
            "/api/v1/admin/exports/operation-logs",
            params={"actor_username": actor},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200, response.text
        rows = _rows(_decode(response))
        assert rows[0] == [
            "事件ID",
            "时间",
            "操作者名称",
            "操作者ID",
            "事件类型",
            "目标类型",
            "目标ID",
            "结果",
            "原因",
            "摘要",
            "请求ID",
            "run_id",
        ]
        assert len(rows) == 2
        row = rows[1]
        assert row[0] == str(event_id)
        assert row[2] == actor
        assert row[4] == "强制下线"
        assert row[5] == "会话"
        assert row[6] == "abc"
        assert row[7] == "成功"
        assert '"session_id": "s-1"' in row[9]
        assert row[11] == ""
    finally:
        _cleanup_event_ids([event_id])


def test_row_limit_400_and_event(
    client: TestClient, admin_token: str
) -> None:
    prefix = f"over_{uuid.uuid4().hex[:6]}_"
    event_ids = _bulk_login_events(5001, username_prefix=prefix)
    try:
        response = client.get(
            "/api/v1/admin/exports/login-logs",
            params={"username": prefix},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400, response.text
        assert response.headers["content-type"].startswith("application/json")
        event = audit_event(request_id_of(response))
        assert event is not None
        assert event.event_type == "EXPORT_FAILED"
        assert event.reason_code == "limit_rows"
        assert event.summary["stage"] == "limit_rows"
        assert event.summary["export_type"] == "login_logs"
    finally:
        _cleanup_event_ids(event_ids)


def test_byte_limit_400(
    client: TestClient, admin_token: str
) -> None:
    actor = f"big_{uuid.uuid4().hex[:6]}"
    event_ids = _bulk_operation_events(4000, actor=actor, summary_size=1500)
    try:
        response = client.get(
            "/api/v1/admin/exports/operation-logs",
            params={"actor_username": actor},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400, response.text
        event = audit_event(request_id_of(response))
        assert event is not None
        assert event.reason_code == "limit_bytes"
    finally:
        _cleanup_event_ids(event_ids)


def test_timeout_500_without_truncation(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.services.admin import exports as exports_service

    monkeypatch.setattr(exports_service, "_monotonic", lambda: 10**9)

    response = client.get(
        "/api/v1/admin/exports/users", headers=auth_headers(admin_token)
    )
    assert response.status_code == 500, response.text
    assert response.headers["content-type"].startswith("application/json")
    event = audit_event(request_id_of(response))
    assert event is not None
    assert event.event_type == "EXPORT_FAILED"
    assert event.reason_code == "timeout"


def test_audit_failure_returns_500_without_csv(
    client: TestClient, admin_token: str, monkeypatch
) -> None:
    from app.services.admin import exports as exports_service

    def _boom():
        raise RuntimeError("audit db down")

    monkeypatch.setattr(exports_service, "SessionLocal", _boom)

    response = client.get(
        "/api/v1/admin/exports/users", headers=auth_headers(admin_token)
    )
    assert response.status_code == 500, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "用户ID" not in response.text


def test_export_success_event_fields(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/exports/users", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    event = audit_event(request_id_of(response))
    assert event is not None
    assert event.event_type == "EXPORT_COMPLETED"
    assert event.result == "SUCCESS"
    assert event.summary["export_type"] == "users"
    assert event.summary["row_count"] >= 1
    assert event.summary["byte_size"] == len(response.content)
    assert event.target_type == "export"


def test_export_permissions(
    client: TestClient, admin_token: str, student_token: str, monkeypatch
) -> None:
    from app.core import admin_permissions
    from app.core.admin_permissions import ROLE_PERMISSIONS
    from app.core.permissions import ROLE_ADMIN

    assert (
        client.get(
            "/api/v1/admin/exports/users", headers=auth_headers(student_token)
        ).status_code
        == 403
    )

    full = ROLE_PERMISSIONS[ROLE_ADMIN]
    # 缺少导出码。
    monkeypatch.setitem(
        admin_permissions.ROLE_PERMISSIONS,
        ROLE_ADMIN,
        full - {"admin:export:users"},
    )
    assert (
        client.get(
            "/api/v1/admin/exports/users", headers=auth_headers(admin_token)
        ).status_code
        == 403
    )

    # 缺少读取码。
    monkeypatch.setitem(
        admin_permissions.ROLE_PERMISSIONS,
        ROLE_ADMIN,
        full - {"admin:user:read"},
    )
    assert (
        client.get(
            "/api/v1/admin/exports/users", headers=auth_headers(admin_token)
        ).status_code
        == 403
    )


def test_pagination_parameters_ignored(
    client: TestClient, admin_token: str
) -> None:
    response = client.get(
        "/api/v1/admin/exports/users?page=99&page_size=10",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    rows = _rows(_decode(response))
    assert len(rows) - 1 >= 2
