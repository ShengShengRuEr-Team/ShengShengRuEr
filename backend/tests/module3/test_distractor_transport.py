"""Fault injection for response completion, raw retention and cost accounting."""

import json
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select


@pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
def test_ec21_ec22_incomplete_response_keeps_raw_and_cost(
    context, monkeypatch, finish_reason
):
    from app.db.base import SessionLocal
    from app.db.models_processing import LlmAttempt
    from app.module3 import llm
    from app.module3.contracts import ProcessingError
    from app.module3.generation_config import MAX_OUTPUT

    monkeypatch.setattr(
        context["settings"], "deepseek_api_key", SecretStr("synthetic-key")
    )
    raw = {
        "model": "synthetic-completion-model",
        "choices": [
            {
                "finish_reason": finish_reason,
                # Valid JSON must still be rejected if completion is not stop.
                "message": {"content": '{"distractor_assessments": []}'},
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 100},
    }
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=raw)

    with pytest.raises(ProcessingError) as error:
        llm.request_json(
            UUID(context["task_id"]),
            context["task_id"],
            "sample",
            "Return strict JSON",
            {},
            context["settings"],
            transport=httpx.MockTransport(handler),
        )
    assert error.value.code == "LLM_RESPONSE_INVALID"
    assert len(requests) == 1
    assert requests[0]["max_tokens"] == MAX_OUTPUT == 4096
    with SessionLocal() as db:
        rows = db.scalars(
            select(LlmAttempt).where(LlmAttempt.task_id == UUID(context["task_id"]))
        ).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.response_payload == raw
        assert row.request_payload == requests[0]
        assert row.status == "failed"
        assert row.error_code == "LLM_RESPONSE_INVALID"
        assert row.billing_status == "estimated"
        assert row.charged_usd > 0
        assert row.reserved_usd >= row.charged_usd
        assert row.output_tokens == 100
