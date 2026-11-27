"""Official text-only adapters and versioned, conservative price manifests."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.module3.contracts import ProcessingError, file_hash, fingerprint
from app.module3.generation_config import generation_parameters

ENDPOINTS = {
    "deepseek-official": "https://api.deepseek.com/chat/completions",
    "bailian-beijing": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    "bailian-singapore": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
}
PRICE_DATE = "2026-11-24"


def freeze(provider, settings):
    if provider == "deepseek":
        value = {
            "provider": provider,
            "official_endpoint_id": "deepseek-official",
            "region": "official",
            "requested_model": "deepseek-flash",
            "resolved_version": "DeepSeek-V4.1-Flash-1017",
            "parameters": generation_parameters(),
            "currency": "USD",
            "input_per_million": "0.30",
            "cache_input_per_million": "0.006",
            "output_per_million": "1.20",
            "usd_per_currency": "1",
            "exchange_rate_source": "USD",
            "exchange_rate_effective_at": PRICE_DATE,
            "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
        }
    elif provider == "bailian":
        region = settings.m3_qwen_region
        if region not in {"beijing", "singapore"}:
            raise ProcessingError(
                "PROVIDER_REGION_UNSUPPORTED", "仅冻结北京与新加坡官方地域配置"
            )
        if not (
            settings.m3_cny_usd_rate
            and settings.m3_cny_usd_rate_source
            and settings.m3_cny_usd_rate_effective_at
        ):
            raise ProcessingError(
                "PRICE_CONFIGURATION_REQUIRED",
                "千问须先登记可信人民币换美元汇率、来源和生效时刻",
            )
        try:
            effective = datetime.fromisoformat(settings.m3_cny_usd_rate_effective_at)
            if effective.tzinfo is None:
                raise ValueError
        except ValueError:
            raise ProcessingError(
                "PRICE_CONFIGURATION_REQUIRED", "汇率生效时刻必须包含时区"
            ) from None
        value = {
            "provider": provider,
            "official_endpoint_id": f"bailian-{region}",
            "region": region,
            "requested_model": "qwen3.8-flash",
            "resolved_version": "qwen3.8-flash (alias; actual response retained)",
            "parameters": {
                "model": "qwen3.8-flash",
                "enable_thinking": False,
                "temperature": 0,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"},
                "stream": False,
            },
            "currency": "CNY",
            "input_per_million": "0.8" if region == "beijing" else "1.094",
            "cache_input_per_million": "0.1" if region == "beijing" else "0.117",
            "output_per_million": "2.7" if region == "beijing" else "3.427",
            "usd_per_currency": str(settings.m3_cny_usd_rate),
            "exchange_rate_source": settings.m3_cny_usd_rate_source,
            "exchange_rate_effective_at": settings.m3_cny_usd_rate_effective_at,
            "price_source": "https://help.aliyun.com/en/model-studio/qwen3-8-flash",
        }
    else:
        raise ProcessingError("PROVIDER_UNSUPPORTED", "只能选择已冻结的两家官方模型")
    enforced = getattr(settings, "m3_budget_enforced", True)
    reference = getattr(settings, "m3_budget_override_reference", "").strip()
    if not enforced and not reference:
        raise ProcessingError(
            "BUDGET_OVERRIDE_REQUIRED", "取消预算上限须有明确授权记录"
        )
    value.update(
        budget_policy={
            "enforced": enforced,
            "override_reference": reference if not enforced else None,
        },
        price_version=f"{provider}-{PRICE_DATE}",
        timeout_seconds=120,
        concurrency=1,
        maximum_corrections=2,
        adapter_version="library.official-chat.v1",
        adapter_sha256=file_hash(Path(__file__)),
    )
    return {**value, "manifest_hash": fingerprint(value)}


def check_manifest(manifest):
    if manifest.get("manifest_hash") != fingerprint(
        {k: v for k, v in manifest.items() if k != "manifest_hash"}
    ):
        raise ProcessingError("PROVIDER_METHOD_CHANGED", "供应商冻结配置哈希不匹配")
    provider = manifest.get("provider")
    if manifest.get("official_endpoint_id") not in ENDPOINTS or manifest.get(
        "requested_model"
    ) != {"deepseek": "deepseek-flash", "bailian": "qwen3.8-flash"}.get(provider):
        raise ProcessingError("PROVIDER_UNSUPPORTED", "供应商端点或模型不在官方白名单")
    return manifest


def prices(manifest):
    check_manifest(manifest)
    return tuple(
        Decimal(manifest[k]) / Decimal(1_000_000)
        for k in ("input_per_million", "output_per_million")
    )


def secret(manifest, settings):
    key = (
        settings.deepseek_api_key
        if manifest["provider"] == "deepseek"
        else settings.dashscope_api_key
    )
    if not key or not key.get_secret_value():
        raise ProcessingError("CREDENTIALS_MISSING", "所选官方供应商尚未配置受控密钥")
    return key.get_secret_value()


def availability(settings):
    """Describe local configuration without disclosing or contacting credentials."""
    items = []
    for provider in ("deepseek", "bailian"):
        key = (
            settings.deepseek_api_key
            if provider == "deepseek"
            else settings.dashscope_api_key
        )
        configured = bool(key and key.get_secret_value())
        issues = []
        if not configured:
            issues.append(
                {"code": "CREDENTIALS_MISSING", "message": "尚未配置所选供应商的密钥"}
            )
        manifest = None
        try:
            manifest = freeze(provider, settings)
        except ProcessingError as error:
            issues.append({"code": error.code, "message": str(error)})
        items.append(
            {
                "provider": provider,
                "requested_model": "deepseek-flash"
                if provider == "deepseek"
                else "qwen3.8-flash",
                "region": "official"
                if provider == "deepseek"
                else settings.m3_qwen_region,
                "credentials_configured": configured,
                "configuration_ready": not issues,
                "issues": issues,
                "currency": manifest["currency"] if manifest else None,
                "usd_per_currency": manifest["usd_per_currency"] if manifest else None,
                "exchange_rate_source": manifest["exchange_rate_source"]
                if manifest
                else None,
                "exchange_rate_effective_at": manifest["exchange_rate_effective_at"]
                if manifest
                else None,
            }
        )
    return {"items": items, "connectivity_checked": False}


def paper_budget_key(request):
    paper = request.get("exam_paper", {})
    names = ("exam_level", "exam_year", "exam_month", "paper_set")
    if not all(paper.get(k) is not None for k in names):
        return None
    return fingerprint({**{k: paper[k] for k in names}, "content_scope": "listening"})
