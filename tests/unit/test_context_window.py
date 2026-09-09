"""Pre-dispatch context-window escalation (#385)."""

from __future__ import annotations

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import InternalRequest, Message
from daari.observability.metrics import Metrics
from daari.router.profile import PromptProfile
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _router(tmp_path, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama=OllamaExecutor(base_url="http://test", default_model="llama3.2:3b"),
        metrics=Metrics(),
        **kwargs,
    )


def _request(text: str = "hi") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def test_oversized_prompt_skips_too_small_l3(tmp_path):
    router = _router(
        tmp_path,
        context_window_escalation=True,
        context_windows={"L3": 100, "L4": 8000, "L5": 32000},
        context_window_buffer=0.95,
    )
    profile = PromptProfile(category="chat", complexity="standard", prompt_tokens_est=1000)
    assert router._choose_initial_tier(_request(), profile) == "L4"


def test_unknown_window_is_left_alone(tmp_path):
    router = _router(
        tmp_path,
        context_window_escalation=True,
        context_windows={},
    )
    profile = PromptProfile(category="chat", complexity="standard", prompt_tokens_est=50_000)
    assert router._choose_initial_tier(_request(), profile) == "L3"


def test_disabled_flag_keeps_heuristic_tier(tmp_path):
    router = _router(
        tmp_path,
        context_window_escalation=False,
        context_windows={"L3": 100, "L4": 8000, "L5": 32000},
    )
    profile = PromptProfile(category="chat", complexity="standard", prompt_tokens_est=1000)
    assert router._choose_initial_tier(_request(), profile) == "L3"


def test_fitting_prompt_stays_on_l3(tmp_path):
    router = _router(
        tmp_path,
        context_window_escalation=True,
        context_windows={"L3": 8192, "L4": 32768, "L5": 131072},
    )
    profile = PromptProfile(category="chat", complexity="standard", prompt_tokens_est=200)
    assert router._choose_initial_tier(_request(), profile) == "L3"


def test_under_24k_chars_but_over_l3_window_still_escalates(tmp_path):
    """#401: context-window escalation alone hops; no 24k-char capability gate."""
    # ~20k chars ≈ 5k tokens under the old 24k threshold, but over a tiny L3 window.
    text = "word " * 4000
    assert len(text) < 24_000
    router = _router(
        tmp_path,
        context_window_escalation=True,
        context_windows={"L3": 100, "L4": 8000, "L5": 32000},
        context_window_buffer=0.95,
    )
    profile = PromptProfile(
        category="chat",
        complexity="standard",
        prompt_tokens_est=max(1, len(text) // 4),
    )
    assert router._choose_initial_tier(_request(text), profile) == "L4"
