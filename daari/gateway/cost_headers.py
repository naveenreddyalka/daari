"""Cost-split and savings response headers (issue #278).

FinOps tooling scrapes headers, not bodies. Every gateway response reports what
the request cost (`x-daari-response-cost`, 0 for local tiers) and what it
avoided (`x-daari-response-cost-avoided`: the frontier-implied price of a
request served at L0–L5, on the same basis as `daari report`), plus the tier
and cache outcome.

Streams have no body to inspect before headers go out, so the router records
its decision in a `StreamOutcome` and `DeferredHeadersStreamingResponse` holds
the HTTP start line until the first body chunk is ready. Cost headers are never
sent on streams: usage is unknown until the last chunk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from starlette.responses import StreamingResponse
from starlette.types import Send

from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd

COST_HEADER = "x-daari-response-cost"
COST_AVOIDED_HEADER = "x-daari-response-cost-avoided"
SESSION_COST_AVOIDED_HEADER = "x-daari-session-cost-avoided"
TIER_HEADER = "x-daari-tier"
CACHE_HEADER = "x-daari-cache"
REGION_HEADER = "x-daari-region"
# Always-on sampling / soft-warning signal — no X-Daari-Meta opt-in (#1007).
WARNING_HEADER = "x-daari-warning"

FRONTIER_TIER = "L6"


def _decimal(value: float) -> str:
    text = f"{max(0.0, value):.8f}".rstrip("0").rstrip(".")
    return text or "0"


# Shared with the budget headers (#319) so every USD header formats alike.
usd_string = _decimal


def _cache_state(*, cache_hit: bool, draft: bool) -> str:
    if cache_hit:
        return "hit"
    return "draft" if draft else "miss"


def _frontier_price_per_1k(settings: Any) -> float:
    usage = getattr(settings, "usage", None)
    return float(getattr(usage, "frontier_price_per_1k_tokens", 0.002) or 0.002)


def _is_frontier(meta: DaariMeta) -> bool:
    return meta.tier == FRONTIER_TIER or (meta.executor or "") == "frontier"


class SessionAvoidedStore:
    """Running frontier-implied savings for one client session id.

    Same TTL as session-affinity pins. Missing / blank ids are ignored so
    single-turn clients keep the per-response header only. When Redis is
    configured (fleet), the total is shared across replicas (#482).
    """

    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] | None = None,
        redis_client: Any | None = None,
        redis_prefix: str = "daari:session-avoided:",
        redis_url: str | None = None,
        redis_timeout_seconds: float = 2.0,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        self._totals: dict[str, tuple[float, float]] = {}
        self._redis = redis_client
        self._redis_url = redis_url
        self._redis_timeout_seconds = redis_timeout_seconds
        self._redis_prefix = redis_prefix
        self._degraded = False

    def _client(self) -> Any | None:
        if self._redis is not None:
            return self._redis
        if not self._redis_url:
            return None
        from daari.cache.redis_client import connect_redis

        self._redis = connect_redis(
            self._redis_url, timeout_seconds=self._redis_timeout_seconds
        )
        return self._redis

    def _redis_key(self, session_id: str) -> str:
        return f"{self._redis_prefix}{session_id}"

    def _mark_degraded(self, exc: BaseException) -> None:
        if self._degraded:
            return
        self._degraded = True
        try:
            from daari.gateway.request_log import log_gateway_event

            log_gateway_event(
                "session_affinity.degraded",
                detail=str(exc),
                backend="redis",
                store="session_avoided",
            )
        except Exception:
            pass

    def _purge(self, session_id: str) -> None:
        row = self._totals.get(session_id)
        if row is None:
            return
        _total, expires_at = row
        if self.ttl_seconds > 0 and self._clock() >= expires_at:
            self._totals.pop(session_id, None)

    def add(self, session_id: str, avoided: float) -> float:
        key = (session_id or "").strip()
        if not key:
            return 0.0
        delta = max(0.0, float(avoided))
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            client = None
        if client is not None:
            try:
                redis_key = self._redis_key(key)
                if hasattr(client, "incrbyfloat"):
                    total = float(client.incrbyfloat(redis_key, delta))
                else:
                    raw = client.get(redis_key)
                    prev = float(raw or 0.0)
                    total = prev + delta
                    if self.ttl_seconds > 0:
                        client.set(redis_key, str(total), ex=int(max(1, self.ttl_seconds)))
                    else:
                        client.set(redis_key, str(total))
                    return total
                if self.ttl_seconds > 0 and hasattr(client, "expire"):
                    client.expire(redis_key, int(max(1, self.ttl_seconds)))
                return total
            except Exception as exc:
                self._mark_degraded(exc)
        self._purge(key)
        now = self._clock()
        expires = now + self.ttl_seconds if self.ttl_seconds > 0 else float("inf")
        prev, _ = self._totals.get(key, (0.0, expires))
        total = prev + delta
        self._totals[key] = (total, expires)
        return total

    def total(self, session_id: str) -> float | None:
        key = (session_id or "").strip()
        if not key:
            return None
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            client = None
        if client is not None:
            try:
                raw = client.get(self._redis_key(key))
                if raw is None:
                    return None
                return float(raw)
            except Exception as exc:
                self._mark_degraded(exc)
        self._purge(key)
        row = self._totals.get(key)
        return None if row is None else row[0]


def avoided_usd(
    meta: DaariMeta,
    settings: Any,
    *,
    prompt_chars: int = 0,
    completion_chars: int = 0,
) -> float:
    """Frontier-implied USD of a local serve; 0 on L6."""
    if _is_frontier(meta):
        return 0.0
    tokens = (max(0, prompt_chars) + max(0, completion_chars)) / 4
    return tokens / 1000 * _frontier_price_per_1k(settings)


def response_cost_headers(
    meta: DaariMeta,
    settings: Any,
    *,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    session_id: str | None = None,
    savings: SessionAvoidedStore | None = None,
) -> dict[str, str]:
    """Headers for a completed (non-streaming) response."""
    price_per_1k = _frontier_price_per_1k(settings)
    avoided = avoided_usd(
        meta, settings, prompt_chars=prompt_chars, completion_chars=completion_chars
    )
    if _is_frontier(meta):
        if meta.cost_usd is not None:
            spent = float(meta.cost_usd)
        else:
            spent = cost_usd(
                meta.model,
                int(meta.input_tokens or 0),
                int(meta.output_tokens or 0),
                getattr(settings, "pricing", None),
                fallback_per_1k=price_per_1k,
                cached_input_tokens=int(meta.cached_tokens or 0),
                service_tier=meta.service_tier,
            )
    else:
        spent = 0.0
    headers = {
        COST_HEADER: _decimal(spent),
        COST_AVOIDED_HEADER: _decimal(avoided),
        TIER_HEADER: meta.tier,
        CACHE_HEADER: _cache_state(cache_hit=meta.cache_hit, draft=meta.draft),
    }
    if meta.region:
        headers[REGION_HEADER] = str(meta.region)
    if meta.warning:
        headers[WARNING_HEADER] = str(meta.warning)
    sid = (session_id or "").strip()
    if sid and savings is not None:
        headers[SESSION_COST_AVOIDED_HEADER] = _decimal(savings.add(sid, avoided))
    return headers


def stream_usage_cost(
    *,
    tier: str | None,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    pricing: object | None = None,
    fallback_per_1k: float = 0.002,
    cached_input_tokens: int = 0,
    reported_cost: float | None = None,
    service_tier: str | None = None,
) -> float:
    """USD for a streamed usage object. Local tiers are $0; L6 matches headers."""
    if (tier or "").upper() != FRONTIER_TIER:
        return 0.0
    if reported_cost is not None:
        return float(reported_cost)
    return cost_usd(
        model,
        int(prompt_tokens),
        int(completion_tokens),
        pricing,
        fallback_per_1k=fallback_per_1k,
        cached_input_tokens=int(cached_input_tokens),
        service_tier=service_tier,
    )


def stream_cached_tokens(
    *,
    tier: str | None,
    prompt_tokens: int = 0,
    cached_from_meta: int | None = None,
) -> int:
    """Cached prompt tokens for a streamed usage object (#399).

    L0/L1 hits report the full prompt as cached. L6 uses provider meta when
    present. Unknown / local generate → 0.
    """
    label = (tier or "").upper()
    if label in {"L0", "L1"}:
        return max(0, int(prompt_tokens))
    if cached_from_meta is not None:
        return max(0, int(cached_from_meta))
    return 0


@dataclass
class StreamOutcome:
    """What the router decided for a streamed request, filled before its first chunk."""

    tier: str | None = None
    cache: str | None = None

    def note(
        self, tier: str | None, *, cache_hit: bool = False, draft: bool = False
    ) -> StreamOutcome:
        if tier:
            self.tier = tier
            self.cache = _cache_state(cache_hit=cache_hit, draft=draft)
        return self

    def headers(self) -> dict[str, str]:
        if not self.tier:
            return {}
        return {TIER_HEADER: self.tier, CACHE_HEADER: self.cache or "miss"}


class DeferredHeadersStreamingResponse(StreamingResponse):
    """Send the HTTP start line only once the first body chunk exists.

    Whatever `late_headers()` returns at that moment is merged into the
    response headers, so streams can report the tier the router actually
    served. Keepalive frames count as a first chunk: a slow model still gets
    its headers out on the keepalive interval, just without tier info.
    """

    def __init__(
        self,
        content: Any,
        *,
        late_headers: Callable[[], dict[str, str]],
        **kwargs: Any,
    ) -> None:
        super().__init__(content, **kwargs)
        self._late_headers = late_headers

    async def _start(self, send: Send) -> None:
        for name, value in self._late_headers().items():
            self.headers[name] = value
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers}
        )

    async def stream_response(self, send: Send) -> None:
        started = False
        async for chunk in self.body_iterator:
            if not started:
                await self._start(send)
                started = True
            if not isinstance(chunk, (bytes, memoryview)):
                chunk = chunk.encode(self.charset)
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        if not started:
            await self._start(send)
        await send({"type": "http.response.body", "body": b"", "more_body": False})
