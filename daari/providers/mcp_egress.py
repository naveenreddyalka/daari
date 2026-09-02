"""MCP egress client — daari calls external MCP servers as tools (issue #121).

Minimal JSON-RPC over HTTP (streamable HTTP / simple POST). Configured via
`integrations.mcp_servers` list. Triggered with `@mcp <server> <tool> ...`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_guardrails import McpGuardrails, first_rule
from daari.providers.integrations import HttpIntegrationProvider


@dataclass
class McpServerConfig:
    id: str
    url: str
    token: str = ""
    triggers: list[str] = field(default_factory=list)


class McpEgressProvider(HttpIntegrationProvider):
    def __init__(self, server: McpServerConfig, guardrails: McpGuardrails | None = None) -> None:
        super().__init__(
            id=f"mcp:{server.id}",
            base_url=server.url.rstrip("/"),
            token_env_var="",
        )
        self.server = server
        # Same rules as the ingress (#317): outbound arguments are checked before
        # they leave the machine, results before they reach the model.
        self.guardrails = guardrails or McpGuardrails(transport="egress")

    def _guardrail_blocked(self, request: InternalRequest, tool: str, rule: str) -> InternalResponse:
        return InternalResponse(
            content=f"{self.id} call to {tool} blocked by guardrail {rule}.",
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="guardrail_blocked",
            ),
        )

    async def health(self) -> bool:
        return True

    async def execute(self, request: InternalRequest) -> InternalResponse:
        text = next((m.content or "" for m in reversed(request.messages) if m.role == "user"), "")
        # "@mcp weather get_forecast Paris" or "@mcp:weather get_forecast Paris"
        match = re.match(
            rf"(?i)^@mcp(?::|{re.escape(self.server.id)}\s+| )(?:{re.escape(self.server.id)}\s+)?(\S+)(?:\s+(.*))?$",
            text.strip(),
        )
        if not match:
            # Fallback: first token after @mcp <id>
            parts = text.strip().split()
            tool = parts[2] if len(parts) >= 3 else "tools/list"
            arg_text = " ".join(parts[3:]) if len(parts) > 3 else ""
        else:
            tool = match.group(1)
            arg_text = (match.group(2) or "").strip()

        headers = {"Content-Type": "application/json"}
        if self.server.token:
            headers["Authorization"] = f"Bearer {self.server.token}"

        if tool in {"tools/list", "list"}:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            headers["Mcp-Method"] = "tools/list"
        else:
            # MCP 2026-07-28 routing headers: let upstream gateways apply
            # per-tool policy without parsing the JSON-RPC body (issue #277).
            headers["Mcp-Method"] = "tools/call"
            headers["Mcp-Name"] = tool
            arguments = {"query": arg_text} if arg_text else {}
            checked = self.guardrails.check_arguments(tool, arguments)
            if checked.blocked:
                return self._guardrail_blocked(request, tool, first_rule(checked))
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            if "error" in data:
                return self._failure(request, RuntimeError(str(data["error"])))
            result = data.get("result", data)
            text, _outcome = self.guardrails.check_result_text(tool, str(result)[:4000])
            return self._ok_response(request, self.id, text)
        except Exception as exc:  # noqa: BLE001
            return self._failure(request, exc)


def _entry_get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def build_mcp_providers(
    servers: list[Any], guardrails: McpGuardrails | None = None
) -> list[McpEgressProvider]:
    providers: list[McpEgressProvider] = []
    for entry in servers or []:
        if isinstance(entry, McpServerConfig):
            cfg = entry
        else:
            cfg = McpServerConfig(
                id=str(_entry_get(entry, "id") or ""),
                url=str(_entry_get(entry, "url") or ""),
                token=str(_entry_get(entry, "token") or ""),
                triggers=list(_entry_get(entry, "triggers") or []),
            )
        if not cfg.id or not cfg.url:
            continue
        if not cfg.triggers:
            cfg.triggers = [f"@mcp:{cfg.id}", f"@mcp {cfg.id}"]
        providers.append(McpEgressProvider(cfg, guardrails=guardrails))
    return providers
