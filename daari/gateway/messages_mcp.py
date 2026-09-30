"""Server-side MCP for Anthropic Messages `mcp_servers` + `mcp_toolset` (#1261).

Opt-in via `integrations.mcp_egress.server_side_messages`. Default off fails
closed with an honesty 400. Resolves labels against configured
`integrations.mcp_servers` (same allowlist as Responses); client URLs are not
used for egress.
"""

from __future__ import annotations

from typing import Any

from daari.gateway.responses_mcp import (
    configured_mcp_server_ids,
    expand_mcp_tools_for_model,
    run_server_side_mcp_rounds,
)


def server_side_messages_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    egress = getattr(integrations, "mcp_egress", None)
    return bool(getattr(egress, "server_side_messages", False))


def _mcp_toolset_entries(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        t
        for t in (tools or [])
        if isinstance(t, dict) and str(t.get("type") or "") == "mcp_toolset"
    ]


def _mcp_server_names(mcp_servers: list[Any] | None) -> list[str]:
    names: list[str] = []
    for entry in mcp_servers or []:
        if isinstance(entry, dict):
            raw = entry.get("name") or entry.get("id")
        else:
            raw = getattr(entry, "name", None) or getattr(entry, "id", None)
        name = str(raw or "").strip()
        if name:
            names.append(name)
    return names


def _allowed_tools_from_toolset(toolset: dict[str, Any]) -> list[str] | None:
    """Map Anthropic toolset configs onto an allowlist when tools are gated."""
    configs = toolset.get("configs")
    default = toolset.get("default_config")
    default_enabled = True
    if isinstance(default, dict) and isinstance(default.get("enabled"), bool):
        default_enabled = default["enabled"]
    if not isinstance(configs, dict) or not configs:
        return None if default_enabled else []
    allowed: list[str] = []
    for name, cfg in configs.items():
        tool_name = str(name or "").strip()
        if not tool_name:
            continue
        enabled = default_enabled
        if isinstance(cfg, dict) and isinstance(cfg.get("enabled"), bool):
            enabled = cfg["enabled"]
        if enabled:
            allowed.append(tool_name)
    if default_enabled and not any(
        isinstance(cfg, dict) and cfg.get("enabled") is False for cfg in configs.values()
    ):
        # No explicit disables → leave unrestricted.
        return None
    return allowed


def messages_mcp_requested(
    *,
    mcp_servers: list[Any] | None,
    tools: list[dict[str, Any]] | None,
) -> bool:
    return bool(_mcp_server_names(mcp_servers) or _mcp_toolset_entries(tools))


def validate_messages_mcp(
    *,
    mcp_servers: list[Any] | None,
    tools: list[dict[str, Any]] | None,
    enabled: bool,
    configured_ids: frozenset[str],
) -> str | None:
    """Return a 400 detail when Messages MCP fields are invalid; None when OK."""
    toolsets = _mcp_toolset_entries(tools)
    server_names = _mcp_server_names(mcp_servers)
    if not toolsets and not server_names:
        return None
    if not enabled:
        return (
            "mcp_servers / mcp_toolset require "
            "integrations.mcp_egress.server_side_messages=true "
            "(Messages server-side MCP is opt-in)"
        )
    labels: list[str] = []
    for toolset in toolsets:
        label = str(toolset.get("mcp_server_name") or "").strip()
        labels.append(label or "(missing)")
    for name in server_names:
        if name not in labels:
            labels.append(name)
    unknown = [label for label in labels if not label or label == "(missing)" or label not in configured_ids]
    # Dedupe while preserving order.
    seen: set[str] = set()
    unknown_unique: list[str] = []
    for label in unknown:
        if label in seen:
            continue
        seen.add(label)
        unknown_unique.append(label)
    if unknown_unique:
        configured = sorted(configured_ids) or ["(none)"]
        return f"mcp server not configured: {unknown_unique}. configured: {configured}"
    return None


def mcp_tools_from_messages(
    *,
    mcp_servers: list[Any] | None,
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Messages MCP shape into Responses-style `{type: mcp, ...}` tools."""
    by_label: dict[str, dict[str, Any]] = {}
    for toolset in _mcp_toolset_entries(tools):
        label = str(toolset.get("mcp_server_name") or "").strip()
        if not label:
            continue
        entry: dict[str, Any] = {"type": "mcp", "server_label": label}
        allowed = _allowed_tools_from_toolset(toolset)
        if allowed is not None:
            entry["allowed_tools"] = allowed
        by_label[label] = entry
    for name in _mcp_server_names(mcp_servers):
        by_label.setdefault(name, {"type": "mcp", "server_label": name})
    return list(by_label.values())


def native_anthropic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return Anthropic tools that are not mcp_toolset entries."""
    out: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if str(tool.get("type") or "") == "mcp_toolset":
            continue
        out.append(tool)
    return out


__all__ = [
    "configured_mcp_server_ids",
    "expand_mcp_tools_for_model",
    "mcp_tools_from_messages",
    "messages_mcp_requested",
    "native_anthropic_tools",
    "run_server_side_mcp_rounds",
    "server_side_messages_enabled",
    "validate_messages_mcp",
]
