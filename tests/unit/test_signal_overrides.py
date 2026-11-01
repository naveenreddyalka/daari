"""Request-fact signals + opt-in routing.signal_overrides (#1996)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from daari.config.settings import RoutingSettings, SignalOverrideRule
from daari.gateway.internal import ContentImage, InternalRequest, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.router.profile import PromptProfile, build_prompt_profile
from daari.router.signals import (
    apply_signal_override,
    context_token_bucket,
    extract_signals,
    match_signal_override,
)


def _req(**kwargs) -> InternalRequest:
    messages = kwargs.pop("messages", [Message(role="user", content="hello there")])
    meta = kwargs.pop("meta", RequestMeta())
    return InternalRequest(messages=messages, model="daari", meta=meta, **kwargs)


def test_extract_signals_defaults():
    request = _req()
    profile = build_prompt_profile(request)
    signals = extract_signals(request, profile)
    assert signals["has_images"] is False
    assert signals["has_tools"] is False
    assert signals["tool_count"] == 0
    assert signals["approx_context_tokens"] == context_token_bucket(profile.prompt_tokens_est)
    assert signals["client_agent"] == "none"
    assert signals["category"] == profile.category
    assert signals["complexity"] == profile.complexity
    assert signals["phase"] is None
    assert set(signals.keys()) <= {
        "has_images",
        "has_tools",
        "tool_count",
        "approx_context_tokens",
        "client_agent",
        "category",
        "complexity",
        "phase",
    }


def test_extract_signals_images_tools_agent():
    request = _req(
        messages=[
            Message(
                role="user",
                content="look",
                images=[ContentImage(data="AAAA", media_type="image/png")],
            )
        ],
        tools=[{"type": "function", "function": {"name": "a"}}, {"type": "function", "function": {"name": "b"}}],
        meta=RequestMeta(user_agent="Cursor/1.0", client_id="cursor"),
    )
    profile = PromptProfile(category="chat", complexity="trivial", prompt_tokens_est=100)
    signals = extract_signals(request, profile, phase="implement")
    assert signals["has_images"] is True
    assert signals["has_tools"] is True
    assert signals["tool_count"] == 2
    assert signals["client_agent"] == "cursor"
    assert signals["phase"] == "implement"


def test_context_token_buckets():
    assert context_token_bucket(50) == "lt_1k"
    assert context_token_bucket(1000) == "1k_4k"
    assert context_token_bucket(4000) == "4k_16k"
    assert context_token_bucket(16000) == "gte_16k"


def test_match_first_wins_and_passthrough():
    signals = {
        "has_images": True,
        "category": "chat",
        "client_agent": "cursor",
        "approx_context_tokens": "lt_1k",
        "has_tools": False,
        "tool_count": 0,
        "complexity": "trivial",
        "phase": None,
    }
    rules = [
        SignalOverrideRule(id="images", match={"has_images": True}, category="doc_qa"),
        SignalOverrideRule(id="cursor", match={"client_agent": "cursor"}, max_tier="L3"),
    ]
    matched = match_signal_override(signals, rules)
    assert matched is not None
    assert matched.id == "images"

    no_match = match_signal_override(
        {**signals, "has_images": False, "client_agent": "none"},
        rules,
    )
    assert no_match is None


def test_apply_override_levers():
    profile = PromptProfile(category="chat", complexity="standard", prompt_tokens_est=10)
    request = _req()
    rule = SignalOverrideRule(
        id="pin",
        match={"category": "chat"},
        category="code_gen",
        max_tier="L4",
        tier_pin="L3",
    )
    new_profile, levers = apply_signal_override(profile, request, rule)
    assert new_profile.category == "code_gen"
    assert levers["max_tier"] == "L4"
    assert levers["tier_pin"] == "L3"
    assert request.meta.tier_override == "L3"
    assert request.meta.tier_cap == "L4"


def test_signal_override_rule_rejects_bad_tier():
    with pytest.raises(ValidationError):
        SignalOverrideRule(id="bad", match={"has_images": True}, max_tier="L9")


def test_signal_override_rejects_typo_match_key():
    with pytest.raises(ValidationError, match=r"typo-key|has_image|unknown match key"):
        SignalOverrideRule(id="typo-key", match={"has_image": True}, category="doc_qa")


def test_signal_override_rejects_bad_context_bucket():
    with pytest.raises(ValidationError, match=r"bad-bucket|approx_context_tokens|4000"):
        SignalOverrideRule(
            id="bad-bucket",
            match={"approx_context_tokens": "4000"},
            max_tier="L4",
        )


def test_signal_override_rejects_bad_match_value_type():
    with pytest.raises(ValidationError, match=r"bad-type|has_images|list|type"):
        SignalOverrideRule(id="bad-type", match={"has_images": [True]}, category="doc_qa")


def test_signal_override_rejects_empty_match():
    with pytest.raises(ValidationError, match=r"empty-match|empty match"):
        SignalOverrideRule(id="empty-match", match={}, category="doc_qa")


def test_signal_override_rejects_leverless_rule():
    with pytest.raises(ValidationError, match=r"no-lever|lever|category|max_tier|tier_pin"):
        SignalOverrideRule(id="no-lever", match={"has_images": True})


def test_signal_override_valid_rule_loads():
    rule = SignalOverrideRule(
        id="ok",
        match={"has_images": True, "approx_context_tokens": "4k_16k", "tool_count": 2},
        category="doc_qa",
        max_tier="L4",
    )
    assert rule.id == "ok"
    assert rule.match["approx_context_tokens"] == "4k_16k"


def test_config_validate_surfaces_signal_override_rule_id(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from daari.cli.app import app as cli_app

    monkeypatch.setenv("HOME", str(tmp_path))
    path = tmp_path / "config.yaml"
    path.write_text(
        "routing:\n"
        "  signal_overrides:\n"
        "    - id: dead-typo\n"
        "      match: { has_image: true }\n"
        "      category: doc_qa\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "dead-typo" in combined


def test_routing_settings_default_empty_overrides():
    routing = RoutingSettings()
    assert routing.signal_overrides == []


@pytest.mark.asyncio
async def test_router_attaches_signals_and_applies_override(tmp_path, monkeypatch):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(
                    tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    metrics = Metrics()
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=metrics,
        signal_overrides=[
            SignalOverrideRule(
                id="img-doc",
                match={"has_images": True},
                category="doc_qa",
                max_tier="L3",
            )
        ],
    )
    request = _req(
        messages=[
            Message(
                role="user",
                content="describe this",
                images=[ContentImage(data="AAAA", media_type="image/png")],
            )
        ]
    )
    response = await router.route(request)
    assert response.daari_meta.signals is not None
    assert response.daari_meta.signals["has_images"] is True
    assert response.daari_meta.task_type == "doc_qa"
    snap = metrics.snapshot(include_histograms=True)
    so = snap.get("signal_override", {}) or {}
    assert so.get("img-doc:global", 0) >= 1 or so.get("img-doc", 0) >= 1
    assert any(event == "signal_override" for event, _ in events)
