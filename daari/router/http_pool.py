"""Shared keepalive httpx.AsyncClient pools for upstream hops (#971)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# Match httpx defaults so existing behaviour stays familiar.
DEFAULT_POOL_MAX_CONNECTIONS = 100
DEFAULT_POOL_KEEPALIVE_CONNECTIONS = 20


@dataclass(frozen=True)
class PoolLimits:
    max_connections: int = DEFAULT_POOL_MAX_CONNECTIONS
    max_keepalive_connections: int = DEFAULT_POOL_KEEPALIVE_CONNECTIONS

    def as_httpx(self) -> httpx.Limits:
        return httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
        )


def pool_limits_from_settings(settings: Any | None = None) -> PoolLimits:
    upstream = getattr(settings, "upstream", None) if settings is not None else None
    if upstream is None:
        return PoolLimits()
    max_conn = getattr(upstream, "pool_max_connections", DEFAULT_POOL_MAX_CONNECTIONS)
    keepalive = getattr(
        upstream, "pool_keepalive_connections", DEFAULT_POOL_KEEPALIVE_CONNECTIONS
    )
    return PoolLimits(
        max_connections=int(max_conn or DEFAULT_POOL_MAX_CONNECTIONS),
        max_keepalive_connections=int(keepalive or DEFAULT_POOL_KEEPALIVE_CONNECTIONS),
    )


def build_async_client(
    httpx_mod: Any = httpx,
    *,
    base_url: str = "",
    limits: PoolLimits | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Long-lived client: no baked-in request timeout (pass per call)."""
    pool = limits or PoolLimits()
    opts: dict[str, Any] = {
        "limits": pool.as_httpx(),
        "timeout": None,
    }
    if base_url:
        opts["base_url"] = base_url
    if transport is not None:
        opts["transport"] = transport
    opts.update(kwargs)
    return httpx_mod.AsyncClient(**opts)


class PooledClientHolder:
    """Lazy shared AsyncClient; call aclose() on shutdown."""

    def __init__(
        self,
        *,
        base_url: str = "",
        limits: PoolLimits | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        httpx_mod: Any = httpx,
    ) -> None:
        self.base_url = base_url
        self.limits = limits
        self.transport = transport
        self._httpx = httpx_mod
        self._http: httpx.AsyncClient | None = None

    def client(self) -> httpx.AsyncClient:
        if self._http is None or getattr(self._http, "is_closed", False):
            self._http = build_async_client(
                self._httpx,
                base_url=self.base_url,
                limits=self.limits,
                transport=self.transport,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not getattr(self._http, "is_closed", True):
            await self._http.aclose()
        self._http = None
