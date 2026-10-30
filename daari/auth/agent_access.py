"""Opt-in agent-access grants for multi_agent virtual keys (#2004)."""

from __future__ import annotations

from typing import Any


def key_has_agent_grant(metadata: Any) -> bool:
    """True when key/team metadata declares an agent grant.

    A grant is ``agents_access: true``, presence of ``allowed_agents`` (even an
    empty list), or an ``agents`` block with ``allow`` / ``deny``.
    """
    if not isinstance(metadata, dict):
        return False
    if metadata.get("agents_access") is True:
        return True
    if "allowed_agents" in metadata:
        return True
    agents = metadata.get("agents")
    if isinstance(agents, dict) and ("allow" in agents or "deny" in agents):
        return True
    return False


def team_has_agent_grant(team: Any) -> bool:
    """True when a team metadata declares an agent grant (#2004)."""
    if team is None:
        return False
    return key_has_agent_grant(getattr(team, "metadata", None) or {})


def virtual_key_lacks_agent_grant(
    claims: Any,
    settings: Any,
    *,
    store: Any = None,
) -> bool:
    """True when opt-in fail-closed applies to this virtual key (#2004)."""
    virtual_keys = getattr(getattr(settings, "server", None), "virtual_keys", None)
    if not bool(getattr(virtual_keys, "agent_access_default_deny", False)):
        return False
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return False
    key = getattr(claims, "virtual_key", None)
    if key is None:
        return False
    if key_has_agent_grant(getattr(key, "metadata", None) or {}):
        return False
    team_id = getattr(claims, "selected_team_id", None) or getattr(key, "team_id", None)
    if store is not None and team_id:
        try:
            team = store.get_team(team_id)
        except Exception:
            team = None
        if team_has_agent_grant(team):
            return False
    return True
