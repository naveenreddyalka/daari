"""MCP egress client — daari calls external MCP servers as tools (issue #121).

Minimal JSON-RPC over HTTP (streamable HTTP / simple POST). Configured via
`integrations.mcp_servers` list. Triggered with `@mcp <server> <tool> ...`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from daari.gateway.internal import InternalRequest, InternalResponse
from daari.providers.integrations import HttpIntegrationProvider


@dataclass
class McpServerConfig:
    id: str
    url: str
    token: str = ""
    triggers: list[str] = field(default_factory=list)


class McpEgressProvider(HttpIntegrationProvider):
    def __init__(self, server: McpServerConfig) -> None:
        super().__init__(
            id=f"mcp:{server.id}",
            base_url=server.url.rstrip("/"),
            token_env_var="",
        )
        self.server = server

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
        else:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool,
                    "arguments": {"query": arg_text} if arg_text else {},
                },
            }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            if "error" in data:
                return self._failure(request, RuntimeError(str(data["error"])))
            result = data.get("result", data)
            return self._ok_response(request, self.id, str(result)[:4000])
        except Exception as exc:  # noqa: BLE001
            return self._failure(request, exc)


def _entry_get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def build_mcp_providers(servers: list[Any]) -> list[McpEgressProvider]:
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
        providers.append(McpEgressProvider(cfg))
    return providers
