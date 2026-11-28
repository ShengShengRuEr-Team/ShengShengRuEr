"""Official-adapter transport tests with synthetic keys, no external calls."""

import json
from contextlib import nullcontext
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr


@pytest.fixture
def provider_context(context, monkeypatch):
    from app.db.base import SessionLocal
    from app.module3 import llm
    from app.services.processing import tasks

    settings = context["settings"]
    monkeypatch.setattr(
        settings, "deepseek_api_key", SecretStr("synthetic-deepseek-key")
    )
    monkeypatch.setattr(
        settings, "dashscope_api_key", SecretStr("synthetic-bailian-key")
    )
    monkeypatch.setattr(settings, "m3_cny_usd_rate", 0.15)
    monkeypatch.setattr(
        settings,
        "m3_cny_usd_rate_source",
        "Synthetic transport-test rate; not production evidence",
    )
    monkeypatch.setattr(
        settings, "m3_cny_usd_rate_effective_at", "2026-11-24T00:00:00+00:00"
    )
    monkeypatch.setattr(llm, "cluster_budget_lock", nullcontext)
    monkeypatch.setattr(llm, "external_commitments", lambda _: [Decimal(0)] * 4)
    with SessionLocal() as db:
        task = tasks.get_task(db, UUID(context["task_id"]))
        task.request = {
            **task.request,
            "exam_paper": {
                **task.request["exam_paper"],
                "paper_set": uuid4().int % 100000 + 100,
            },
        }
        db.commit()
    return context


@pytest.mark.parametrize("provider", ["deepseek", "bailian"])
def test_official_request_parameters_and_original_currency(provider_context, provider):
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm, providers

    context = provider_context
    settings = context["settings"]
    method = providers.freeze(provider, settings)
    calls = []

    def transport(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == providers.ENDPOINTS[method["official_endpoint_id"]]
        assert body["model"] == method["requested_model"]
        assert body["max_tokens"] == 4096
        assert body["stream"] is False
        if provider == "bailian":
            assert body["enable_thinking"] is False
            assert "thinking" not in body
        return httpx.Response(
            200,
            json={
                "model": method["requested_model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"candidate":"synthetic"}'},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    parsed, receipt = llm.request_json(
        UUID(context["task_id"]),
        "different-run-key",
        "run",
        "Return JSON",
        {"input": "synthetic"},
        settings,
        transport=httpx.MockTransport(transport),
        provider_manifest=method,
    )
    assert parsed == {"candidate": "synthetic"}
    assert len(calls) == 1
    with SessionLocal() as db:
        attempt = db.get(LlmAttempt, receipt["attempt_id"])
        assert attempt.provider == provider
        assert attempt.currency == method["currency"]
        assert attempt.original_charged > 0
        assert attempt.charged_usd > 0
        assert attempt.billing_status == "estimated"
        assert attempt.paper_budget_key
        assert "synthetic-bailian-key" not in json.dumps(attempt.request_payload)


def test_transport_failure_has_one_attempt_and_unknown_reservation(provider_context):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm, providers
    from app.module3.contracts import ProcessingError

    context = provider_context
    settings = context["settings"]
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("Synthetic timeout")

    with pytest.raises(ProcessingError, match="未知消耗"):
        llm.request_json(
            UUID(context["task_id"]),
            "timeout-run",
            "run",
            "Return JSON",
            {},
            settings,
            transport=httpx.MockTransport(timeout),
            provider_manifest=providers.freeze("bailian", settings),
        )
    assert len(calls) == 1
    with SessionLocal() as db:
        attempt = db.scalar(
            select(LlmAttempt).where(LlmAttempt.task_id == UUID(context["task_id"]))
        )
        assert attempt.billing_status == "unknown"
        assert attempt.charged_usd is None
        assert attempt.reserved_usd > 0


def test_qwen_rejects_missing_price_basis_and_changed_manifest(
    provider_context, monkeypatch
):
    from app.module3 import providers
    from app.module3.contracts import ProcessingError

    settings = provider_context["settings"]
    frozen = providers.freeze("bailian", settings)
    with pytest.raises(ProcessingError):
        providers.check_manifest(
            {**frozen, "official_endpoint_id": "https://untrusted.invalid"}
        )
    monkeypatch.setattr(settings, "m3_cny_usd_rate_source", "")
    with pytest.raises(ProcessingError, match="汇率"):
        providers.freeze("bailian", settings)


def test_different_models_and_run_keys_share_paper_budget(
    provider_context, monkeypatch
):
    from app.module3 import llm, providers
    from app.module3.contracts import ProcessingError

    context = provider_context
    settings = context["settings"]
    task_id = UUID(context["task_id"])
    monkeypatch.setattr(settings, "m3_run_budget_usd", 0.006)
    llm.reserve(
        task_id,
        "first-model-run",
        "run",
        {},
        settings,
        provider_manifest=providers.freeze("deepseek", settings),
    )
    with pytest.raises(ProcessingError, match="预算"):
        llm.reserve(
            task_id,
            "second-model-new-run",
            "run",
            {},
            settings,
            provider_manifest=providers.freeze("bailian", settings),
        )


def test_authorized_uncapped_calls_keep_reservations_and_audit(
    provider_context, monkeypatch
):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm, providers
    from app.module3.contracts import ProcessingError

    settings = provider_context["settings"]
    task_id = UUID(provider_context["task_id"])
    monkeypatch.setattr(settings, "m3_budget_enforced", False)
    monkeypatch.setattr(
        settings,
        "m3_budget_override_reference",
        "Synthetic explicit uncapped authorization",
    )
    monkeypatch.setattr(settings, "m3_total_budget_usd", 0.00001)
    monkeypatch.setattr(settings, "m3_run_budget_usd", 0.00001)
    monkeypatch.setattr(
        llm,
        "external_commitments",
        lambda _: [Decimal(100), Decimal(100), Decimal(100), 2],
    )
    manifest = providers.freeze("deepseek", settings)
    attempt_id = llm.reserve(
        task_id, "uncapped-synthetic", "run", {}, settings, provider_manifest=manifest
    )
    with SessionLocal() as db:
        row = db.get(LlmAttempt, attempt_id)
        assert row.reserved_usd > 0 and row.charged_usd is None
        assert row.billing_status == "unknown"
        assert row.provider_manifest["budget_policy"] == {
            "enforced": False,
            "override_reference": "Synthetic explicit uncapped authorization",
        }
    monkeypatch.setattr(settings, "m3_budget_enforced", True)
    with pytest.raises(ProcessingError, match="授权"):
        llm.reserve(
            task_id, "wrong-runtime", "run", {}, settings, provider_manifest=manifest
        )
    with SessionLocal() as db:
        assert (
            len(
                db.scalars(
                    select(LlmAttempt).where(LlmAttempt.task_id == task_id)
                ).all()
            )
            == 1
        )


def test_disabling_limits_requires_an_explicit_reference():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="授权"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://test:test@localhost/test",
            jwt_secret_key="s" * 40,
            m3_budget_enforced=False,
        )
