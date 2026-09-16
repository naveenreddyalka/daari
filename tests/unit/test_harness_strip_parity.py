"""Regression corpus: Claude Code / Codex harness envelopes must not bump tier (#541).

Mirrors LiteLLM Sep 2026 Codex reminder markers plus Claude Code system catalogs.
"""

from __future__ import annotations

import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.profile import build_prompt_profile, strip_harness_text
from daari.router.router import OllamaExecutor, Router
from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from tests.conftest import NoopEmbedder

# --- Fixture shapes operators see from current harnesses ---

CODEX_ENVIRONMENT = (
    "<environment_context>\n"
    + ("cwd=/repo shell=zsh model=gpt-5\n" * 80)
    + "</environment_context>"
)
CODEX_PLUGINS = (
    "<recommended_plugins>\n"
    + ("plugin:code-search notes=catalog-entry\n" * 40)
    + "</recommended_plugins>"
)
CODEX_USER_INSTRUCTIONS = (
    "<user_instructions>\n"
    + ("Always prefer thorough unit tests and a dataclass pattern.\n" * 40)
    + "</user_instructions>"
)
CODEX_ENVIRONMENTS_INSTRUCTIONS = (
    "<environments_instructions>\n"
    + ("Repository coding standards: prefer careful concurrency modules.\n" * 40)
    + "</environments_instructions>"
)
CODEX_AGENTS_MD = (
    "# agents.md instructions for /repo\n"
    + ("Follow AGENTS.md: prefer functions, write pytest, tidy modules.\n" * 60)
    + "</instructions>"
)

CLAUDE_SYSTEM_CATALOG = (
    "You are Claude Code.\n"
    + ("Skill catalog entry: implement complex class decorator concurrency\n" * 200)
)
CLAUDE_REMINDER = (
    "<system-reminder>\n"
    + ("As of this turn, remember to write a function and run pytest.\n" * 40)
    + "</system-reminder>"
)

SHORT_TASK = "fix the typo"
CHAT_TASK = "hello there"


def _codex_user_payload(task: str) -> str:
    return "\n".join(
        [
            task,
            CODEX_ENVIRONMENT,
            CODEX_PLUGINS,
            CODEX_USER_INSTRUCTIONS,
            CODEX_ENVIRONMENTS_INSTRUCTIONS,
            CODEX_AGENTS_MD,
        ]
    )


def test_strip_removes_codex_parity_markers():
    blob = _codex_user_payload(SHORT_TASK)
    cleaned, removed = strip_harness_text(blob)
    assert SHORT_TASK in cleaned
    assert removed >= 1000
    assert "environment_context" not in cleaned.lower()
    assert "user_instructions" not in cleaned.lower()
    assert "environments_instructions" not in cleaned.lower()
    assert "recommended_plugins" not in cleaned.lower()
    assert "agents.md instructions" not in cleaned.lower()
    assert "</instructions>" not in cleaned.lower()


def test_codex_envelope_keeps_trivial_chat_category():
    """Harness code keywords must not reclassify a short chat ask (#541)."""
    request = InternalRequest(
        messages=[Message(role="user", content=_codex_user_payload(CHAT_TASK))],
        model="llama3.2:3b",
    )
    profile = build_prompt_profile(request)
    assert profile.category == "chat"
    assert profile.complexity == "trivial"
    assert profile.stripped_chars >= 1000
    # Full payload still counted for context-window escalation.
    assert profile.prompt_tokens_est == max(1, len(_codex_user_payload(CHAT_TASK)) // 4)


def test_codex_envelope_without_harness_aware_bumps_complexity():
    request = InternalRequest(
        messages=[Message(role="user", content=_codex_user_payload(SHORT_TASK))],
        model="llama3.2:3b",
    )
    aware = build_prompt_profile(request, harness_aware=True)
    naive = build_prompt_profile(request, harness_aware=False)
    assert aware.complexity == "trivial"
    assert naive.complexity == "complex"


def test_claude_code_system_and_reminder_ignored():
    request = InternalRequest(
        messages=[
            Message(role="system", content=CLAUDE_SYSTEM_CATALOG),
            Message(role="user", content=f"{SHORT_TASK}\n{CLAUDE_REMINDER}"),
        ],
        model="llama3.2:3b",
    )
    profile = build_prompt_profile(request)
    assert profile.category == "chat"
    assert profile.complexity == "trivial"
    assert profile.stripped_chars >= len(CLAUDE_SYSTEM_CATALOG)


def _tiered_router(tmp_path) -> Router:
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

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        context_window_escalation=False,
    )


@pytest.mark.asyncio
async def test_codex_harness_does_not_bump_router_tier(tmp_path):
    """Without strip, complexity=complex would start above L3; harness must not (#541)."""
    router = _tiered_router(tmp_path)
    # Avoid DEV-* policy matches on harness keywords; profile strip is what we pin.
    payload = "\n".join(
        [
            CHAT_TASK,
            CODEX_ENVIRONMENT,
            CODEX_PLUGINS,
            "<user_instructions>\n" + ("Keep replies short.\n" * 80) + "</user_instructions>",
            CODEX_ENVIRONMENTS_INSTRUCTIONS.replace("concurrency", "clarity"),
            "# agents.md instructions for /repo\n"
            + ("Follow AGENTS.md: keep modules tidy and documented.\n" * 60)
            + "</instructions>",
        ]
    )
    request = InternalRequest(
        messages=[Message(role="user", content=payload)],
        model="llama3.2:3b",
    )
    assert build_prompt_profile(request, harness_aware=False).complexity == "complex"
    response = await router.route(request)
    assert response.daari_meta.complexity == "trivial"
    assert response.daari_meta.task_type == "chat"
    assert response.daari_meta.tier == "L3"
