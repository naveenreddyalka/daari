"""F6 product boundaries: local-first scope gate."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import BoundariesSettings, Settings
from daari.gateway.boundaries import (
    BoundaryDecision,
    BoundaryEngine,
    engine_from_settings,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
    )


def _fintech_settings(**kwargs) -> BoundariesSettings:
    data = {
        "enabled": True,
        "mode": "block",
        "product_name": "CK Assist",
        "product_description": "Credit scores, cards, loans, and account help only.",
        "allow_topics": ["credit score", "credit card", "loan"],
        "deny_topics": ["python", "wedding", "novel"],
        "examples_in": ["Why did my score drop?", "Best travel card?"],
        "examples_out": ["Write a Python scraper", "Plan my wedding"],
        "refuse_message": "I only help with credit and CK account questions.",
        "clear_out_threshold": 0.7,
        "clear_in_threshold": 0.7,
        "stages_b0": True,
        "stages_b1": True,
        "stages_b2": False,
        "stages_b3": False,
    }
    data.update(kwargs)
    return BoundariesSettings.model_validate(data)


def test_disabled_engine_is_none():
    settings = Settings()
    assert settings.boundaries.enabled is False
    assert engine_from_settings(settings) is None


def test_b0_clear_out_via_deny_topic():
    engine = BoundaryEngine.from_settings(_fintech_settings())
    decision = engine.classify_b0(_request("Write a Python script for me"))
    assert decision.label == "out"
    assert decision.confidence >= 0.7
    assert decision.stage == "b0"


def test_b0_clear_in_via_allow_topic():
    engine = BoundaryEngine.from_settings(_fintech_settings())
    decision = engine.classify_b0(_request("Why did my credit score drop last month?"))
    assert decision.label == "in"
    assert decision.confidence >= 0.7


def test_b0_ambiguous_when_no_topic_hit():
    engine = BoundaryEngine.from_settings(_fintech_settings())
    decision = engine.classify_b0(_request("What is the weather in Austin?"))
    assert decision.label == "ambiguous"


@pytest.mark.asyncio
async def test_router_blocks_clear_out_without_model(tmp_path):
    calls = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content="should-not-run",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    engine = BoundaryEngine.from_settings(_fintech_settings())
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        metrics=Metrics(),
        boundaries=engine,
    )
    resp = await router.route(_request("Help me write a Python novel chapter"))
    assert calls["n"] == 0
    assert resp.daari_meta.tier == "boundary"
    assert "credit" in resp.content.lower() or "CK" in resp.content
    assert resp.daari_meta.boundary is not None
    assert resp.daari_meta.boundary["label"] == "out"


@pytest.mark.asyncio
async def test_router_warn_mode_still_answers(tmp_path):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="model-answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    engine = BoundaryEngine.from_settings(_fintech_settings(mode="warn"))
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        metrics=Metrics(),
        boundaries=engine,
    )
    resp = await router.route(_request("Write a Python scraper"))
    assert resp.content == "model-answer"
    assert resp.daari_meta.boundary is not None
    assert resp.daari_meta.boundary["label"] == "out"
    assert resp.daari_meta.warning


@pytest.mark.asyncio
async def test_b1_judge_resolves_ambiguous(tmp_path):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="in-scope answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def fake_judge(text: str, settings: BoundariesSettings) -> BoundaryDecision:
        return BoundaryDecision(label="in", confidence=0.9, stage="b1", reason="judge")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    engine = BoundaryEngine.from_settings(_fintech_settings(), judge=fake_judge)
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        metrics=Metrics(),
        boundaries=engine,
    )
    resp = await router.route(_request("What is the weather in Austin?"))
    assert resp.content == "in-scope answer"
    assert resp.daari_meta.boundary["stage"] == "b1"
    assert resp.daari_meta.boundary["label"] == "in"


@pytest.mark.asyncio
async def test_b1_judge_out_blocks(tmp_path):
    calls = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content="should-not-run",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def fake_judge(text: str, settings: BoundariesSettings) -> BoundaryDecision:
        return BoundaryDecision(label="out", confidence=0.95, stage="b1", reason="judge_out")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    engine = BoundaryEngine.from_settings(_fintech_settings(), judge=fake_judge)
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        metrics=Metrics(),
        boundaries=engine,
    )
    resp = await router.route(_request("What is the weather in Austin?"))
    assert calls["n"] == 0
    assert resp.daari_meta.tier == "boundary"
    assert resp.daari_meta.boundary["stage"] == "b1"
    assert resp.daari_meta.boundary["label"] == "out"


def test_persist_includes_boundaries(tmp_path):
    from daari.config.persist import persist_safe_config

    path = tmp_path / "config.yaml"
    path.write_text("routing:\n  prefer: balanced\n", encoding="utf-8")
    persist_safe_config(
        {
            "boundaries": {
                "enabled": True,
                "mode": "warn",
                "product_name": "Demo",
                "allow_topics": ["mortgage"],
            }
        },
        config_path=path,
    )
    text = path.read_text(encoding="utf-8")
    assert "boundaries:" in text
    assert "Demo" in text
    assert "mortgage" in text


def test_policy_sync_applies_boundaries(settings):
    from daari.enterprise.policy_sync import apply_policy_to_runtime
    from daari.router.router import AppContext

    settings.boundaries.enabled = False
    ctx = AppContext.from_settings(settings)
    assert ctx.router.boundaries is None
    applied = apply_policy_to_runtime(
        settings,
        ctx.router,
        {
            "boundaries": {
                "enabled": True,
                "mode": "block",
                "product_name": "Synced Bot",
                "allow_topics": ["apr"],
                "deny_topics": ["python"],
            }
        },
    )
    assert applied.get("boundaries.enabled") is True
    assert ctx.router.boundaries is not None
    assert ctx.router.boundaries.settings.product_name == "Synced Bot"


@pytest.mark.asyncio
async def test_metrics_record_boundary_decision(tmp_path):
    metrics = Metrics()
    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="x",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        metrics=metrics,
        boundaries=BoundaryEngine.from_settings(_fintech_settings()),
    )
    await router.route(_request("Write a Python scraper"))
    snap = metrics.snapshot(include_histograms=True)
    assert snap["boundaries"].get("b0:out", 0) >= 1


@pytest.mark.asyncio
async def test_config_editor_exposes_boundaries(settings):
    from httpx import ASGITransport, AsyncClient

    from daari.router.router import AppContext
    from daari.server.app import create_app

    settings.observability.config_editor = True
    settings.boundaries.enabled = True
    settings.boundaries.product_name = "CK Assist"
    settings.boundaries.mode = "warn"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        assert body["boundaries"]["enabled"] is True
        assert body["boundaries"]["product_name"] == "CK Assist"
        patched = await client.patch(
            "/v1/daari/config",
            json={
                "boundaries": {
                    "enabled": True,
                    "mode": "block",
                    "product_name": "Mortgage Bot",
                    "allow_topics": ["mortgage", "apr"],
                }
            },
        )
        assert patched.status_code == 200
        assert patched.json()["boundaries"]["product_name"] == "Mortgage Bot"
        assert patched.json()["boundaries"]["mode"] == "block"
        assert app.state.ctx.router.boundaries is not None
        assert app.state.ctx.router.boundaries.settings.product_name == "Mortgage Bot"


def test_startup_warns_when_b3_cannot_run():
    from daari.gateway.boundaries import startup_warnings

    settings = Settings.model_validate(
        {
            "boundaries": {"enabled": True, "stages_b3": True},
            "frontier": {"enabled": False},
        }
    )
    warnings = startup_warnings(settings)
    assert any("b3" in w.lower() and "frontier" in w.lower() for w in warnings)


def test_majority_vote_needs_quorum():
    from daari.gateway.boundaries import majority_vote

    votes = [
        BoundaryDecision("in", 0.8, "b0"),
        BoundaryDecision("in", 0.7, "b1"),
        BoundaryDecision("out", 0.9, "b0"),
    ]
    decided = majority_vote(votes, quorum=2)
    assert decided is not None
    assert decided.label == "in"
    assert decided.stage == "b2"


@pytest.mark.asyncio
async def test_b2_quorum_resolves_ambiguous(monkeypatch):
    engine = BoundaryEngine.from_settings(
        _fintech_settings(stages_b2=True, stages_b1=True, stages_b3=False, quorum_votes=2)
    )

    async def judge(text, settings):
        return BoundaryDecision("in", 0.9, "b1", "judge")

    engine.judge = judge
    # B0 is ambiguous; B1 votes in; default_local_judge also votes in via
    # product-description overlap ("account help") — quorum 2 → B2.
    decision = await engine.classify(_request("Can you help with my account?"))
    assert decision.stage == "b2"
    assert decision.label == "in"


@pytest.mark.asyncio
async def test_b3_respects_daily_budget():
    spent = {"n": 0}

    async def frontier_judge(text, settings):
        spent["n"] += 1
        return BoundaryDecision("out", 0.95, "b3", "frontier")

    engine = BoundaryEngine.from_settings(
        _fintech_settings(
            stages_b2=False,
            stages_b1=False,
            stages_b3=True,
            frontier_judge_daily_budget_usd=0.0,
        )
    )
    engine.frontier_judge = frontier_judge
    decision = await engine.classify(_request("What is the weather in Austin?"))
    assert spent["n"] == 0
    assert decision.label == "ambiguous"


@pytest.mark.asyncio
async def test_b3_consults_frontier_within_budget():
    spent = {"n": 0}

    async def frontier_judge(text, settings):
        spent["n"] += 1
        return BoundaryDecision("out", 0.95, "b3", "frontier")

    engine = BoundaryEngine.from_settings(
        _fintech_settings(
            stages_b2=False,
            stages_b1=False,
            stages_b3=True,
            frontier_judge_daily_budget_usd=0.5,
        )
    )
    engine.frontier_judge = frontier_judge
    decision = await engine.classify(_request("What is the weather in Austin?"))
    assert spent["n"] == 1
    assert decision.stage == "b3"
    assert decision.label == "out"


@pytest.mark.asyncio
async def test_b0_embed_cosine_classifies_when_lexical_misses():
    class TopicVec:
        async def embed(self, text: str, *, model: str | None = None):
            lower = text.lower()
            if any(w in lower for w in ("python", "scrape", "scraper", "harvest")):
                return [1.0, 0.0]
            if any(w in lower for w in ("credit", "loan", "card", "score")):
                return [0.0, 1.0]
            return [0.0, 0.0]

    engine = BoundaryEngine.from_settings(_fintech_settings())
    engine.embedder = TopicVec()
    decision = await engine.classify(_request("Help me scrape a few sites"))
    assert decision.label == "out"
    assert decision.stage == "b0"


@pytest.mark.asyncio
async def test_b0_embed_falls_back_when_embedder_fails():
    class Boom:
        async def embed(self, text: str, *, model: str | None = None):
            raise RuntimeError("down")

    engine = BoundaryEngine.from_settings(_fintech_settings())
    engine.embedder = Boom()
    decision = engine.classify_b0(_request("Write a Python script for me"))
    assert decision.label == "out"
    assert decision.stage == "b0"


def test_fixture_false_refuse_is_zero():
    from daari.gateway.boundaries import score_boundary_fixtures

    report = score_boundary_fixtures(
        BoundaryEngine.from_settings(_fintech_settings(stages_b1=False, stages_b2=False, stages_b3=False))
    )
    assert report["false_refuse"] == 0
    assert report["total"] >= 6
