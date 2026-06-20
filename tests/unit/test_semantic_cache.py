from __future__ import annotations

import pytest

from daari.cache.semantic import (
    SemanticCache,
    cosine_similarity,
    extract_embed_text,
    semantic_context_key,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta


class StaticEmbedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float] | None:
        self.calls.append(text)
        return self.vectors.get(text)


class TestSemanticHelpers:
    def test_cosine_similarity_identical(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_extract_embed_text_includes_roles(self):
        request = InternalRequest(
            messages=[
                Message(role="user", content="hello"),
                Message(role="assistant", content="hi there"),
            ],
            model="llama3.2:3b",
        )
        text = extract_embed_text(request)
        assert "user:hello" in text
        assert "assistant:hi there" in text

    def test_semantic_context_key_ignores_message_content(self):
        a = InternalRequest(
            messages=[Message(role="user", content="one")],
            model="llama3.2:3b",
            temperature=0.7,
        )
        b = InternalRequest(
            messages=[Message(role="user", content="two")],
            model="llama3.2:3b",
            temperature=0.7,
        )
        assert semantic_context_key(a) == semantic_context_key(b)

    def test_semantic_context_key_differs_on_temperature(self):
        base = InternalRequest(
            messages=[Message(role="user", content="x")],
            model="llama3.2:3b",
        )
        warm = InternalRequest(
            messages=[Message(role="user", content="x")],
            model="llama3.2:3b",
            temperature=0.2,
        )
        assert semantic_context_key(base) != semantic_context_key(warm)

    def test_semantic_context_key_differs_on_tier_override(self):
        plain = InternalRequest(
            messages=[Message(role="user", content="x")],
            model="llama3.2:3b",
        )
        override = InternalRequest(
            messages=[Message(role="user", content="x")],
            model="llama3.2:3b",
            meta=RequestMeta(tier_override="L3"),
        )
        assert semantic_context_key(plain) != semantic_context_key(override)


class TestSemanticCache:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_disabled(self, tmp_path):
        embedder = StaticEmbedder({"user:hi": [1.0, 0.0]})
        cache = SemanticCache(str(tmp_path / "l1"), embedder, enabled=False)
        request = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
        )
        hit, score = await cache.get(request)
        assert hit is None
        assert score is None
        assert embedder.calls == []

    @pytest.mark.asyncio
    async def test_put_and_get_similar_prompt(self, tmp_path):
        original_text = "user:Write a commit message for this diff"
        paraphrase_text = "user:Please draft a commit message for the diff"
        embedder = StaticEmbedder(
            {
                original_text: [1.0, 0.0, 0.0],
                paraphrase_text: [0.99, 0.01, 0.0],
            }
        )
        cache = SemanticCache(
            str(tmp_path / "l1"),
            embedder,
            enabled=True,
            similarity_threshold=0.92,
        )
        original = InternalRequest(
            messages=[Message(role="user", content="Write a commit message for this diff")],
            model="llama3.2:3b",
        )
        response = InternalResponse(
            content="feat: add widget",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )
        await cache.put(original, response)

        paraphrase = InternalRequest(
            messages=[Message(role="user", content="Please draft a commit message for the diff")],
            model="llama3.2:3b",
        )
        hit, score = await cache.get(paraphrase)
        assert hit is not None
        assert hit.content == "feat: add widget"
        assert score is not None
        assert score >= 0.92

    @pytest.mark.asyncio
    async def test_get_misses_below_threshold(self, tmp_path):
        text_a = "user:explain microservices"
        text_b = "user:what is the weather"
        embedder = StaticEmbedder(
            {
                text_a: [1.0, 0.0],
                text_b: [0.0, 1.0],
            }
        )
        cache = SemanticCache(
            str(tmp_path / "l1"),
            embedder,
            enabled=True,
            similarity_threshold=0.92,
        )
        request_a = InternalRequest(
            messages=[Message(role="user", content="explain microservices")],
            model="llama3.2:3b",
        )
        response = InternalResponse(
            content="answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )
        await cache.put(request_a, response)

        request_b = InternalRequest(
            messages=[Message(role="user", content="what is the weather")],
            model="llama3.2:3b",
        )
        hit, score = await cache.get(request_b)
        assert hit is None
        assert score is None or score < 0.92

    @pytest.mark.asyncio
    async def test_max_entries_evicts_oldest(self, tmp_path):
        axes = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        embedder = StaticEmbedder(
            {f"user:prompt-{i}": axes[i] for i in range(3)}
        )
        cache = SemanticCache(
            str(tmp_path / "l1"),
            embedder,
            enabled=True,
            similarity_threshold=0.5,
            max_entries=2,
        )
        for i in range(3):
            request = InternalRequest(
                messages=[Message(role="user", content=f"prompt-{i}")],
                model="llama3.2:3b",
            )
            response = InternalResponse(
                content=f"resp-{i}",
                model="llama3.2:3b",
                daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
            )
            await cache.put(request, response)

        first = InternalRequest(
            messages=[Message(role="user", content="prompt-0")],
            model="llama3.2:3b",
        )
        hit, _ = await cache.get(first)
        assert hit is None

        last = InternalRequest(
            messages=[Message(role="user", content="prompt-2")],
            model="llama3.2:3b",
        )
        hit, _ = await cache.get(last)
        assert hit is not None
        assert hit.content == "resp-2"
