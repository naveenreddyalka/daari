"""Prompt profile heuristics and category action policies (issue #19)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import CategoryPolicy
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.profile import PromptProfile, build_prompt_profile, categorize
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


class TestCategorize:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("write a pytest for the cache module", "test"),
            ("git rebase my branch onto main", "git"),
            ("run ruff and fix the lint errors", "lint"),
            ("fetch https://example.com and summarize", "fetch"),
            ("write a function that parses JSON into a dataclass", "code_gen"),
            ("implement a retry decorator with backoff", "code_gen"),
            ("explain what this function does and why", "code_explain"),
            ("how does this class handle concurrency?", "code_explain"),
            ("what is a semantic cache?", "doc_qa"),
            ("why is the sky blue?", "doc_qa"),
            ("hello there", "chat"),
            ("thanks, that worked great", "chat"),
        ],
    )
    def test_buckets(self, text: str, expected: str) -> None:
        assert categorize(text) == expected


class TestComplexity:
    def test_trivial_short_prompt(self):
        profile = build_prompt_profile(_request("hello there"))
        assert profile.complexity == "trivial"

    def test_standard_prompt(self):
        profile = build_prompt_profile(
            _request("write a function that parses JSON into a dataclass with validation")
        )
        assert profile.complexity == "standard"

    def test_complex_long_prompt(self):
        profile = build_prompt_profile(_request("word " * 300))
        assert profile.complexity == "complex"

    def test_complex_multi_code_fence(self):
        text = "fix this\n```py\na\n```\nand this\n```py\nb\n```"
        profile = build_prompt_profile(_request(text))
        assert profile.complexity == "complex"

    def test_tokens_estimate(self):
        profile = build_prompt_profile(_request("x" * 400))
        assert profile.prompt_tokens_est == 100


def _tiered_router(tmp_path, *, category_policies=None) -> Router:
    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier)

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        category_policies=category_policies or {},
    )


class TestCategoryPolicy:
    @pytest.mark.asyncio
    async def test_policy_tier_overrides_default_choice(self, tmp_path):
        # "hello there" is chat and would normally start at L3 (<=12 words).
        router = _tiered_router(tmp_path, category_policies={"chat": CategoryPolicy(tier="L4")})
        response = await router.route(_request("hello there"))
        assert response.daari_meta.tier == "L4"

    @pytest.mark.asyncio
    async def test_no_policy_keeps_default_choice(self, tmp_path):
        router = _tiered_router(tmp_path)
        response = await router.route(_request("hello there"))
        assert response.daari_meta.tier == "L3"

    @pytest.mark.asyncio
    async def test_header_override_beats_policy(self, tmp_path):
        router = _tiered_router(tmp_path, category_policies={"chat": CategoryPolicy(tier="L4")})
        request = _request("hello there")
        request.meta.tier_override = "L5"
        response = await router.route(request)
        assert response.daari_meta.tier == "L5"

    @pytest.mark.asyncio
    async def test_cache_skip_policy_bypasses_l0(self, tmp_path):
        router = _tiered_router(tmp_path, category_policies={"chat": CategoryPolicy(cache="skip")})
        first = await router.route(_request("hello there"))
        second = await router.route(_request("hello there"))
        assert first.daari_meta.tier == "L3"
        assert second.daari_meta.tier == "L3"  # would be L0 without the skip policy
        assert second.daari_meta.cache_hit is False

    @pytest.mark.asyncio
    async def test_profile_metadata_on_response(self, tmp_path):
        router = _tiered_router(tmp_path)
        response = await router.route(_request("what is a semantic cache?"))
        assert response.daari_meta.task_type == "doc_qa"
        assert response.daari_meta.complexity == "trivial"


def test_profile_model_shape():
    profile = build_prompt_profile(_request("hello there"))
    assert isinstance(profile, PromptProfile)
    assert profile.category == "chat"
    assert profile.prompt_tokens_est > 0
