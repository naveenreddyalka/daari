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

    def test_extract_embed_text_includes_audio_cache_tokens(self):
        """#1001: different clips with the same caption must not share an L1 embed."""
        from daari.gateway.internal import ContentAudio

        caption = "what did I say?"
        a = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content=caption,
                    audio=[ContentAudio(data="clip-a", format="wav")],
                )
            ],
            model="llama3.2:3b",
        )
        b = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content=caption,
                    audio=[ContentAudio(data="clip-b", format="wav")],
                )
            ],
            model="llama3.2:3b",
        )
        text_a = extract_embed_text(a)
        text_b = extract_embed_text(b)
        token_a = a.messages[0].audio[0].cache_token()
        token_b = b.messages[0].audio[0].cache_token()
        assert token_a in text_a
        assert token_b in text_b
        assert text_a != text_b
        assert caption in text_a

    def test_extract_embed_text_text_only_unchanged(self):
        """#1001: text-only requests keep the pre-change embed string."""
        request = InternalRequest(
            messages=[
                Message(role="user", content="hello"),
                Message(role="assistant", content="hi there"),
            ],
            model="llama3.2:3b",
        )
        assert extract_embed_text(request) == "user:hello\nassistant:hi there"

    def test_extract_embed_text_includes_image_cache_tokens(self):
        """#1029: different images with the same caption must not share an L1 embed."""
        from daari.gateway.internal import ContentImage

        caption = "what is in this picture?"
        a = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content=caption,
                    images=[ContentImage(data="img-a", media_type="image/png")],
                )
            ],
            model="llama3.2:3b",
        )
        b = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content=caption,
                    images=[ContentImage(data="img-b", media_type="image/png")],
                )
            ],
            model="llama3.2:3b",
        )
        text_a = extract_embed_text(a)
        text_b = extract_embed_text(b)
        token_a = a.messages[0].images[0].cache_token()
        token_b = b.messages[0].images[0].cache_token()
        assert token_a in text_a
        assert token_b in text_b
        assert text_a != text_b
        assert caption in text_a

    def test_extract_embed_text_audio_only_unchanged_by_image_fold(self):
        """#1029: audio-only embed strings stay as after #1001."""
        from daari.gateway.internal import ContentAudio

        request = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="caption",
                    audio=[ContentAudio(data="clip-a", format="wav")],
                )
            ],
            model="llama3.2:3b",
        )
        token = request.messages[0].audio[0].cache_token()
        assert extract_embed_text(request) == f"user:caption|audio:{token}"

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


class ModelTaggedEmbedder:
    def __init__(self, model: str, vectors: dict[str, list[float]]) -> None:
        self.model = model
        self.vectors = vectors
        self.calls = 0

    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        self.calls += 1
        return self.vectors.get(text)


@pytest.mark.asyncio
async def test_embedding_model_change_yields_clean_miss(tmp_path):
    """Entries under embed model A are not candidates under model B (#845)."""
    text = "user:same prompt"
    vectors = {text: [1.0, 0.0, 0.0]}
    a = ModelTaggedEmbedder("nomic-a", vectors)
    b = ModelTaggedEmbedder("nomic-b", vectors)
    request = InternalRequest(
        messages=[Message(role="user", content="same prompt")],
        model="llama3.2:3b",
    )
    response = InternalResponse(
        content="answer",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
    )
    cache_a = SemanticCache(str(tmp_path / "l1a"), a, enabled=True, similarity_threshold=0.5)
    await cache_a.put(request, response)
    hit, score = await cache_a.nearest(request)
    assert hit is not None and score >= 0.5

    cache_b = SemanticCache(str(tmp_path / "l1a"), b, enabled=True, similarity_threshold=0.5)
    # Same on-disk entries, different embedder identity → miss (no cross-model hit).
    miss, miss_score = await cache_b.nearest(request)
    assert miss is None
    assert miss_score == 0.0
    assert semantic_context_key(request, embedding_model="nomic-a") != semantic_context_key(
        request, embedding_model="nomic-b"
    )


def test_trim_prefers_dropping_stale_embed_rows(tmp_path):
    embedder = ModelTaggedEmbedder("live", {})
    cache = SemanticCache(str(tmp_path / "trim"), embedder, enabled=True, max_entries=2)
    entries = [
        {"context_key": "m|0.7||embed:old", "answer_hash": "1"},
        {"context_key": "m|0.7||embed:old", "answer_hash": "2"},
        {"context_key": "m|0.7||embed:live", "answer_hash": "3"},
        {"context_key": "m|0.7||embed:live", "answer_hash": "4"},
    ]
    trimmed = cache._trim_entries(entries)
    assert len(trimmed) == 2
    assert all("embed:live" in e["context_key"] for e in trimmed)
