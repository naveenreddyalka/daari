"""Claude Managed Agents → daari Anthropic facade pin (#2257)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import collect_managed_agents_headers
from daari.gateway.internal import InternalRequest
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_cma_inference_tip


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_collect_managed_agents_headers_filters_prefix() -> None:
    req = _FakeRequest(
        {
            "anthropic-version": "2023-06-01",
            "anthropic-managed-agents-session-id": "sess-1",
            "Anthropic-Managed-Agents-Run-Id": "run-9",
            "x-api-key": "daari-local",
        }
    )
    collected = collect_managed_agents_headers(req)
    assert collected == {
        "anthropic-managed-agents-session-id": "sess-1",
        "anthropic-managed-agents-run-id": "run-9",
    }


@pytest.mark.asyncio
async def test_messages_accepts_cma_server_metadata_user_id(settings):
    """CMA sends metadata.user_id=cma-server; must not 422 (#2257)."""
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"user_id": "cma-server"},
            },
            headers={
                "anthropic-version": "2023-06-01",
                "x-api-key": "daari-local",
                "anthropic-managed-agents-session-id": "sess-cma",
                "anthropic-managed-agents-attribution": "self-hosted",
            },
        )
    assert response.status_code == 200, response.text
    assert seen
    assert seen[0].meta.user == "cma-server"


def test_cma_doctor_tip_when_daemon_up(settings) -> None:
    tip = _check_cma_inference_tip(settings, daemon_ok=True)
    assert tip is not None
    assert tip.name == "cma_inference"
    assert tip.ok is True
    assert tip.optional is True
    assert "Managed Agents" in tip.detail or "CMA" in tip.detail
    assert "11435" in tip.detail or str(settings.server.port) in tip.detail
    assert "partner" not in tip.detail.lower()
    assert "partnership" not in tip.detail.lower()


def test_cma_doctor_tip_absent_when_daemon_down(settings) -> None:
    assert _check_cma_inference_tip(settings, daemon_ok=False) is None


def test_cma_setup_guide_documents_inference_path() -> None:
    root = Path(__file__).resolve().parents[2]
    guide = (root / "docs/developer/guides/clients/claude-managed-agents.md").read_text(
        encoding="utf-8"
    )
    assert "cma-server" in guide
    assert "11435" in guide
    assert "metadata.user_id" in guide
    assert "anthropic-managed-agents-" in guide
    assert "partnership" not in guide.lower()
