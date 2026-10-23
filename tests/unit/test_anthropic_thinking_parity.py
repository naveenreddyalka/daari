"""Anthropic thinking, metadata, and top_k reach L6 payloads (#1009).

Request-level `thinking` / `metadata` were dropped by `AnthropicRequest`;
`top_k` reached local Ollama but not `to_anthropic_payload`.

API version 2026-10-21 removes sampling params (#1849).
Local strip of thinking.between_tools bumps soft_warnings (#1851).
"""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.observability.metrics import Metrics
from daari.router.anthropic_messages import (
    apply_anthropic_version_sampling_compat,
    to_anthropic_payload,
)
from daari.router.frontier import FrontierExecutor
from daari.router.param_compat import FrontierParamCompatResult
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


THINKING = {"type": "enabled", "budget_tokens": 4096}
METADATA = {"user_id": "user_abc"}


class TestHttpRetention:
    def test_anthropic_request_temperature_defaults_to_none(self):
        """Omitting temperature must not inject 0.7 (#1849)."""
        req = AnthropicRequest.model_validate(
            {
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
            }
        )
        assert req.temperature is None
        assert req.top_p is None
        assert req.top_k is None

    def test_anthropic_request_keeps_thinking_and_metadata(self):
        req = AnthropicRequest.model_validate(
            {
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 20,
            }
        )
        assert req.thinking == THINKING
        assert req.metadata == METADATA
        assert req.top_k == 20

    def test_from_anthropic_body_retains_fields(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 100,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 20,
            }
        )
        assert params.thinking == THINKING
        assert params.metadata == METADATA
        assert params.top_k == 20
        # Budget present → reasoning_effort for local think mapping.
        assert params.reasoning_effort == "medium"


class TestPayloadEmission:
    def test_to_anthropic_payload_forwards_thinking_metadata_top_k(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 15,
            }
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["thinking"] == THINKING
        assert payload["metadata"] == METADATA
        assert payload["top_k"] == 15

    def test_thinking_budget_maps_to_ollama_think(self):
        low = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "enabled", "budget_tokens": 1024}}
        )
        high = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "enabled", "budget_tokens": 16000}}
        )
        assert low.ollama_think() == "low"
        assert high.ollama_think() == "high"

    def test_disabled_thinking_does_not_enable_local_think(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "disabled"}}
        )
        assert params.thinking == {"type": "disabled"}
        assert params.ollama_think() is None

    def test_between_tools_degrades_locally_without_silent_drop(self):
        """Local tiers map between_tools → no think and signal the drop (#1828)."""
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "between_tools"}}
        )
        assert params.thinking == {"type": "between_tools"}
        assert params.ollama_think() is None
        assert params.reasoning_effort is None
        assert "thinking.between_tools" in params.dropped_param_names()
        notes = params.unsupported_locally()
        assert any("between_tools" in note for note in notes)

    def test_to_anthropic_payload_forwards_between_tools_unchanged(self):
        """L6 Anthropic path keeps thinking.type=between_tools (#1828)."""
        between = {"type": "between_tools"}
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "thinking": between}
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-5-5",
        )
        assert payload["thinking"] == between

    def test_omitted_temperature_not_on_anthropic_payload(self):
        """No default temperature on L6 when the client omitted it (#1849)."""
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                temperature=None,
            ),
            model="claude-sonnet-4-0",
        )
        assert "temperature" not in payload

    def test_api_version_2026_10_21_strips_sampling_params(self):
        """anthropic-version 2026-10-21 drops temperature/top_p/top_k (#1849)."""
        payload = {
            "model": "claude",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 50,
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 20,
        }
        dropped = apply_anthropic_version_sampling_compat(payload, "2026-10-21")
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload
        assert dropped == ["temperature", "top_p", "top_k"]

    def test_legacy_api_version_keeps_sampling_params(self):
        payload = {
            "model": "claude",
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 20,
        }
        dropped = apply_anthropic_version_sampling_compat(payload, "2023-06-01")
        assert payload["temperature"] == 0.5
        assert dropped == []

    def test_frontier_anthropic_payload_records_version_drops(self):
        """Frontier merges API-version sampling drops into last_param_compat (#1849)."""
        executor = FrontierExecutor(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-0",
            provider="anthropic",
        )
        request = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="daari",
            temperature=0.4,
            sampling=SamplingParams(top_p=0.8, top_k=10, max_tokens=50),
            meta=RequestMeta(anthropic_version="2026-10-21"),
        )
        payload = executor._anthropic_payload(request, stream=False)
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload
        compat = executor.last_param_compat
        assert isinstance(compat, FrontierParamCompatResult)
        for name in ("temperature", "top_p", "top_k"):
            assert name in compat.dropped_params


def test_sampling_strip_records_soft_warning_and_prometheus():
    """2026-10-21 sampling strip bumps soft_warning + Prom series (#1869)."""
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    executor = FrontierExecutor(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        provider="anthropic",
        metrics=metrics,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=0.4,
        sampling=SamplingParams(top_p=0.8, top_k=10, max_tokens=50),
        meta=RequestMeta(anthropic_version="2026-10-21"),
    )
    executor._anthropic_payload(request, stream=False)
    assert metrics.soft_warnings.get("anthropic_sampling_stripped") == 1
    text = render_prometheus(metrics)
    assert 'daari_soft_warnings_total{kind="anthropic_sampling_stripped"} 1' in text

    # Stream path shares _anthropic_payload — second strip increments again.
    executor._anthropic_payload(request, stream=True)
    assert metrics.soft_warnings.get("anthropic_sampling_stripped") == 2


def test_sampling_strip_soft_warning_absent_when_clean_or_legacy():
    """No soft_warning when nothing stripped or version is legacy (#1869)."""
    metrics = Metrics()
    executor = FrontierExecutor(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        provider="anthropic",
        metrics=metrics,
    )
    clean = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=None,  # omit default 0.7 so payload has no sampling knobs
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(anthropic_version="2026-10-21"),
    )
    executor._anthropic_payload(clean, stream=False)
    assert metrics.soft_warnings.get("anthropic_sampling_stripped") is None

    legacy = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=0.4,
        sampling=SamplingParams(top_p=0.8, top_k=10, max_tokens=50),
        meta=RequestMeta(anthropic_version="2023-06-01"),
    )
    executor._anthropic_payload(legacy, stream=False)
    assert metrics.soft_warnings.get("anthropic_sampling_stripped") is None


def _between_tools_request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="llama3.2:3b",
        sampling=SamplingParams.from_anthropic_body(
            {"max_tokens": 16, "thinking": {"type": "between_tools"}}
        ),
    )


@pytest.mark.asyncio
async def test_local_between_tools_increments_soft_warning_once(tmp_path):
    """Local strip of between_tools bumps soft_warnings exactly once (#1851)."""
    metrics = Metrics()

    async def fake_l3(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_l3  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "c"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama=ollama,
        metrics=metrics,
        confidence_threshold=0.0,
    )
    result = await router.route(_between_tools_request())
    assert result.daari_meta.tier == "L3"
    assert "thinking.between_tools" in (result.daari_meta.dropped_params or [])
    assert metrics.soft_warnings.get("thinking_between_tools_stripped") == 1
    await router.route(_between_tools_request())
    assert metrics.soft_warnings.get("thinking_between_tools_stripped") == 2


@pytest.mark.asyncio
async def test_l6_between_tools_does_not_increment_soft_warning(tmp_path):
    """L6 Anthropic forward keeps between_tools — no soft_warning (#1851)."""
    metrics = Metrics()

    async def fake_l3(request: InternalRequest) -> InternalResponse:
        raise AssertionError("local must not run on web_search L6 path")

    async def fake_l6(
        request: InternalRequest,
        *,
        escalated_from: str,
        local_confidence: float,
    ) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="claude-sonnet-5-5",
            daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_l3  # type: ignore[method-assign]
    frontier = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-5-5",
        api_key="sk-test",
        provider="anthropic",
    )
    frontier.execute = fake_l6  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "c"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama=ollama,
        metrics=metrics,
        frontier=frontier,
        frontier_enabled=True,
    )
    request = _between_tools_request()
    # Force L6 without local degrade (same as Anthropic forward path).
    request.sampling.web_search_options = {"search_context_size": "medium"}
    result = await router.route(request)
    assert result.daari_meta.tier == "L6"
    assert metrics.soft_warnings.get("thinking_between_tools_stripped") is None
