"""Prometheus counter for X-Daari-Priority admission outcomes (#2113)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import (
    VirtualKey,
    admission_priority_outcome,
    resolve_request_admission_priority,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def test_prometheus_renders_admission_priority_outcomes() -> None:
    metrics = Metrics()
    metrics.record_admission_priority("raised")
    metrics.record_admission_priority("ignored")
    metrics.record_admission_priority("ignored")
    metrics.record_admission_priority("baseline")
    metrics.record_admission_priority("lowered")
    text = render_prometheus(metrics)
    assert "# TYPE daari_admission_priority_total counter" in text
    assert 'daari_admission_priority_total{outcome="raised"} 1' in text
    assert 'daari_admission_priority_total{outcome="ignored"} 2' in text
    assert 'daari_admission_priority_total{outcome="baseline"} 1' in text
    assert 'daari_admission_priority_total{outcome="lowered"} 1' in text


def test_outcome_classifier_raised_ignored_baseline_lowered() -> None:
    key = VirtualKey(key_id="k1", name="bot", prefix="dk", priority="normal")

    effective, warning, changed = resolve_request_admission_priority(
        key, header="high", allow_boost=True
    )
    assert (
        admission_priority_outcome(
            header="high",
            baseline="normal",
            effective=effective,
            warning=warning,
            changed=changed,
        )
        == "raised"
    )

    effective, warning, changed = resolve_request_admission_priority(
        key, header="high", allow_boost=False
    )
    assert (
        admission_priority_outcome(
            header="high",
            baseline="normal",
            effective=effective,
            warning=warning,
            changed=changed,
        )
        == "ignored"
    )

    effective, warning, changed = resolve_request_admission_priority(
        key, header="nope", allow_boost=True
    )
    assert (
        admission_priority_outcome(
            header="nope",
            baseline="normal",
            effective=effective,
            warning=warning,
            changed=changed,
        )
        == "ignored"
    )

    effective, warning, changed = resolve_request_admission_priority(
        key, header=None, allow_boost=False
    )
    assert (
        admission_priority_outcome(
            header=None,
            baseline="normal",
            effective=effective,
            warning=warning,
            changed=changed,
        )
        == "baseline"
    )

    effective, warning, changed = resolve_request_admission_priority(
        key, header="low", allow_boost=False
    )
    assert (
        admission_priority_outcome(
            header="low",
            baseline="normal",
            effective=effective,
            warning=warning,
            changed=changed,
        )
        == "lowered"
    )


def _mock_execute(app) -> None:
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake


def _app(settings, tmp_path: Path, *, allow_boost: bool = False):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.allow_request_priority_boost = allow_boost
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.observability.prometheus = True
    settings.rate_limit.max_in_flight = 4
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    _mock_execute(app)
    return app


@pytest.mark.asyncio
async def test_gateway_allowed_raise_bumps_raised(settings, tmp_path) -> None:
    app = _app(settings, tmp_path, allow_boost=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": "Bearer master",
                "X-Daari-Priority": "high",
                "X-Daari-No-Cache": "true",
            },
        )
        assert r.status_code == 200
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_admission_priority_total{outcome="raised"} 1' in metrics.text
    assert 'daari_admission_priority_total{outcome="ignored"}' not in metrics.text
    assert app.state.ctx.metrics.admission_priority.get("raised") == 1


@pytest.mark.asyncio
async def test_gateway_invalid_and_disallowed_bump_ignored(settings, tmp_path) -> None:
    app = _app(settings, tmp_path, allow_boost=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": "Bearer master",
                "X-Daari-Priority": "nope",
                "X-Daari-No-Cache": "true",
            },
        )
        assert bad.status_code == 200
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": "Bearer master",
                "X-Daari-Priority": "high",
                "X-Daari-No-Cache": "true",
            },
        )
        assert denied.status_code == 200
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_admission_priority_total{outcome="ignored"} 2' in metrics.text
    assert 'daari_admission_priority_total{outcome="raised"}' not in metrics.text
    assert app.state.ctx.metrics.admission_priority.get("ignored") == 2


@pytest.mark.asyncio
async def test_gateway_no_header_does_not_inflate_raised(settings, tmp_path) -> None:
    app = _app(settings, tmp_path, allow_boost=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": "Bearer master",
                "X-Daari-No-Cache": "true",
            },
        )
        assert r.status_code == 200
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_admission_priority_total{outcome="raised"}' not in metrics.text
    assert 'daari_admission_priority_total{outcome="baseline"} 1' in metrics.text
    assert app.state.ctx.metrics.admission_priority.get("raised") is None
    assert app.state.ctx.metrics.admission_priority.get("baseline") == 1


def test_grafana_and_docs_mention_admission_priority() -> None:
    root = Path(__file__).resolve().parents[2]
    dashboard = (root / "deploy/grafana/daari-dashboard.json").read_text(encoding="utf-8")
    guide = (
        root / "docs/developer/guides/observability/metrics-prometheus.md"
    ).read_text(encoding="utf-8")
    assert "daari_admission_priority_total" in dashboard
    assert "daari_admission_priority_total" in guide
