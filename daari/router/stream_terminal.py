"""Classify stream terminal finish_reason / done_reason (#2241).

LiteLLM 1.109.0 treats ``abort`` and streams that never emit a terminal
finish_reason as failures so retries and failover can run. daari mirrors that
on-box via the existing ``stream_incomplete`` path.
"""

from __future__ import annotations

# Successful OpenAI / Anthropic / Ollama terminal tokens (normalized lower).
_SUCCESS_FINISH_REASONS = frozenset(
    {
        "stop",
        "tool_calls",
        "length",
        "end_turn",
        "max_tokens",
        "tool_use",
        "stop_sequence",
        "pause_turn",
        "refusal",
    }
)
_ABORT_FINISH_REASONS = frozenset({"abort"})


class StreamTerminalError(RuntimeError):
    """Upstream stream aborted or ended without a terminal finish_reason."""

    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        self.reason = reason
        message = detail or reason
        super().__init__(message)


def is_abort_finish_reason(raw: str | None) -> bool:
    """True when upstream signaled an abort (not a clean stop)."""
    return (raw or "").strip().lower() in _ABORT_FINISH_REASONS


def is_success_finish_reason(raw: str | None) -> bool:
    """True for stop / tool_calls / length / Anthropic equivalents."""
    token = (raw or "").strip().lower()
    return bool(token) and token in _SUCCESS_FINISH_REASONS


def stream_ended_without_terminal(*, had_output: bool, saw_terminal: bool) -> bool:
    """Content or tool deltas were sent but no terminal done/finish_reason arrived."""
    return bool(had_output) and not saw_terminal


def normalize_stream_finish_reason(raw: str | None) -> str | None:
    """Map upstream terminal token to an OpenAI-shaped finish_reason, or None."""
    token = (raw or "").strip().lower()
    if not token:
        return None
    if token in _ABORT_FINISH_REASONS:
        return "abort"
    if token in {"length", "max_tokens"}:
        return "length"
    if token in {"tool_calls", "tool_use"}:
        return "tool_calls"
    if token in {"pause_turn", "refusal"}:
        return token
    if token in {"stop", "end_turn", "stop_sequence"}:
        return "stop"
    if token in _SUCCESS_FINISH_REASONS:
        return token
    return None
