"""Configuration visibility is administrator-only, read-only and secret-free."""

import pytest
from pydantic import SecretStr

from app.core.config import get_settings

URL = "/api/v1/admin/library-providers"


def test_provider_configuration_requires_admin(client, student_token):
    assert client.get(URL).status_code == 401
    assert (
        client.get(
            URL, headers={"Authorization": "Bearer " + student_token}
        ).status_code
        == 403
    )


def test_provider_configuration_does_not_expose_credentials(
    client, admin_token, monkeypatch
):
    settings = get_settings()
    for name in ("deepseek_api_key", "dashscope_api_key"):
        monkeypatch.setattr(
            settings, name, SecretStr("secret-marker-must-never-leave-server")
        )
    monkeypatch.setattr(settings, "m3_qwen_region", "beijing")
    monkeypatch.setattr(settings, "m3_cny_usd_rate", 0.15)
    monkeypatch.setattr(
        settings, "m3_cny_usd_rate_source", "Synthetic configuration evidence"
    )
    monkeypatch.setattr(
        settings, "m3_cny_usd_rate_effective_at", "2026-11-24T09:15:00+08:00"
    )
    response = client.get(URL, headers={"Authorization": "Bearer " + admin_token})
    assert response.status_code == 200
    assert "secret-marker" not in response.text
    data = response.json()["data"]
    assert data["connectivity_checked"] is False
    assert all(item["configuration_ready"] for item in data["items"])
    assert data["items"][1]["usd_per_currency"] == "0.15"


@pytest.mark.parametrize("fault", ["credentials", "rate", "timezone", "region"])
def test_qwen_configuration_reports_the_actionable_blocker(
    client, admin_token, monkeypatch, fault
):
    settings = get_settings()
    values = {
        "dashscope_api_key": SecretStr("synthetic-only"),
        "m3_qwen_region": "beijing",
        "m3_cny_usd_rate": 0.15,
        "m3_cny_usd_rate_source": "Synthetic evidence",
        "m3_cny_usd_rate_effective_at": "2026-11-24T09:15:00+08:00",
    }
    values.update(
        {
            "credentials": {"dashscope_api_key": None},
            "rate": {"m3_cny_usd_rate": None},
            "timezone": {"m3_cny_usd_rate_effective_at": "2026-11-24T09:15:00"},
            "region": {"m3_qwen_region": "unsupported"},
        }[fault]
    )
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    response = client.get(URL, headers={"Authorization": "Bearer " + admin_token})
    assert response.status_code == 200
    item = response.json()["data"]["items"][1]
    assert not item["configuration_ready"]
    assert (
        item["issues"][0]["code"]
        == {
            "credentials": "CREDENTIALS_MISSING",
            "rate": "PRICE_CONFIGURATION_REQUIRED",
            "timezone": "PRICE_CONFIGURATION_REQUIRED",
            "region": "PROVIDER_REGION_UNSUPPORTED",
        }[fault]
    )
