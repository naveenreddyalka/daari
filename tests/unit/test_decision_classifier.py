"""Optional decision-model complexity classifier for tier pick (#1292)."""

from __future__ import annotations

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, InternalResponse, Message, DaariMeta
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.decision_classifier import (
    classification_from_answers,
    map_choice_to_complexity,
    map_score_to_complexity,
)
from daari.router.router import OllamaExecutor, Router


class NoopEmbedder:
    async def embed(self, text: str, *, model: str | None = None):
        return None


def _router(tmp_path, *, enabled: bool = True, agent_turns: bool = False) -> Router:
    return Router(
        cache=ExactCache(path=str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"),
            embedder=NoopEmbedder(),
            enabled=False,
        ),
        ollama_l3=OllamaExecutor(
            base_url="http://ollama.test:11434",
            default_model="llama3.2:3b",
            tier="L3",
        ),
        ollama_l4=OllamaExecutor(
            base_url="http://ollama.test:11434",
            default_model="llama3.1:8b",
            tier="L4",
        ),
        ollama_l5=OllamaExecutor(
            base_url="http://ollama.test:11434",
            default_model="qwen2.5:14b",
            tier="L5",
        ),
        metrics=Metrics(),
        decision_classifier_enabled=enabled,
        decision_classifier_model="nimble",
        decision_classifier_timeout_seconds=2.0,
        decision_classifier_agent_turns=agent_turns,
    )


def _request(text: str = "hello") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def test_map_choice_and_score():
    assert map_choice_to_complexity("trivial") == "trivial"
    assert map_choice_to_complexity("L5") == "complex"
    assert map_score_to_complexity(0.1) == "trivial"
    assert map_score_to_complexity(0.5) == "standard"
    assert map_score_to_complexity(0.9) == "complex"
    mapped = classification_from_answers(
        model="nimble",
        answers={"difficulty": {"type": "choice", "choice": "complex", "confidence": 0.9}},
    )
    assert mapped is not None
    assert mapped.tier == "L5"
    assert mapped.complexity == "complex"


def test_settings_default_off(settings):
    assert settings.routing.decision_classifier.enabled is False
    assert settings.routing.decision_classifier.model == "nimble"


def test_disabled_path_unchanged(tmp_path):
    router = _router(tmp_path, enabled=False)
    request = _request("hi")
    # Short prompt → L3 via heuristics.
    assert router._choose_uncapped_tier(request) == "L3"
    assert request.meta.decision_tier is None


@pytest.mark.asyncio
async def test_enabled_path_influences_tier(tmp_path, monkeypatch):
    router = _router(tmp_path, enabled=True)

    async def fake_classify(**kwargs):
        from daari.router.decision_classifier import DecisionClassification

        return DecisionClassification(
            model="nimble",
            complexity="complex",
            tier="L5",
            answer={"type": "choice", "choice": "complex", "confidence": 0.95},
        )

    monkeypatch.setattr(
        "daari.router.decision_classifier.classify_via_systemone",
        fake_classify,
    )
    # Also patch the import site used by the router method.
    monkeypatch.setattr(
        "daari.router.router.classify_via_systemone",
        fake_classify,
        raising=False,
    )

    request = _request("hi")
    from daari.router.profile import build_prompt_profile

    profile = build_prompt_profile(request)
    # Patch via the module the router imports inside the method.
    import daari.router.decision_classifier as dc

    monkeypatch.setattr(dc, "classify_via_systemone", fake_classify)

    updated = await router._apply_decision_classifier(request, profile)
    assert updated.complexity == "complex"
    assert request.meta.decision_tier == "L5"
    assert router._choose_uncapped_tier(request, updated) == "L5"
    assert request.meta.decision_classifier["model"] == "nimble"


@pytest.mark.asyncio
async def test_failure_falls_back_to_heuristics(tmp_path, monkeypatch):
    router = _router(tmp_path, enabled=True)

    async def boom(**kwargs):
        raise RuntimeError("ollama down")

    import daari.router.decision_classifier as dc

    monkeypatch.setattr(dc, "classify_via_systemone", boom)

    request = _request("hi")
    from daari.router.profile import build_prompt_profile

    profile = build_prompt_profile(request)
    updated = await router._apply_decision_classifier(request, profile)
    assert updated.complexity == profile.complexity
    assert request.meta.decision_tier is None
    assert router._choose_uncapped_tier(request, updated) == "L3"


@pytest.mark.asyncio
async def test_route_records_decision_on_daari_meta(tmp_path, monkeypatch):
    router = _router(tmp_path, enabled=True)
    router.trace_store = TraceStore(path=str(tmp_path / "traces.sqlite3"), enabled=True)

    async def fake_classify(**kwargs):
        from daari.router.decision_classifier import DecisionClassification

        return DecisionClassification(
            model="nimble",
            complexity="standard",
            tier="L4",
            answer={"type": "choice", "choice": "standard"},
        )

    import daari.router.decision_classifier as dc

    monkeypatch.setattr(dc, "classify_via_systemone", fake_classify)

    async def fake_execute(self, request):
        return InternalResponse(
            content="ok enough length for confidence",
            model=self.default_model,
            daari_meta=DaariMeta(tier=self.tier, executor="ollama", latency_ms=1),
        )

    monkeypatch.setattr(OllamaExecutor, "execute", fake_execute)

    response = await router.route(_request("short ask"))
    assert response.daari_meta.decision is not None
    assert response.daari_meta.decision["tier"] == "L4"
    assert response.daari_meta.decision["model"] == "nimble"
    assert response.daari_meta.tier == "L4"
    assert response.daari_meta.complexity == "standard"
