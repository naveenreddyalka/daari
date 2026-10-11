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


def nested_agent_usages(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-agent usage rows from known multi_agent nested shapes (#1500).

    OpenAI's published Responses multi_agent schema aggregates subagent tokens
    into top-level ``usage``. Some payloads (or future schema) also expose a
    breakdown via ``agent_usages`` / ``usage_by_agent`` / ``usage.agents``.
    """
    if not isinstance(data, dict):
        return []
    candidates: list[Any] = []
    for key in ("agent_usages", "usage_by_agent"):
        raw = data.get(key)
        if isinstance(raw, list):
            candidates.extend(raw)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    for key in ("agent_usages", "usage_by_agent", "agents"):
        raw = usage.get(key)
        if isinstance(raw, list):
            candidates.extend(raw)
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            item_usage = item.get("usage")
            agent = item.get("agent") if isinstance(item.get("agent"), dict) else {}
            agent_id = (
                item.get("agent_id")
                or agent.get("agent_id")
                or agent.get("agent_name")
                or item.get("id")
            )
            if isinstance(item_usage, dict) and agent_id:
                row = dict(item_usage)
                row.setdefault("agent_id", agent_id)
                candidates.append(row)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        agent_id = (
            raw.get("agent_id")
            or raw.get("id")
            or raw.get("name")
            or raw.get("agent_name")
        )
        inp = _positive_int(
            raw.get("prompt_tokens") if raw.get("prompt_tokens") is not None else raw.get("input_tokens")
        )
        out = _positive_int(
            raw.get("completion_tokens")
            if raw.get("completion_tokens") is not None
            else raw.get("output_tokens")
        )
        cost_raw = raw.get("cost")
        cost = float(cost_raw) if isinstance(cost_raw, (int, float)) else None
        if agent_id is None and inp is None and out is None and cost is None:
            continue
        key = (str(agent_id or ""), inp, out, cost)
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, Any] = {}
        if agent_id is not None:
            row["agent_id"] = str(agent_id)
        if inp is not None:
            row["input_tokens"] = inp
        if out is not None:
            row["output_tokens"] = out
        if cost is not None:
            row["cost"] = cost
        rows.append(row)
    return rows


def openai_token_usage(
    data: dict[str, Any], prompt_chars: int, content: str
) -> tuple[int, int, bool]:
    """(input_tokens, output_tokens, estimated) from an OpenAI-shaped response.

    When nested multi_agent usages are present and top-level ``usage`` already
    covers them (OpenAI aggregated path), keep the top-level totals. When
    top-level under-counts relative to the nested sum, add parent + nested so
    the ledger is not silently short (#1500).
    """
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    reported_in = _positive_int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    reported_out = _positive_int(
        usage.get("completion_tokens") or usage.get("output_tokens")
    )
    agents = nested_agent_usages(data)
    nested_in = sum(int(a["input_tokens"]) for a in agents if "input_tokens" in a)
    nested_out = sum(int(a["output_tokens"]) for a in agents if "output_tokens" in a)
    has_nested_tokens = any("input_tokens" in a or "output_tokens" in a for a in agents)
    if has_nested_tokens:
        if (
            reported_in is not None
            and reported_out is not None
            and reported_in >= nested_in
            and reported_out >= nested_out
        ):
            return reported_in, reported_out, False
        meter_in = (reported_in or 0) + nested_in
        meter_out = (reported_out or 0) + nested_out
        if meter_in > 0 or meter_out > 0:
            return meter_in, meter_out, False
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
