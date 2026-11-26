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


def resolve_stream_finish_reason(upstream: str | None, *, tool_calls_sent: bool = False) -> str:
    """Terminal ``finish_reason`` for a relayed stream (#2331).

    Mirrors the upstream token when one arrived (``max_tokens`` → ``length``,
    ``tool_use`` → ``tool_calls``, ``pause_turn`` / ``refusal`` / ``content_filter``
    verbatim); only synthesizes ``stop`` / ``tool_calls`` when upstream said
    nothing or said a plain stop after tool calls were relayed.
    """
    token = (upstream or "").strip().lower()
    normalized = normalize_stream_finish_reason(token) or token or None
    if normalized is None or (normalized == "stop" and tool_calls_sent):
        return "tool_calls" if tool_calls_sent else "stop"
    return normalized
