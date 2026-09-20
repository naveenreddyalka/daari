"""Per-provider and per-tier retry/timeout policy (#712)."""

from __future__ import annotations

import httpx
import pytest

from daari.config.settings import FrontierProviderConfig, FrontierSettings, Settings
from daari.gateway.internal import InternalRequest, Message
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot, build_frontier_pool
from daari.router.retry import RetryPolicy


def _request(text: str = "hi") -> InternalRequest:
    return InternalRequest(model="daari", messages=[Message(role="user", content=text)])


def _chat_completion(content: str = "answer") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }


def _sequence_transport(responses: list) -> tuple[httpx.MockTransport, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), calls


def _settings_with_providers(*entries: FrontierProviderConfig) -> Settings:
    settings = Settings()
    settings.frontier = FrontierSettings(enabled=True, providers=list(entries))
    return settings


class TestProviderPolicyConfig:
    def test_optional_fields_default_unset(self):
        entry = FrontierProviderConfig(id="openai")
        assert entry.timeout_s is None
        assert entry.retry_attempts is None
        assert entry.retry_backoff_s is None

    def test_yaml_accepts_per_provider_overrides(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text(
            "frontier:\n"
            "  enabled: true\n"
            "  providers:\n"
            "    - id: openai\n"
            "      keys: [sk-a]\n"
            "      timeout_s: 30\n"
            "      retry_attempts: 2\n"
            "      retry_backoff_s: 0.5\n"
            "    - id: anthropic\n"
            "      keys: [sk-b]\n"
            "      timeout_s: 60\n"
            "      retry_attempts: 0\n",
            encoding="utf-8",
        )
        settings = Settings.load(config_path=path)
        openai, anthropic = settings.frontier.providers
        assert openai.timeout_s == 30.0
        assert openai.retry_attempts == 2
        assert openai.retry_backoff_s == 0.5
        assert anthropic.timeout_s == 60.0
        assert anthropic.retry_attempts == 0
        assert anthropic.retry_backoff_s is None


class TestBuildPoolHonorsOverrides:
    def test_unset_falls_back_to_globals(self):
        settings = _settings_with_providers(
            FrontierProviderConfig(id="openai", keys=["sk-a"])
        )
        pool = build_frontier_pool(settings)
        slot = pool.slots[0]
        assert slot.executor.timeout == settings.upstream.frontier_timeout_seconds
        assert slot.executor.retry is not None
        assert slot.executor.retry.attempts == settings.upstream.retry.attempts
        assert slot.executor.retry.base_delay == pytest.approx(
            settings.upstream.retry.base_delay_ms / 1000
        )

    def test_per_provider_override_is_wired_onto_the_executor(self):
        settings = _settings_with_providers(
            FrontierProviderConfig(
                id="openai",
                keys=["sk-a"],
                timeout_s=30,
                retry_attempts=2,
                retry_backoff_s=0.5,
            ),
            FrontierProviderConfig(
                id="anthropic",
                keys=["sk-b"],
                timeout_s=60,
                retry_attempts=0,
            ),
        )
        pool = build_frontier_pool(settings)
        openai, anthropic = pool.slots
        assert openai.executor.timeout == 30.0
        assert openai.executor.retry.attempts == 2
        assert openai.executor.retry.base_delay == pytest.approx(0.5)
        assert anthropic.executor.timeout == 60.0
        # 0 retries → one attempt (same clamp as RetryPolicy).
        assert anthropic.executor.retry.attempts == 1
        assert anthropic.executor.retry.base_delay == pytest.approx(
            settings.upstream.retry.base_delay_ms / 1000
        )


class TestLocalTierTimeout:
    def test_models_timeout_s_overrides_per_tier(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings()
        settings.models.timeout_s = {"L3": 45.0, "L5": 180.0}
        from daari.router.router import AppContext

        ctx = AppContext.from_settings(settings)
        assert ctx.router.ollama_l3.timeout == 45.0
        assert ctx.router.ollama_l4.timeout == settings.upstream.local_timeout_seconds
        assert ctx.router.ollama_l5.timeout == 180.0

    def test_defaults_unchanged_without_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings()
        from daari.router.router import AppContext

        ctx = AppContext.from_settings(settings)
        assert ctx.router.ollama_l3.timeout == 120.0
        assert ctx.router.ollama_l4.timeout == 120.0
        assert ctx.router.ollama_l5.timeout == 120.0
        assert settings.upstream.frontier_timeout_seconds == 90.0
        assert settings.upstream.retry.attempts == 3


class TestFailoverBudgets:
    @pytest.mark.asyncio
    async def test_exhausted_retries_advance_the_chain(self):
        primary_transport, primary_calls = _sequence_transport([(503, {"error": "busy"})])
        secondary_transport, secondary_calls = _sequence_transport(
            [(200, _chat_completion("from-secondary"))]
        )
        primary = FrontierExecutor(
            base_url="http://primary",
            default_model="a",
            api_key="k1",
            provider="primary",
            timeout=30.0,
            retry=RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0),
            transport=primary_transport,
        )
        secondary = FrontierExecutor(
            base_url="http://secondary",
            default_model="b",
            api_key="k2",
            provider="secondary",
            timeout=60.0,
            retry=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
            transport=secondary_transport,
        )
        pool = FrontierPool(
            slots=[
                ProviderSlot(id="primary", executor=primary, keys=["k1"]),
                ProviderSlot(id="secondary", executor=secondary, keys=["k2"]),
            ]
        )

        response = await pool.execute(_request(), escalated_from="L5", local_confidence=0.2)

        assert response.content == "from-secondary"
        assert response.daari_meta.provider_id == "secondary"
        assert len(primary_calls) == 2, "primary spent its own retry budget then yielded"
        assert len(secondary_calls) == 1

    @pytest.mark.asyncio
    async def test_timeout_does_not_consume_the_next_provider_budget(self):
        """A timed-out provider must not shrink the next slot's retry window."""
        primary_transport, primary_calls = _sequence_transport(
            [httpx.ReadTimeout("primary hung")]
        )
        secondary_transport, secondary_calls = _sequence_transport(
            [(503, {"error": "busy"}), (200, _chat_completion("recovered"))]
        )
        primary = FrontierExecutor(
            base_url="http://primary",
            default_model="a",
            api_key="k1",
            provider="primary",
            timeout=0.05,
            retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0),
            transport=primary_transport,
        )
        secondary = FrontierExecutor(
            base_url="http://secondary",
            default_model="b",
            api_key="k2",
            provider="secondary",
            timeout=30.0,
            retry=RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0),
            transport=secondary_transport,
        )
        pool = FrontierPool(
            slots=[
                ProviderSlot(id="primary", executor=primary, keys=["k1"]),
                ProviderSlot(id="secondary", executor=secondary, keys=["k2"]),
            ]
        )

        response = await pool.execute(_request(), escalated_from="L5", local_confidence=0.2)

        assert response.content == "recovered"
        assert len(primary_calls) == 1
        assert len(secondary_calls) == 2, "secondary still used its own retry budget"
        assert secondary.timeout == 30.0


class TestRoutePreviewPolicy:
    def test_preview_shows_effective_per_entry_policy(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        settings = Settings()
        settings.models.timeout_s = {"L3": 45.0}
        settings.frontier = FrontierSettings(
            enabled=True,
            providers=[
                FrontierProviderConfig(
                    id="openai",
                    keys=["sk-a"],
                    timeout_s=30,
                    retry_attempts=2,
                    retry_backoff_s=0.5,
                ),
                FrontierProviderConfig(id="anthropic", keys=["sk-b"]),
            ],
        )
        from daari.router.router import AppContext

        preview = AppContext.from_settings(settings).router.preview_initial_tier(_request())
        assert preview["tier"] == "L3"
        assert preview["policy"]["timeout_s"] == 45.0
        assert preview["policy"]["retry_attempts"] == settings.upstream.retry.attempts
        ids = [entry["id"] for entry in preview["chain"]]
        assert ids[:3] == ["L3", "L4", "L5"]
        assert "openai" in ids and "anthropic" in ids
        openai = next(entry for entry in preview["chain"] if entry["id"] == "openai")
        anthropic = next(entry for entry in preview["chain"] if entry["id"] == "anthropic")
        l3 = next(entry for entry in preview["chain"] if entry["id"] == "L3")
        l4 = next(entry for entry in preview["chain"] if entry["id"] == "L4")
        assert openai["timeout_s"] == 30.0
        assert openai["retry_attempts"] == 2
        assert openai["retry_backoff_s"] == pytest.approx(0.5)
        assert anthropic["timeout_s"] == settings.upstream.frontier_timeout_seconds
        assert anthropic["retry_attempts"] == settings.upstream.retry.attempts
        assert l3["timeout_s"] == 45.0
        assert l4["timeout_s"] == settings.upstream.local_timeout_seconds
