"""Agent User-Agent / client_id sniffing for routing shortcuts (#421)."""

from __future__ import annotations

# Normalized client_ids produced by sniff_agent_client_id / accepted as agents.
AGENT_CLIENT_IDS = frozenset({"cursor", "claude-code", "codex"})


def sniff_agent_client_id(user_agent: str) -> str | None:
    """Map a User-Agent string to a known agent client_id, or None."""
    ua = (user_agent or "").lower()
    if "cursor" in ua:
        return "cursor"
    if "claude-code" in ua or "claude code" in ua:
        return "claude-code"
    if "codex" in ua:
        return "codex"
    return None


def is_classify_user_turn_agent(
    *, user_agent: str | None = None, client_id: str | None = None
) -> bool:
    """True when UA or client_id identifies Cursor / Claude Code / Codex."""
    if sniff_agent_client_id(user_agent or "") is not None:
        return True
    return (client_id or "").strip().lower() in AGENT_CLIENT_IDS
