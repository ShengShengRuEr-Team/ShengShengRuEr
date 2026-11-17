"""活动节流（AC-07 部分，主文档 §6.3）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.admin_support import (
    cleanup_users,
    create_user,
    get_session,
    login_token,
    seconds_ago,
    session_of_token,
    set_session,
)
from tests.conftest import auth_headers


@pytest.fixture
def tracked_user(client: TestClient, admin_token: str):
    data, payload = create_user(client, admin_token)
    token = login_token(client, payload["username"], payload["password"])
    try:
        yield data, payload, token, session_of_token(token)
    finally:
        cleanup_users([data["id"]])


def test_activity_throttle_thirty_seconds(
    client: TestClient, tracked_user
) -> None:
    _, _, token, session_id = tracked_user
    headers = auth_headers(token)

    recent = seconds_ago(10)
    set_session(session_id, last_activity_at=recent)
    expires_before = get_session(session_id).expires_at

    assert client.get("/api/v1/getInfo", headers=headers).status_code == 200
    row = get_session(session_id)
    assert row.last_activity_at == recent  # 10 秒内不刷新
    assert row.expires_at == expires_before  # 绝不延长有效期

    old = seconds_ago(40)
    set_session(session_id, last_activity_at=old)
    assert client.get("/api/v1/getInfo", headers=headers).status_code == 200
    row = get_session(session_id)
    assert row.last_activity_at > old
    assert row.expires_at == expires_before


def test_monitor_reads_do_not_keep_session_alive(
    client: TestClient, admin_token: str
) -> None:
    admin_session = session_of_token(admin_token)
    old = seconds_ago(120)
    set_session(admin_session, last_activity_at=old)

    response = client.get(
        "/api/v1/admin/monitor/sessions", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert get_session(admin_session).last_activity_at == old


def test_list_refresh_requires_explicit_marker(
    client: TestClient, admin_token: str
) -> None:
    admin_session = session_of_token(admin_token)
    old = seconds_ago(120)
    set_session(admin_session, last_activity_at=old)

    poll = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert poll.status_code == 200
    assert get_session(admin_session).last_activity_at == old

    manual = client.get(
        "/api/v1/admin/users",
        headers={**auth_headers(admin_token), "X-Admin-Activity": "explicit"},
    )
    assert manual.status_code == 200
    assert get_session(admin_session).last_activity_at > old


def test_activity_write_failure_is_non_blocking(
    client: TestClient, tracked_user, monkeypatch, caplog
) -> None:
    from app.api import deps

    _, _, token, session_id = tracked_user
    set_session(session_id, last_activity_at=seconds_ago(120))

    def _boom(*args, **kwargs):
        raise OperationalError("UPDATE", {}, Exception("db down"))

    monkeypatch.setattr(deps, "update", _boom)

    with caplog.at_level("WARNING"):
        response = client.get("/api/v1/getInfo", headers=auth_headers(token))

    assert response.status_code == 200, response.text
    assert "会话活动时间更新失败" in caplog.text
    # 失败不影响鉴权结果，也不改数据库。
    assert get_session(session_id).last_activity_at <= seconds_ago(100)
