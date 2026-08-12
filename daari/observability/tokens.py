"""Token counting helpers (#156).

Every count in daari used to be `len(chars) // 4`. Providers actually report
usage — Ollama as `prompt_eval_count`/`eval_count`, OpenAI-shaped APIs as a
`usage` object — so read it when present and fall back to the estimate only
when it is genuinely absent, flagging that it happened.
"""

from __future__ import annotations

from typing import Any

CHARS_PER_TOKEN = 4


def estimate_tokens(chars: int) -> int:
    return max(0, chars) // CHARS_PER_TOKEN


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(value)


def ollama_token_usage(
    data: dict[str, Any], request: Any, content: str
) -> tuple[int, int, bool]:
    """(input_tokens, output_tokens, estimated) from an Ollama /api/chat body."""
    reported_in = _positive_int(data.get("prompt_eval_count"))
    reported_out = _positive_int(data.get("eval_count"))
    if reported_in is not None and reported_out is not None:
        return reported_in, reported_out, False
    prompt_chars = sum(len(message.content or "") for message in request.messages)
    return (
        reported_in if reported_in is not None else estimate_tokens(prompt_chars),
        reported_out if reported_out is not None else estimate_tokens(len(content)),
        True,
    )


def openai_token_usage(
    data: dict[str, Any], prompt_chars: int, content: str
) -> tuple[int, int, bool]:
    """(input_tokens, output_tokens, estimated) from an OpenAI-shaped response."""
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    reported_in = _positive_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    reported_out = _positive_int(
        usage.get("completion_tokens") or usage.get("output_tokens")
    )
    if reported_in is not None and reported_out is not None:
        return reported_in, reported_out, False
    return (
        reported_in if reported_in is not None else estimate_tokens(prompt_chars),
        reported_out if reported_out is not None else estimate_tokens(len(content)),
        True,
    )


def response_token_usage(response: Any, prompt_chars: int) -> tuple[int, int, bool]:
    """Token counts for an InternalResponse, estimating only what is missing."""
    meta = response.daari_meta
    reported_in = _positive_int(getattr(meta, "input_tokens", None))
    reported_out = _positive_int(getattr(meta, "output_tokens", None))
    estimated = bool(getattr(meta, "usage_estimated", True))
    if reported_in is None:
        reported_in = estimate_tokens(prompt_chars)
        estimated = True
    if reported_out is None:
        reported_out = estimate_tokens(len(response.content or ""))
        estimated = True
    return reported_in, reported_out, estimated
