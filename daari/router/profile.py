"""Prompt profiling: category, complexity, token estimate.

Pure local heuristics (<1ms, no model calls) per docs/prd/intelligence.md.
The interface is deliberately small so a learned classifier can replace
`categorize` later without touching call sites.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from daari.gateway.internal import InternalRequest

CATEGORIES = frozenset(
    {"code_gen", "code_explain", "test", "git", "lint", "fetch", "doc_qa", "chat"}
)

_TEST_TOKENS = ("pytest", "unit test", "unittest", "write a test", "tests for")
_GIT_TOKENS = ("git ", "commit", "branch", "merge", "rebase")
_LINT_TOKENS = ("lint", "eslint", "ruff", "flake8")
_FETCH_TOKENS = ("http://", "https://", "fetch ", "api ")
_CODE_TOKENS = (
    "function",
    "class ",
    "code",
    "bug",
    "refactor",
    "implement",
    "decorator",
    "module",
    "script",
    "regex",
    "dataclass",
    "concurrency",
)
_EXPLAIN_MARKERS = (
    "explain",
    "what does",
    "why does",
    "how does",
    "describe",
    "walk me through",
    "understand",
)
_GEN_VERBS = ("write", "create", "implement", "add ", "build", "generate", "refactor", "fix")
_QUESTION_STARTERS = ("what", "why", "how", "when", "where", "who", "which", "is ", "are ", "can ")


class PromptProfile(BaseModel):
    category: str
    complexity: str  # trivial | standard | complex
    prompt_tokens_est: int


def categorize(text: str) -> str:
    normalized = text.lower().strip()
    if any(token in normalized for token in _TEST_TOKENS):
        return "test"
    if any(token in normalized for token in _GIT_TOKENS):
        return "git"
    if any(token in normalized for token in _LINT_TOKENS):
        return "lint"
    if any(token in normalized for token in _FETCH_TOKENS):
        return "fetch"
    has_code_signal = "```" in normalized or any(token in normalized for token in _CODE_TOKENS)
    if has_code_signal and any(marker in normalized for marker in _EXPLAIN_MARKERS):
        return "code_explain"
    if has_code_signal and any(normalized.startswith(verb) or f" {verb}" in normalized for verb in _GEN_VERBS):
        return "code_gen"
    if has_code_signal:
        return "code_explain" if "?" in normalized else "code_gen"
    if normalized.startswith(_QUESTION_STARTERS) or normalized.endswith("?"):
        return "doc_qa"
    return "chat"


def build_prompt_profile(request: InternalRequest) -> PromptProfile:
    last_user = ""
    for message in reversed(request.messages):
        if message.role == "user" and message.content:
            last_user = message.content
            break
    total_chars = sum(len(message.content or "") for message in request.messages)
    words = len(re.findall(r"\S+", last_user))
    fences = last_user.count("```") // 2
    tokens_est = max(1, total_chars // 4)

    if words > 250 or fences >= 2 or tokens_est > 2000:
        complexity = "complex"
    elif words <= 8 and fences == 0:
        complexity = "trivial"
    else:
        complexity = "standard"

    return PromptProfile(
        category=categorize(last_user),
        complexity=complexity,
        prompt_tokens_est=tokens_est,
    )
