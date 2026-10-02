"""RFC 8693 token exchange for MCP egress OBO (#1319).

Exchanges the inbound caller Bearer (subject_token) for a scoped upstream MCP
token. Secrets and tokens are never written to logs.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from daari.gateway.request_log import log_gateway_event
from daari.security.egress_url import EgressUrlBlocked, validate_egress_url

GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
DEFAULT_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
AUTH_TYPE_TOKEN_EXCHANGE = "oauth2_token_exchange"

WARNING_MISSING_SUBJECT = "mcp_token_exchange_missing_subject"
WARNING_EXCHANGE_FAILED = "mcp_token_exchange_failed"
WARNING_SSRF = "mcp_token_exchange_ssrf"

_DEFAULT_EXPIRES_IN = 3600.0
_REFRESH_MARGIN = 60.0
_TIMEOUT_SECONDS = 10.0


@dataclass
class _CachedExchange:
    access_token: str
    expires_at: float


class TokenExchangeError(Exception):
    """Exchange failed; ``warning`` is a stable InternalResponse code."""

    def __init__(self, warning: str, message: str) -> None:
        super().__init__(message)
        self.warning = warning


def normalize_subject_token_type(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value or value == "access_token":
        return DEFAULT_SUBJECT_TOKEN_TYPE
    if value.startswith("urn:"):
        return value
    return f"urn:ietf:params:oauth:token-type:{value}"


def bearer_from_authorization(header: str | None) -> str | None:
    if not header:
        return None
    text = header.strip()
    if text.lower().startswith("bearer "):
        token = text[7:].strip()
        return token or None
    return None


def subject_fingerprint(subject_token: str) -> str:
    return hashlib.sha256(subject_token.encode("utf-8")).hexdigest()[:16]


class TokenExchangeCache:
    """Per-provider cache keyed by subject fingerprint (not the raw token)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, _CachedExchange] = {}

    def get(self, fingerprint: str, *, now: float | None = None) -> str | None:
        clock = time.monotonic() if now is None else now
        with self._lock:
            entry = self._entries.get(fingerprint)
            if entry is None:
                return None
            if clock >= entry.expires_at - _REFRESH_MARGIN:
                return None
            return entry.access_token

    def put(
        self,
        fingerprint: str,
        access_token: str,
        *,
        expires_in: float,
        now: float | None = None,
    ) -> None:
        clock = time.monotonic() if now is None else now
        with self._lock:
            self._entries[fingerprint] = _CachedExchange(
                access_token=access_token,
                expires_at=clock + max(0.0, expires_in),
            )


async def exchange_access_token(
    *,
    server_id: str,
    endpoint: str,
    client_id: str,
    client_secret: str,
    subject_token: str,
    subject_token_type: str = DEFAULT_SUBJECT_TOKEN_TYPE,
    audience: str = "",
    scopes: list[str] | None = None,
    allow_private_networks: bool = False,
    cache: TokenExchangeCache | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Return an upstream access_token; raise TokenExchangeError on failure."""
    fp = subject_fingerprint(subject_token)
    if cache is not None:
        hit = cache.get(fp)
        if hit is not None:
            return hit

    endpoint = (endpoint or "").strip()
    if not endpoint:
        log_gateway_event(
            "mcp_token_exchange_failed",
            {"server_id": server_id, "reason": "missing_endpoint"},
        )
        raise TokenExchangeError(WARNING_EXCHANGE_FAILED, "token_exchange_endpoint is empty")

    try:
        validate_egress_url(endpoint, allow_private_networks=allow_private_networks)
    except EgressUrlBlocked as exc:
        log_gateway_event(
            "mcp_token_exchange_ssrf",
            {"server_id": server_id, "reason": str(exc)[:300]},
        )
        raise TokenExchangeError(WARNING_SSRF, str(exc)) from exc

    form: dict[str, str] = {
        "grant_type": GRANT_TYPE,
        "subject_token": subject_token,
        "subject_token_type": normalize_subject_token_type(subject_token_type),
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if audience:
        form["audience"] = audience
    if scopes:
        form["scope"] = " ".join(str(s) for s in scopes if s)

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    try:
        response = await http.post(
            endpoint,
            data=form,
            headers={"Accept": "application/json"},
        )
    except Exception as exc:  # noqa: BLE001 — never echo secrets
        host = urlparse(endpoint).hostname or "token-endpoint"
        log_gateway_event(
            "mcp_token_exchange_failed",
            {
                "server_id": server_id,
                "reason": type(exc).__name__,
                "endpoint_host": host,
            },
        )
        raise TokenExchangeError(
            WARNING_EXCHANGE_FAILED, f"token exchange request failed ({type(exc).__name__})"
        ) from None
    finally:
        if owns_client and not http.is_closed:
            await http.aclose()

    if response.status_code < 200 or response.status_code >= 300:
        log_gateway_event(
            "mcp_token_exchange_failed",
            {
                "server_id": server_id,
                "reason": f"http_{response.status_code}",
            },
        )
        raise TokenExchangeError(
            WARNING_EXCHANGE_FAILED,
            f"token exchange returned HTTP {response.status_code}",
        )

    try:
        payload: Any = response.json()
    except ValueError:
        log_gateway_event(
            "mcp_token_exchange_failed",
            {"server_id": server_id, "reason": "non_json"},
        )
        raise TokenExchangeError(WARNING_EXCHANGE_FAILED, "token exchange returned non-JSON") from None

    access = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access, str) or not access.strip():
        log_gateway_event(
            "mcp_token_exchange_failed",
            {"server_id": server_id, "reason": "no_access_token"},
        )
        raise TokenExchangeError(WARNING_EXCHANGE_FAILED, "token exchange returned no access_token")

    expires_raw = payload.get("expires_in", _DEFAULT_EXPIRES_IN) if isinstance(payload, dict) else _DEFAULT_EXPIRES_IN
    try:
        expires_in = float(expires_raw)
    except (TypeError, ValueError):
        expires_in = _DEFAULT_EXPIRES_IN

    token = access.strip()
    if cache is not None:
        cache.put(fp, token, expires_in=expires_in)
    log_gateway_event(
        "mcp_token_exchange_ok",
        {
            "server_id": server_id,
            "subject_fp": fp,
            "expires_in": int(expires_in),
        },
    )
    return token
