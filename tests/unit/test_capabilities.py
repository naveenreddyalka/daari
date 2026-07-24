"""Capability catalog + VRAM advisor (issue #113)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.capabilities import (
    CapabilityCatalog,
    catalog_from_settings,
    filter_tiers_by_capability,
    required_capabilities,
    suggest_models_for_vram,
)
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def test_required_capabilities_detects_tools():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        tools=[{"type": "function", "function": {"name": "x"}}],
    )
    assert "tools" in required_capabilities(req)


def test_filter_drops_incapable_tiers():
    catalog = CapabilityCatalog(
        models={
            "tiny": frozenset(),
            "mid": frozenset({"tools"}),
            "big": frozenset({"tools", "vision"}),
        }
    )
    kept = filter_tiers_by_capability(
        ["L3", "L4", "L5"],
        tier_models={"L3": "tiny", "L4": "mid", "L5": "big"},
        catalog=catalog,
        required={"tools"},
    )
    assert kept == ["L4", "L5"]


def test_suggest_models_scales_with_ram():
    assert suggest_models_for_vram(8)["l3"] == "llama3.2:1b"
    assert "14b" in suggest_models_for_vram(32)["l5"]
    assert "70b" in suggest_models_for_vram(64)["l5"]


def test_catalog_from_settings_defaults():
    catalog = catalog_from_settings(Settings())
    assert "tools" in catalog.for_model("llama3.2:3b")


@pytest.mark.asyncio
async def test_router_skips_tier_without_tools(tmp_path):
    catalog = CapabilityCatalog(
        models={
            "llama3.2:3b": frozenset(),
            "llama3.1:8b": frozenset({"tools"}),
        }
    )
    seen: list[str] = []

    async def fake(request: InternalRequest) -> InternalResponse:
        # Which executor ran is inferred from the call site via closure below.
        return InternalResponse(
            content="tool ready",
            model="m",
            daari_meta=DaariMeta(
                tier=seen[-1] if seen else "L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    l3 = OllamaExecutor(base_url="http://t", default_model="llama3.2:3b", tier="L3")
    l4 = OllamaExecutor(base_url="http://t", default_model="llama3.1:8b", tier="L4")

    async def l3_exec(request):
        seen.append("L3")
        return await fake(request)

    async def l4_exec(request):
        seen.append("L4")
        return await fake(request)

    l3.execute = l3_exec  # type: ignore[method-assign]
    l4.execute = l4_exec  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama_l3=l3,
        ollama_l4=l4,
        metrics=Metrics(),
        frontier_enabled=False,
        capability_catalog=catalog,
    )
    req = InternalRequest(
        messages=[Message(role="user", content="use a tool")],
        model="daari",
        tools=[{"type": "function", "function": {"name": "x"}}],
    )
    # Force L3 preference via short prompt; capability filter should step to L4.
    result = await router.route(req)
    assert "L3" not in seen
    assert "L4" in seen
    assert result.content == "tool ready"


def test_doctor_suggest_models_cli():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["doctor", "--suggest-models"])
    assert result.exit_code == 0
    assert "Suggested L3:" in result.output
