"""T07a：留存调度表结构、种子与迁移链（主文档 §5.3）。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.fixture
def db():
    from app.db.base import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _columns(db, table: str) -> set[str]:
    return set(
        db.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        ).scalars()
    )


def _indexes(db, table: str) -> set[str]:
    return set(
        db.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename=:t"),
            {"t": table},
        ).scalars()
    )


def _constraints(db, table: str) -> set[str]:
    return set(
        db.execute(
            text(
                "SELECT c.conname FROM pg_constraint c"
                " JOIN pg_class t ON t.oid = c.conrelid"
                " WHERE t.relname = :t"
            ),
            {"t": table},
        ).scalars()
    )


def test_job_tables_exist_with_expected_columns(db) -> None:
    assert _columns(db, "admin_job_definitions") == {
        "job_id",
        "enabled",
        "timezone",
        "next_scheduled_at",
        "last_scheduled_slot",
        "last_run_id",
        "active_run_id",
        "missed_slots",
        "updated_at",
    }
    assert _columns(db, "admin_job_runs") == {
        "id",
        "job_id",
        "trigger",
        "slot_key",
        "actor_id",
        "state",
        "queued_at",
        "started_at",
        "finished_at",
        "heartbeat_at",
        "attempt_count",
        "retry_at",
        "retry_pending",
        "counts",
        "counts_complete",
        "error_code",
        "created_at",
    }
    assert _columns(db, "admin_job_scheduler_state") == {
        "instance_id",
        "booted_at",
        "heartbeat_at",
        "last_error_code",
        "state",
        "version",
    }


def test_job_constraints_and_indexes(db) -> None:
    run_constraints = _constraints(db, "admin_job_runs")
    for name in (
        "ck_admin_job_runs_trigger",
        "ck_admin_job_runs_slot_rule",
        "ck_admin_job_runs_state",
        "ck_admin_job_runs_attempt_count",
        "fk_admin_job_runs_actor_id_users",
    ):
        assert name in run_constraints, name

    definition_constraints = _constraints(db, "admin_job_definitions")
    assert "ck_admin_job_definitions_job_id" in definition_constraints
    assert "ck_admin_job_definitions_missed_slots" in definition_constraints

    run_indexes = _indexes(db, "admin_job_runs")
    assert {"uq_admin_job_runs_slot", "uq_admin_job_runs_active"} <= run_indexes
    assert "ix_admin_job_runs_job_created" in run_indexes
    assert "pk_admin_job_runs" in run_indexes

    assert "ix_admin_job_scheduler_state_heartbeat" in _indexes(
        db, "admin_job_scheduler_state"
    )


def test_seed_definition_row(db) -> None:
    row = db.execute(
        text(
            "SELECT job_id, enabled, timezone, missed_slots,"
            " active_run_id, last_run_id, next_scheduled_at"
            " FROM admin_job_definitions"
        )
    ).one()
    assert row.job_id == "admin.retention_cleanup"
    assert row.enabled is True
    assert row.timezone == "Asia/Shanghai"
    assert row.missed_slots == 0
    assert row.active_run_id is None
    assert row.last_run_id is None
    # 由调度进程启动时计算并持久化。
    assert row.next_scheduled_at is None

    count = db.execute(
        text("SELECT count(*) FROM admin_job_definitions")
    ).scalar()
    assert count == 1


def test_single_head_is_0008() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == ["0008_admin_retention_scheduler"]


def test_schedule_helpers_use_asia_shanghai() -> None:
    from app.core.admin_jobs import (
        latest_slot_before,
        next_run_after,
        slot_key_for,
    )

    morning = datetime(2026, 11, 17, 2, 0, tzinfo=UTC)  # 北京 10:00
    assert next_run_after(morning).isoformat().startswith("2026-11-18T03:10:00+08:00")
    assert latest_slot_before(morning).isoformat().startswith(
        "2026-11-17T03:10:00+08:00"
    )
    assert slot_key_for(morning).isoformat() == "2026-11-17"

    early = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)  # 北京 02:00
    assert next_run_after(early).isoformat().startswith("2026-11-17T03:10:00+08:00")
    assert latest_slot_before(early).isoformat().startswith(
        "2026-11-16T03:10:00+08:00"
    )
