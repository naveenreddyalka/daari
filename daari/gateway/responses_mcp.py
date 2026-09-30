"""Server-side MCP execution for Responses `type: mcp` tools (#1232).

Opt-in via `integrations.mcp_egress.server_side_responses`. Default off keeps
the #1135 honesty 400 for hosted tool types.
"""

from __future__ import annotations

import json
from typing import Any

from daari.gateway.internal import InternalRequest, InternalResponse, Message
from daari.gateway.request_log import log_gateway_event
from daari.providers.mcp_egress import McpEgressProvider

MAX_MCP_TOOL_ROUNDS = 5
_FN_SEP = "__"


def server_side_responses_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    egress = getattr(integrations, "mcp_egress", None)
    return bool(getattr(egress, "server_side_responses", False))


def configured_mcp_server_ids(settings: Any) -> frozenset[str]:
    integrations = getattr(settings, "integrations", None)
    servers = getattr(integrations, "mcp_servers", None) or []
    ids: set[str] = set()
    for entry in servers:
        if isinstance(entry, dict):
            raw = entry.get("id")
        else:
            raw = getattr(entry, "id", None)
        sid = str(raw or "").strip()
        if sid:
            ids.add(sid)
    return frozenset(ids)


def mcp_server_label(tool: dict[str, Any]) -> str:
    return str(tool.get("server_label") or tool.get("server_id") or "").strip()


def function_name_for(server_id: str, tool_name: str) -> str:
    return f"{server_id}{_FN_SEP}{tool_name}"


def parse_mcp_function_name(
    name: str, known_servers: frozenset[str]
) -> tuple[str, str] | None:
    for sid in sorted(known_servers, key=len, reverse=True):
        prefix = f"{sid}{_FN_SEP}"
        if name.startswith(prefix) and len(name) > len(prefix):
            return sid, name[len(prefix) :]
    return None


def validate_responses_mcp_tools(
    tools: list[dict[str, Any]] | None,
    *,
    enabled: bool,
    configured_ids: frozenset[str],
) -> str | None:
    """Return a 400 detail string when tools are invalid; None when OK."""
    if not tools:
        return None
    bad_hosted: list[str] = []
    seen_hosted: set[str] = set()
    unknown_mcp: list[str] = []
    for tool in tools:
        kind = str(tool.get("type") or "") or "(missing)"
        if kind == "function":
            continue
        if kind == "mcp":
            if not enabled:
                if kind not in seen_hosted:
                    seen_hosted.add(kind)
                    bad_hosted.append(kind)
                continue
            label = mcp_server_label(tool)
            if not label or label not in configured_ids:
                unknown_mcp.append(label or "(missing)")
            continue
        if kind not in seen_hosted:
            seen_hosted.add(kind)
            bad_hosted.append(kind)
    if bad_hosted:
        supported = ["function"] + (["mcp"] if enabled else [])
        return f"tools type not supported: {bad_hosted}. supported: {sorted(supported)}"
    if unknown_mcp:
        configured = sorted(configured_ids) or ["(none)"]
        return f"mcp server not configured: {unknown_mcp}. configured: {configured}"
    return None


def _allowed_tool_names(mcp_tool: dict[str, Any]) -> frozenset[str] | None:
    raw = mcp_tool.get("allowed_tools")
    if raw is None:
        return None
    if isinstance(raw, list):
        return frozenset(str(item) for item in raw if str(item))
    return None


def _mcp_tools_from_request(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [t for t in (tools or []) if isinstance(t, dict) and t.get("type") == "mcp"]


def _function_tools_from_request(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [t for t in (tools or []) if isinstance(t, dict) and t.get("type") == "function"]


def _provider_for(ctx: Any, server_id: str) -> McpEgressProvider | None:
    provider = ctx.providers.get(f"mcp:{server_id}")
    if isinstance(provider, McpEgressProvider):
        return provider
    return None


async def expand_mcp_tools_for_model(
    ctx: Any,
    request: InternalRequest,
    body_tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], frozenset[str]]:
    """List MCP catalogs and return OpenAI-shaped function tools + MCP server ids.

    Raises ``ValueError`` with a client-facing message on policy/SSRF/list failure.
    """
    mcp_tools = _mcp_tools_from_request(body_tools)
    function_tools = list(_function_tools_from_request(body_tools))
    if not mcp_tools:
        return function_tools, frozenset()

    known: set[str] = set()
    for mcp_tool in mcp_tools:
        server_id = mcp_server_label(mcp_tool)
        provider = _provider_for(ctx, server_id)
        if provider is None:
            raise ValueError(
                f"mcp server not configured: {[server_id or '(missing)']}. "
                f"configured: {sorted(configured_mcp_server_ids(ctx.settings)) or ['(none)']}"
            )
        catalog, err = await provider.list_tools_catalog(request)
        if err is not None:
            warning = getattr(err.daari_meta, "warning", None) or ""
            raise ValueError(err.content or f"mcp egress blocked ({warning})")
        assert catalog is not None
        allowed = _allowed_tool_names(mcp_tool)
        for entry in catalog:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            if allowed is not None and name not in allowed:
                continue
            known.add(server_id)
            schema = entry.get("inputSchema") or entry.get("parameters") or {
                "type": "object",
                "properties": {},
            }
            function_tools.append(
                {
                    "type": "function",
                    "name": function_name_for(server_id, name),
                    "description": str(entry.get("description") or f"MCP {server_id}/{name}"),
                    "parameters": schema if isinstance(schema, dict) else {"type": "object"},
                }
            )
    return function_tools, frozenset(known)


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"query": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {}


async def run_server_side_mcp_rounds(
    ctx: Any,
    request: InternalRequest,
    result: InternalResponse,
    *,
    mcp_server_ids: frozenset[str],
    route_fn: Any,
) -> InternalResponse:
    """Execute MCP tool_calls via egress and re-route until the model stops calling."""
    if not mcp_server_ids or not result.tool_calls:
        return result

    messages = list(request.messages)
    current = result
    for round_i in range(MAX_MCP_TOOL_ROUNDS):
        tool_calls = list(current.tool_calls or [])
        mcp_calls = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            name = str(function.get("name") or "")
            parsed = parse_mcp_function_name(name, mcp_server_ids)
            if parsed is None:
                continue
            mcp_calls.append((call, parsed[0], parsed[1], function.get("arguments")))
        if not mcp_calls:
            return current

        messages.append(
            Message(
                role="assistant",
                content=current.content or "",
                tool_calls=tool_calls,
            )
        )
        for call, server_id, tool_name, raw_args in mcp_calls:
            call_id = str(call.get("id") or f"call_{server_id}_{tool_name}")
            provider = _provider_for(ctx, server_id)
            if provider is None:
                tool_content = f"mcp server '{server_id}' is not available"
            else:
                egress_result = await provider.call_tool(
                    request,
                    tool=tool_name,
                    arguments=_parse_arguments(raw_args),
                )
                tool_content = egress_result.content or ""
            messages.append(
                Message(role="tool", content=tool_content, tool_call_id=call_id)
            )

        log_gateway_event(
            "responses_mcp_tool_round",
            {
                "round": round_i + 1,
                "mcp_calls": len(mcp_calls),
                "servers": sorted({sid for _, sid, _, _ in mcp_calls}),
            },
        )
        follow = request.model_copy(
            update={
                "messages": messages,
                "stream": False,
            }
        )
        current = await route_fn(follow)
        if not current.tool_calls:
            return current
    return current
