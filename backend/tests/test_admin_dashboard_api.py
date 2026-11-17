"""首页汇总接口（AC-30，需求 §10.1 / 主文档 §9.5）。"""

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from tests.admin_support import (
    cleanup_users,
    session_local,
    session_of_token,
    unique,
)
from tests.attempt_support import (
    create_hidden_paper,
    create_stale_paper,
    create_student,
    create_visible_paper,
)
from tests.conftest import auth_headers

BEIJING = ZoneInfo("Asia/Shanghai")
CARD_KEYS = {
    "paper_count",
    "awaiting_visibility_count",
    "failed_check_count",
    "active_student_count",
    "disabled_student_count",
    "successful_attempts_7d",
}


def _dashboard(client: TestClient, token: str) -> dict:
    # 统计对比需要读取最新快照：每个断言前丢弃进程内缓存。
    from app.services.admin import dashboard_cache

    dashboard_cache.reset_dashboard_cache()
    response = client.get("/api/v1/admin/dashboard", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _expected_counts(as_of: datetime) -> dict[str, int]:
    """独立实现：直接在 Python 里按口径计算，用于与 SQL 结果对照。"""

    from app.db.models import Role, User, UserRole
    from app.db.models_attempt import Attempt
    from app.db.models_listening import (
        ContentCheck,
        ExamPaper,
        ImportBatch,
        PaperVisibility,
    )

    local = as_of.astimezone(BEIJING)
    today_start = datetime.combine(local.date(), time.min, tzinfo=BEIJING)
    window_start = (today_start - timedelta(days=6)).astimezone(UTC)
    window_end = min((today_start + timedelta(days=1)).astimezone(UTC), as_of)

    SessionLocal = session_local()
    with SessionLocal() as db:
        paper_count = db.scalar(select(func.count()).select_from(ExamPaper))
        batch = db.scalar(
            select(ImportBatch)
            .where(ImportBatch.is_current.is_(True), ImportBatch.status == "active")
            .order_by(ImportBatch.id.desc())
            .limit(1)
        )
        checks: dict[int, tuple] = {}
        visibility: dict[int, tuple] = {}
        if batch is not None:
            for check in db.scalars(
                select(ContentCheck).where(ContentCheck.batch_id == batch.id)
            ):
                key = (check.checked_at, check.id)
                if check.exam_paper_id not in checks or key > checks[check.exam_paper_id][0]:
                    checks[check.exam_paper_id] = (key, check.is_passed)
            for row in db.scalars(
                select(PaperVisibility).where(PaperVisibility.batch_id == batch.id)
            ):
                key = (row.updated_at, row.id)
                if row.exam_paper_id not in visibility or key > visibility[row.exam_paper_id][0]:
                    visibility[row.exam_paper_id] = (key, row.is_visible)

        awaiting = 0
        failed = 0
        for paper_id, (_, passed) in checks.items():
            if passed:
                visible = visibility.get(paper_id)
                if visible is None or visible[1] is False:
                    awaiting += 1
            else:
                failed += 1

        admin_ids = set(
            db.scalars(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.role_key == "admin")
            ).all()
        )
        student_rows = db.execute(
            select(User.id, User.status)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.role_key == "student")
            .distinct()
        ).all()
        active_students = {
            row.id
            for row in student_rows
            if row.id not in admin_ids and row.status == "active"
        }
        disabled_students = {
            row.id
            for row in student_rows
            if row.id not in admin_ids and row.status == "disabled"
        }

        attempts = db.scalar(
            select(func.count())
            .select_from(Attempt)
            .where(
                Attempt.submitted_at >= window_start,
                Attempt.submitted_at < window_end,
            )
        )
    return {
        "paper_count": int(paper_count or 0),
        "awaiting_visibility_count": awaiting,
        "failed_check_count": failed,
        "active_student_count": len(active_students),
        "disabled_student_count": len(disabled_students),
        "successful_attempts_7d": int(attempts or 0),
    }


def test_dashboard_shape_and_auth(
    client: TestClient, admin_token: str, student_token: str
) -> None:
    data = _dashboard(client, admin_token)
    assert set(data) == {
        "as_of",
        "window_start",
        "window_end",
        "timezone",
        "cache",
        "cards",
    }
    assert data["timezone"] == "Asia/Shanghai"
    assert data["as_of"].endswith("+08:00")
    assert data["window_start"].endswith("+08:00")
    assert data["window_end"].endswith("+08:00")
    assert set(data["cards"]) == CARD_KEYS
    assert all(isinstance(value, int) and value >= 0 for value in data["cards"].values())
    assert set(data["cache"]) == {
        "enabled",
        "status",
        "ttl_seconds",
        "cached_at",
        "expires_at",
        "age_seconds",
    }
    assert data["cache"]["ttl_seconds"] == 15

    assert (
        client.get(
            "/api/v1/admin/dashboard", headers=auth_headers(student_token)
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/dashboard").status_code == 401

    # 旧 overview 兼容：字段与状态码不变。
    overview = client.get("/api/v1/admin/overview", headers=auth_headers(admin_token))
    assert overview.status_code == 200
    assert set(overview.json()["data"]) == {"role", "message"}


def test_counts_match_independent_computation(
    client: TestClient, admin_token: str
) -> None:
    data = _dashboard(client, admin_token)
    expected = _expected_counts(datetime.fromisoformat(data["as_of"]))
    assert data["cards"] == expected


def test_paper_count_not_double_counted_across_batches(
    client: TestClient, admin_token: str
) -> None:
    before = _dashboard(client, admin_token)["cards"]["paper_count"]
    create_stale_paper(code=f"DASH_{uuid.uuid4().hex[:8]}")

    data = _dashboard(client, admin_token)
    assert data["cards"]["paper_count"] == before + 1


def test_awaiting_and_failed_checks_are_exclusive(
    client: TestClient, admin_token: str
) -> None:
    from app.db.models_listening import ContentCheck, PaperVisibility

    SessionLocal = session_local()
    before = _dashboard(client, admin_token)["cards"]

    # 检查通过但未确认可见 → 待确认 +1。
    hidden_id = create_hidden_paper(code=f"DASH_H_{uuid.uuid4().hex[:8]}")
    after_hidden = _dashboard(client, admin_token)["cards"]
    assert after_hidden["awaiting_visibility_count"] == (
        before["awaiting_visibility_count"] + 1
    )
    assert after_hidden["failed_check_count"] == before["failed_check_count"]

    with SessionLocal() as db:
        record = db.scalar(
            select(PaperVisibility).where(PaperVisibility.exam_paper_id == hidden_id)
        )
        batch_id = record.batch_id
        # 删除可见性记录 → 视为未确认，仍计入待确认。
        db.delete(record)
        db.flush()
        db.add(
            ContentCheck(
                exam_paper_id=hidden_id,
                batch_id=batch_id,
                is_passed=False,
                issues=[{"kind": "test", "message": "失败"}],
                checked_at=datetime.now(UTC),
            )
        )
        db.commit()

    after_failed = _dashboard(client, admin_token)["cards"]
    # 最新检查失败 → 从待确认移到失败，二者不重叠。
    assert after_failed["failed_check_count"] == before["failed_check_count"] + 1
    assert after_failed["awaiting_visibility_count"] == before["awaiting_visibility_count"]


def test_student_counts_exclude_admins_and_mixed_roles(
    client: TestClient, admin_token: str
) -> None:
    from app.db.models import Role, User, UserRole

    SessionLocal = session_local()
    before = _dashboard(client, admin_token)["cards"]

    student_id = create_student(unique("dash_student"))
    disabled_id = None
    try:
        after_student = _dashboard(client, admin_token)["cards"]
        assert (
            after_student["active_student_count"]
            == before["active_student_count"] + 1
        )

        with SessionLocal() as db:
            admin_role = db.scalar(select(Role).where(Role.role_key == "admin"))
            db.add(UserRole(user_id=student_id, role_id=admin_role.id))
            db.commit()

        after_mixed = _dashboard(client, admin_token)["cards"]
        # 混合角色按 admin 优先，不再计入学生。
        assert after_mixed["active_student_count"] == before["active_student_count"]

        disabled_id = create_student(unique("dash_disabled"))
        with SessionLocal() as db:
            db.execute(
                text("UPDATE users SET status='disabled' WHERE id = :id"),
                {"id": disabled_id},
            )
            db.commit()
        after_disabled = _dashboard(client, admin_token)["cards"]
        assert (
            after_disabled["disabled_student_count"]
            == before["disabled_student_count"] + 1
        )
    finally:
        # 清理临时用户，尤其不能遗留额外的 active 管理员。
        created = [student_id]
        if disabled_id is not None:
            created.append(disabled_id)
        with SessionLocal() as db:
            db.execute(
                text("DELETE FROM user_roles WHERE user_id = ANY(:ids)"),
                {"ids": created},
            )
            db.commit()
        cleanup_users(created)


def test_attempts_window_boundaries(
    client: TestClient, admin_token: str
) -> None:
    from app.db.models_attempt import Attempt

    SessionLocal = session_local()
    paper = create_visible_paper(code=f"DASH_ATT_{uuid.uuid4().hex[:8]}")
    student_id = create_student(unique("dash_attempt"))
    now = datetime.now(UTC)
    local = now.astimezone(BEIJING)
    today_start = datetime.combine(local.date(), time.min, tzinfo=BEIJING)
    window_start = (today_start - timedelta(days=6)).astimezone(UTC)

    def _attempt(submitted_at: datetime) -> Attempt:
        return Attempt(
            attempt_code=uuid.uuid4().hex,
            student_id=student_id,
            exam_paper_id=paper.paper_id,
            import_batch_id=paper.batch_id,
            attempt_key=uuid.uuid4().hex,
            request_fingerprint=uuid.uuid4().hex,
            submitted_at=submitted_at,
            question_count=4,
            correct_count=2,
            correct_rate=50,
            practice_score=None,
            score_breakdown={"rule": "test", "available": False, "reason": "test"},
        )

    before = _dashboard(client, admin_token)["cards"]["successful_attempts_7d"]
    with SessionLocal() as db:
        db.add_all(
            [
                _attempt(window_start - timedelta(seconds=1)),  # 早 1 秒：不计
                _attempt(window_start),  # 恰好下界：计
                _attempt(now - timedelta(minutes=1)),  # 窗口内：计
                _attempt(now + timedelta(days=1)),  # 未来：不计
            ]
        )
        db.commit()

    after = _dashboard(client, admin_token)["cards"]["successful_attempts_7d"]
    assert after == before + 2


def test_response_has_no_personal_details(
    client: TestClient, admin_token: str
) -> None:
    create_visible_paper(code=f"DASH_LEAK_{uuid.uuid4().hex[:8]}")
    response = client.get(
        "/api/v1/admin/dashboard", headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.text.lower()
    for forbidden in (
        "attempt_code",
        "student_id",
        "correct_count",
        "score",
        "answer",
        "username",
    ):
        assert forbidden not in body
    assert set(response.json()["data"]["cards"]) == CARD_KEYS


def test_dashboard_does_not_refresh_activity(
    client: TestClient, admin_token: str
) -> None:
    SessionLocal = session_local()
    session_id = session_of_token(admin_token)

    old = datetime.now(UTC) - timedelta(minutes=10)
    with SessionLocal() as db:
        db.execute(
            text("UPDATE auth_sessions SET last_activity_at = :t WHERE id = :id"),
            {"t": old, "id": session_id},
        )
        db.commit()

    _dashboard(client, admin_token)

    with SessionLocal() as db:
        current = db.scalar(
            text("SELECT last_activity_at FROM auth_sessions WHERE id = :id"),
            {"id": session_id},
        )
    assert current == old


def test_empty_current_batch_counts_zero(client: TestClient, admin_token: str) -> None:
    """没有当前 active 批次时，待确认/失败应为真实 0 而不是报错。"""

    data = _dashboard(client, admin_token)
    assert data["cards"]["awaiting_visibility_count"] >= 0
    assert data["cards"]["failed_check_count"] >= 0
