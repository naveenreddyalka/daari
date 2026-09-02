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

from dataclasses import dataclass
from typing import Any, Callable

from starlette.responses import StreamingResponse
from starlette.types import Send

from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd

COST_HEADER = "x-daari-response-cost"
COST_AVOIDED_HEADER = "x-daari-response-cost-avoided"
TIER_HEADER = "x-daari-tier"
CACHE_HEADER = "x-daari-cache"

FRONTIER_TIER = "L6"


def _decimal(value: float) -> str:
    text = f"{max(0.0, value):.8f}".rstrip("0").rstrip(".")
    return text or "0"


def _cache_state(*, cache_hit: bool, draft: bool) -> str:
    if cache_hit:
        return "hit"
    return "draft" if draft else "miss"


def _frontier_price_per_1k(settings: Any) -> float:
    usage = getattr(settings, "usage", None)
    return float(getattr(usage, "frontier_price_per_1k_tokens", 0.002) or 0.002)


def _is_frontier(meta: DaariMeta) -> bool:
    return meta.tier == FRONTIER_TIER or (meta.executor or "") == "frontier"


def response_cost_headers(
    meta: DaariMeta,
    settings: Any,
    *,
    prompt_chars: int = 0,
    completion_chars: int = 0,
) -> dict[str, str]:
    """Headers for a completed (non-streaming) response."""
    price_per_1k = _frontier_price_per_1k(settings)
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
            )
        avoided = 0.0
    else:
        spent = 0.0
        # chars/4 ~ tokens, priced as if a frontier model had served them —
        # identical to UsageLedger.report so per-response and per-team agree.
        tokens = (max(0, prompt_chars) + max(0, completion_chars)) / 4
        avoided = tokens / 1000 * price_per_1k
    return {
        COST_HEADER: _decimal(spent),
        COST_AVOIDED_HEADER: _decimal(avoided),
        TIER_HEADER: meta.tier,
        CACHE_HEADER: _cache_state(cache_hit=meta.cache_hit, draft=meta.draft),
    }


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
