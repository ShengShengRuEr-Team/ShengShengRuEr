"""Fault injection, real database ownership constraints and persistent budgets."""

from uuid import UUID

import pytest


@pytest.mark.parametrize(
    "status,count", [(401, 1), (403, 1), (429, 3), (500, 3), (503, 3)]
)
def test_a17_http_retry_limit_and_unknown_billing(context, monkeypatch, status, count):
    import httpx
    from pydantic import SecretStr
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm
    from app.module3.contracts import ProcessingError

    monkeypatch.setattr(
        context["settings"], "deepseek_api_key", SecretStr("synthetic-key")
    )
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json={"error": "synthetic"})

    with pytest.raises(ProcessingError):
        llm.request_json(
            UUID(context["task_id"]),
            context["task_id"],
            "sample",
            "JSON",
            {},
            context["settings"],
            transport=httpx.MockTransport(handler),
        )
    assert len(seen) == count
    with SessionLocal() as db:
        rows = db.scalars(
            select(LlmAttempt).where(LlmAttempt.task_id == UUID(context["task_id"]))
        ).all()
        assert len(rows) == count
        assert all(
            r.billing_status == "unknown"
            and r.charged_usd is None
            and r.reserved_usd > 0
            for r in rows
        )


def test_a17_budget_stops_before_request(context, monkeypatch):
    import httpx
    from pydantic import SecretStr

    from app.module3 import llm
    from app.module3.contracts import ProcessingError

    monkeypatch.setattr(
        context["settings"], "deepseek_api_key", SecretStr("synthetic-key")
    )
    monkeypatch.setattr(context["settings"], "m3_total_budget_usd", 0.00001)

    def handler(request):
        pytest.fail("budget violation must be stopped before network")

    with pytest.raises(ProcessingError, match="预算"):
        llm.request_json(
            UUID(context["task_id"]),
            context["task_id"],
            "sample",
            "JSON",
            {},
            context["settings"],
            transport=httpx.MockTransport(handler),
        )


def test_a17_timeout_reservation_not_zeroed(context, monkeypatch):
    import httpx
    from pydantic import SecretStr
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm
    from app.module3.contracts import ProcessingError

    monkeypatch.setattr(
        context["settings"], "deepseek_api_key", SecretStr("synthetic-key")
    )
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)

    def handler(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with pytest.raises(ProcessingError):
        llm.request_json(
            UUID(context["task_id"]),
            context["task_id"],
            "sample",
            "JSON",
            {},
            context["settings"],
            transport=httpx.MockTransport(handler),
        )
    with SessionLocal() as db:
        rows = db.scalars(
            select(LlmAttempt).where(LlmAttempt.task_id == UUID(context["task_id"]))
        ).all()
        assert len(rows) == 3 and all(
            r.charged_usd is None and r.reserved_usd > 0 for r in rows
        )


def test_a07_concurrent_claim_skips_locked_task(context):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_processing import ProcessingTask
    from app.services.processing.tasks import claim_task

    with SessionLocal() as first, SessionLocal() as second:
        task = claim_task(first, "first-worker")
        assert task is not None
        other = claim_task(second, "second-worker")
        assert other is None or other.id != task.id
        assert (
            first.scalar(
                select(ProcessingTask).where(ProcessingTask.id == task.id)
            ).worker_id
            == "first-worker"
        )
        first.rollback()
        second.rollback()


def test_a08_database_unavailable_returns_503(context, client):
    from sqlalchemy.exc import OperationalError

    from app.db.base import get_db
    from app.main import app

    def unavailable():
        raise OperationalError("synthetic", {}, Exception("database unavailable"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = unavailable
    try:
        response = client.get(
            "/api/v1/admin/processing-tasks", headers=context["headers"]
        )
        assert response.status_code == 503
        assert "synthetic" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_a21_database_rejects_cross_batch_evidence(persisted):
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.db.base import SessionLocal
    from app.db.models_annotations import EvidenceItem, EvidenceSegment
    from app.db.models_listening import ImportBatch, TranscriptSegment

    c = persisted
    with SessionLocal() as db:
        evidence = db.scalar(
            select(EvidenceItem).where(EvidenceItem.batch_id == c["batch_id"])
        )
        segment = db.scalar(
            select(TranscriptSegment).where(TranscriptSegment.batch_id == c["batch_id"])
        )
        other = ImportBatch(
            exam_paper_id=c["paper_id"], batch_code="X" + c["task_id"], status="pending"
        )
        db.add(other)
        db.flush()
        db.add(
            EvidenceSegment(
                evidence_id=evidence.id,
                batch_id=other.id,
                passage_id=evidence.passage_id,
                segment_id=segment.id,
                sort_order=99,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_a28_a30_cleanup_preserves_reused_file(context, tmp_path):
    from app.services.processing.persistence import cleanup_failed_files, publish_audio

    directory = tmp_path / "publish"
    first, created = publish_audio(
        context["audio"], directory, context["payload"]["audio"]
    )
    assert created
    reused, created_again = publish_audio(
        context["audio"], directory, context["payload"]["audio"]
    )
    assert reused == first and not created_again
    cleanup_failed_files([])
    assert first.exists()
    cleanup_failed_files([(first, context["audio_hash"])])
    assert not first.exists()


def test_a31_media_full_hash_and_ranges(persisted, client, student_token):
    import hashlib

    from tests.module3.test_processing import approve_fixture

    c = persisted
    check = approve_fixture(client, c)
    response = client.post(
        f"/api/v1/admin/listening-papers/{c['paper_id']}/current-batch",
        headers=c["headers"],
        json={
            "task_id": c["task_id"],
            "batch_id": c["batch_id"],
            "check_id": check["id"],
            "result_hash": c["result_hash"],
            "expected_current_batch_id": None,
        },
    )
    assert response.status_code == 200
    visible = f"/api/v1/admin/listening-papers/{c['paper_id']}/visibility"
    assert (
        client.post(
            visible,
            headers=c["headers"],
            json={"action": "confirm", "reason": "synthetic"},
        ).status_code
        == 200
    )
    url = f"/api/v1/listening-papers/{c['paper_id']}/audio"
    headers = {"Authorization": "Bearer " + student_token}
    response = client.get(url, headers=headers)
    assert (
        response.status_code == 200
        and hashlib.sha256(response.content).hexdigest() == c["audio_hash"]
    )
    assert (
        client.get(url, headers={**headers, "Range": "bytes=1-12"}).status_code == 206
    )
    assert (
        client.get(url, headers={**headers, "Range": "bytes=99999999-"}).status_code
        == 416
    )
