"""Second-stage verification before serving an L1 hit (#168).

daari measured its semantic-cache false-hit rate but still served any hit above
a cosine threshold. Correct and incorrect similarity distributions overlap, so a
threshold alone cannot separate a paraphrase from a near-miss: "cost of 5 items"
and "cost of 6 items" are textually almost identical and semantically different.
"""

from __future__ import annotations

import pytest

from daari.cache.verify import LexicalVerifier, build_verifier
from daari.config.settings import L1CacheSettings
from daari.gateway.internal import InternalRequest, Message


def _verify(candidate: str, stored: str):
    return LexicalVerifier().verify(candidate, stored)


# --- near-misses that must be rejected --------------------------------------


@pytest.mark.parametrize(
    ("candidate", "stored", "label"),
    [
        ("what is 15% of 200", "what is 15% of 300", "differing numbers"),
        ("retry after 30 seconds", "retry after 30 minutes", "changed units"),
        ("how do I deploy to staging", "how do I deploy to production", "differing entity"),
        ("is this thread safe", "is this not thread safe", "negation flip"),
        ("which is greater, a or b", "which is less, a or b", "reversed comparison"),
        ("convert 10 km to miles", "convert 10 miles to km", "reversed units"),
        ("sort ascending by date", "sort descending by date", "reversed order"),
    ],
)
def test_near_misses_are_rejected(candidate, stored, label):
    result = _verify(candidate, stored)
    assert result.ok is False, f"{label}: should not serve a cached answer"
    assert result.reason, "a rejection must say why"


# --- paraphrases that must still be served ---------------------------------


@pytest.mark.parametrize(
    ("candidate", "stored"),
    [
        ("how do I list files", "how can I list files"),
        ("what does this function do?", "what does this function do"),
        ("explain the router module", "please explain the router module"),
        ("show me 5 examples of decorators", "show 5 examples of decorators"),
        ("how do I deploy to staging", "how do I deploy to Staging"),
    ],
)
def test_paraphrases_are_retained(candidate, stored):
    result = _verify(candidate, stored)
    assert result.ok is True, f"paraphrase wrongly rejected: {result.reason}"


def test_identical_text_passes():
    assert _verify("same question", "same question").ok is True


# --- configuration ----------------------------------------------------------


def test_lexical_is_the_default_mode():
    assert L1CacheSettings().verify == "lexical"


def test_build_verifier_modes():
    assert build_verifier("none") is None
    assert isinstance(build_verifier("lexical"), LexicalVerifier)
    assert build_verifier("unrecognised") is None, "unknown modes must not fail closed"


# --- cache integration ------------------------------------------------------


class _StubEmbedder:
    """Returns a fixed vector so every candidate looks like a cosine hit."""

    async def embed(self, text: str):
        return [1.0, 0.0, 0.0]


def _request(text: str) -> InternalRequest:
    return InternalRequest(model="daari", messages=[Message(role="user", content=text)])


@pytest.mark.asyncio
async def test_verified_near_miss_is_not_served(tmp_path):
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse

    cache = SemanticCache(
        str(tmp_path / "l1"),
        _StubEmbedder(),
        similarity_threshold=0.5,
        verifier=LexicalVerifier(),
    )
    stored = InternalResponse(
        content="30 is the answer",
        model="m",
        daari_meta=DaariMeta(tier="L3", executor="ollama"),
    )
    await cache.put(_request("what is 15% of 200"), stored)

    # Identical embeddings mean cosine similarity cannot tell these apart.
    hit, score = await cache.get(_request("what is 15% of 300"))
    assert hit is None, "verification must veto a cosine hit with a different number"

    same, _ = await cache.get(_request("what is 15% of 200"))
    assert same is not None, "the original question must still hit"


@pytest.mark.asyncio
async def test_unverifiable_legacy_entry_is_not_served(tmp_path):
    """Entries written before #168 have no prompt text, so they cannot be checked."""
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse

    cache = SemanticCache(
        str(tmp_path / "l1"),
        _StubEmbedder(),
        similarity_threshold=0.5,
        verifier=LexicalVerifier(),
    )
    await cache.put(
        _request("original question"),
        InternalResponse(
            content="answer", model="m", daari_meta=DaariMeta(tier="L3", executor="ollama")
        ),
    )
    entries = cache._load_entries()
    entries[0].pop("prompt_text", None)
    cache._save_entries(entries)

    hit, _ = await cache.get(_request("original question"))
    assert hit is None, "an entry with no stored text cannot be verified, so must not serve"


@pytest.mark.asyncio
async def test_verification_off_serves_the_near_miss(tmp_path):
    """Proves the veto above comes from verification, not from the threshold."""
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse

    cache = SemanticCache(
        str(tmp_path / "l1"), _StubEmbedder(), similarity_threshold=0.5, verifier=None
    )
    await cache.put(
        _request("what is 15% of 200"),
        InternalResponse(
            content="30", model="m", daari_meta=DaariMeta(tier="L3", executor="ollama")
        ),
    )
    hit, _ = await cache.get(_request("what is 15% of 300"))
    assert hit is not None, "without a verifier the near-miss is served — the bug being fixed"


@pytest.mark.asyncio
async def test_rejection_increments_the_avoided_counter(tmp_path):
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    cache = SemanticCache(
        str(tmp_path / "l1"),
        _StubEmbedder(),
        similarity_threshold=0.5,
        verifier=LexicalVerifier(),
        metrics=metrics,
    )
    await cache.put(
        _request("what is 15% of 200"),
        InternalResponse(
            content="30", model="m", daari_meta=DaariMeta(tier="L3", executor="ollama")
        ),
    )
    await cache.get(_request("what is 15% of 300"))
    snapshot = metrics.snapshot(include_histograms=True)
    assert snapshot["cache_false_hits_avoided"] == 1


def test_prometheus_exposes_the_avoided_counter():
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    metrics.record_false_hit_avoided()
    text = render_prometheus(metrics)
    assert "daari_cache_false_hits_avoided_total 1" in text


# --- latency budget ---------------------------------------------------------


def test_verification_is_cheap():
    """Verification must not eat the saving a cache hit exists to produce."""
    import time

    verifier = LexicalVerifier()
    candidate = "how do I configure the frontier tier with a 30 second timeout"
    stored = "how do I configure the frontier tier with a 60 second timeout"
    started = time.perf_counter()
    for _ in range(1000):
        verifier.verify(candidate, stored)
    per_call_ms = (time.perf_counter() - started) / 1000 * 1000
    assert per_call_ms < 1.0, f"lexical verification took {per_call_ms:.3f}ms per call"
