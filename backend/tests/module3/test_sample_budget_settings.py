"""The authorized override changes the sample ceiling, never other limits."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def settings(**overrides):
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://synthetic@localhost/synthetic",
        jwt_secret_key="synthetic-budget-settings-0123456789abcdef",
        **overrides,
    )


def test_sample_default_and_authorized_ceiling(monkeypatch):
    for key in (
        "M3_SAMPLE_BUDGET_USD",
        "M3_RUN_BUDGET_USD",
        "M3_TOTAL_BUDGET_USD",
    ):
        monkeypatch.delenv(key, raising=False)
    original = settings()
    authorized = settings(m3_sample_budget_usd=0.75)
    assert original.m3_sample_budget_usd == 0.5
    assert authorized.m3_sample_budget_usd == 0.75
    assert original.m3_run_budget_usd == authorized.m3_run_budget_usd == 2.0
    assert original.m3_total_budget_usd == authorized.m3_total_budget_usd == 5.0


@pytest.mark.parametrize(
    "override",
    [
        {"m3_sample_budget_usd": 0.75001},
        {"m3_run_budget_usd": 2.00001},
        {"m3_total_budget_usd": 5.00001},
    ],
)
def test_authorized_sample_change_does_not_remove_hard_limits(override):
    with pytest.raises(ValidationError):
        settings(**override)
