"""MCP egress OTel spans, retry, and per-server circuit breaker (#1203)."""

from __future__ import annotations

import socket

import httpx
import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind  # noqa: E402

from daari.gateway.internal import InternalRequest, Message  # noqa: E402
from daari.observability.metrics import Metrics  # noqa: E402
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig  # noqa: E402
from daari.router.circuit_breaker import CircuitBreaker  # noqa: E402
from daari.router.retry import RetryPolicy  # noqa: E402

_FAST = RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def _sequence_handler(responses: list, seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = responses[min(len(seen) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return httpx.Response(status, json=payload)

    return handler


def _patch_client(monkeypatch, handler):
    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)


def _provider(**kwargs) -> McpEgressProvider:
    defaults = dict(
        server=McpServerConfig(id="demo", url="http://mcp.test/rpc"),
        retry=_FAST,
        breaker=CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0),
        metrics=Metrics(),
    )
    defaults.update(kwargs)
    return McpEgressProvider(**defaults)


def _isolate_tracer(monkeypatch) -> InMemorySpanExporter:
    """Use a private TracerProvider so we never touch the process-global one."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def get_tracer(name: str, *args, **kwargs):
        return provider.get_tracer(name)

    monkeypatch.setattr("opentelemetry.trace.get_tracer", get_tracer)
    return exporter


@pytest.mark.asyncio
async def test_egress_emits_client_span_with_server_and_tool(monkeypatch):
    exporter = _isolate_tracer(monkeypatch)
    seen: list[httpx.Request] = []
    _patch_client(
        monkeypatch,
        _sequence_handler([(200, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})], seen),
    )
    provider = _provider()
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo get_forecast Paris")],
            model="daari",
        )
    )
    assert result.daari_meta.warning is None
    spans = [s for s in exporter.get_finished_spans() if s.name == "mcp.tools/call"]
    assert spans, f"expected mcp.tools/call span, got {[s.name for s in exporter.get_finished_spans()]}"
    span = spans[-1]
    assert span.kind == SpanKind.CLIENT
    attrs = dict(span.attributes or {})
    assert attrs.get("mcp.server.id") == "demo"
    assert attrs.get("mcp.tool.name") == "get_forecast"


@pytest.mark.asyncio
async def test_egress_retries_503_then_succeeds(monkeypatch):
    seen: list[httpx.Request] = []
    _patch_client(
        monkeypatch,
        _sequence_handler(
            [
                (503, {"error": "busy"}),
                (200, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
            ],
            seen,
        ),
    )
    metrics = Metrics()
    provider = _provider(metrics=metrics)
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo ping")],
            model="daari",
        )
    )
    assert result.daari_meta.warning is None
    assert len(seen) == 2
    assert metrics.snapshot(include_histograms=True)["upstream_retries"] >= 1


@pytest.mark.asyncio
async def test_egress_4xx_does_not_retry(monkeypatch):
    seen: list[httpx.Request] = []
    _patch_client(
        monkeypatch,
        _sequence_handler([(400, {"error": "bad"})], seen),
    )
    provider = _provider()
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo ping")],
            model="daari",
        )
    )
    assert result.daari_meta.warning == "integration_request_failed"
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_breaker_trips_then_fail_fast(monkeypatch):
    seen: list[httpx.Request] = []
    _patch_client(
        monkeypatch,
        _sequence_handler([(500, {"error": "down"})], seen),
    )
    metrics = Metrics()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    provider = _provider(
        retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0),
        breaker=breaker,
        metrics=metrics,
    )
    first = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo ping")],
            model="daari",
        )
    )
    assert first.daari_meta.warning == "integration_request_failed"
    assert breaker.state == "open"
    assert len(seen) == 1

    second = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo ping")],
            model="daari",
        )
    )
    assert second.daari_meta.warning == "mcp_circuit_open"
    assert len(seen) == 1  # no further HTTP
    snap = metrics.snapshot(include_histograms=True)
    assert any(
        key.startswith("demo:") and ":open" in key
        for key in (snap.get("mcp_egress") or {})
    )
