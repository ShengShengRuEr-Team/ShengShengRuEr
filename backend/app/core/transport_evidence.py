"""TLS 传输证据：最外层保存原始连接事实，再由本层唯一解析代理头（§9.3/DD-02）。"""

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import Headers

from app.core.config import get_settings

PROXY_HEADER_MODES = ("forwarded", "x_forwarded")


@dataclass(frozen=True)
class TransportEvidence:
    direct_scheme: str
    raw_peer: str | None
    peer_trusted: bool
    external_tls_state: str  # tls | not_configured | unknown
    source: str
    reason: str | None


def _trusted_networks():
    raw = get_settings().trusted_proxy_cidrs.strip()
    if not raw:
        return []
    networks = []
    for part in raw.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            continue
    return networks


def _peer_trusted(peer: str | None) -> bool:
    if not peer:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _trusted_networks())


def _first_value(headers: Headers, name: str) -> tuple[str | None, bool]:
    values = headers.getlist(name)
    if not values:
        return None, False
    if len(values) > 1:
        return None, True  # 多个同名头视为歧义
    return values[0], False


def build_evidence(scope: dict[str, Any]) -> TransportEvidence:
    headers = Headers(scope=scope)
    direct_scheme = str(scope.get("scheme") or "http")
    client = scope.get("client")
    raw_peer = client[0] if client else None
    trusted = _peer_trusted(raw_peer)
    settings = get_settings()

    has_proxy_header = any(
        headers.get(name) is not None
        for name in ("forwarded", "x-forwarded-proto", "x-forwarded-for")
    )

    if not trusted:
        if has_proxy_header and direct_scheme != "https":
            return TransportEvidence(
                direct_scheme=direct_scheme,
                raw_peer=raw_peer,
                peer_trusted=False,
                external_tls_state="unknown",
                source="untrusted_peer",
                reason="proxy_headers_from_untrusted_peer",
            )
        return TransportEvidence(
            direct_scheme=direct_scheme,
            raw_peer=raw_peer,
            peer_trusted=False,
            external_tls_state=(
                "tls" if direct_scheme == "https" else "not_configured"
            ),
            source="direct",
            reason=None,
        )

    mode = settings.proxy_header_mode
    if mode == "forwarded":
        value, duplicated = _first_value(headers, "forwarded")
        source = "forwarded"
        if duplicated:
            return TransportEvidence(
                direct_scheme, raw_peer, True, "unknown", source,
                "duplicate_proxy_header",
            )
        if value is None:
            return TransportEvidence(
                direct_scheme, raw_peer, True,
                "tls" if direct_scheme == "https" else "not_configured",
                "direct", "no_proxy_header",
            )
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if len(parts) != 1:
            return TransportEvidence(
                direct_scheme, raw_peer, True, "unknown", source,
                "multi_hop_chain",
            )
        proto = None
        for token in parts[0].split(";"):
            key, _, val = token.strip().partition("=")
            if key.strip().lower() == "proto":
                proto = val.strip().strip('"').lower()
        if proto not in {"http", "https"}:
            return TransportEvidence(
                direct_scheme, raw_peer, True, "unknown", source,
                "malformed_forwarded_header",
            )
        return TransportEvidence(
            direct_scheme,
            raw_peer,
            True,
            "tls" if proto == "https" else "not_configured",
            source,
            None,
        )

    # x_forwarded 模式：只认单值，不混用 Forwarded。
    value, duplicated = _first_value(headers, "x-forwarded-proto")
    source = "x_forwarded"
    if duplicated:
        return TransportEvidence(
            direct_scheme, raw_peer, True, "unknown", source,
            "duplicate_proxy_header",
        )
    if value is None:
        return TransportEvidence(
            direct_scheme, raw_peer, True,
            "tls" if direct_scheme == "https" else "not_configured",
            "direct", "no_proxy_header",
        )
    if "," in value:
        return TransportEvidence(
            direct_scheme, raw_peer, True, "unknown", source,
            "multi_hop_chain",
        )
    proto = value.strip().lower()
    if proto not in {"http", "https"}:
        return TransportEvidence(
            direct_scheme, raw_peer, True, "unknown", source,
            "malformed_proxy_header",
        )
    return TransportEvidence(
        direct_scheme,
        raw_peer,
        True,
        "tls" if proto == "https" else "not_configured",
        source,
        None,
    )


class TransportEvidenceMiddleware:
    """最外层 ASGI 中间件：只记录证据，不改变业务行为。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            try:
                evidence = build_evidence(scope)
                scope.setdefault("state", {})["transport_evidence"] = evidence
            except Exception:  # noqa: BLE001 - 证据失败不影响请求
                scope.setdefault("state", {})["transport_evidence"] = None
        await self.app(scope, receive, send)


def evidence_payload(evidence: TransportEvidence | None) -> dict[str, Any]:
    settings = get_settings()
    if evidence is None:
        return {
            "direct_scheme": "unknown",
            "external_tls_state": "unknown",
            "configured_public_origin": settings.public_origin or None,
            "source": "unknown",
            "reason": "evidence_missing",
            "peer_trusted": False,
            "observed_at": datetime.now(UTC),
        }
    return {
        "direct_scheme": evidence.direct_scheme,
        "external_tls_state": evidence.external_tls_state,
        "configured_public_origin": settings.public_origin or None,
        "source": evidence.source,
        "reason": evidence.reason,
        "peer_trusted": evidence.peer_trusted,
        "observed_at": datetime.now(UTC),
    }
