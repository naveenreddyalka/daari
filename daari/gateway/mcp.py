from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from daari.gateway.base import GatewayAdapter
from daari.gateway.internal import InternalRequest, Message
from daari.router.router import AppContext


class MCPQueryRequest(BaseModel):
    tool: str = Field(default="route")
    input: str | None = None
    model: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)


class MCPQueryResponse(BaseModel):
    ok: bool = True
    tool: str
    result: Any
    daari_meta: dict[str, Any] = Field(default_factory=dict)


def _tool_catalog() -> list[dict[str, Any]]:
    basic_input_schema = {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "additionalProperties": True,
    }
    basic_output_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "daari_meta": {"type": "object"},
        },
    }
    return [
        {
            "name": "health",
            "description": "MCP adapter health check",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
        },
        {
            "name": "stats",
            "description": "Current daari tier metrics snapshot",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "output_schema": {"type": "object"},
        },
        {
            "name": "route",
            "description": "Route prompt through daari pipeline",
            "input_schema": basic_input_schema,
            "output_schema": basic_output_schema,
        },
        {
            "name": "sourcegraph",
            "description": "Run Sourcegraph search",
            "input_schema": basic_input_schema,
            "output_schema": basic_output_schema,
        },
        {
            "name": "ghe",
            "description": "Run GitHub Enterprise search",
            "input_schema": basic_input_schema,
            "output_schema": basic_output_schema,
        },
    ]


class MCPGatewayAdapter(GatewayAdapter):
    id = "mcp"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/mcp/query", response_model=None)
        async def mcp_query(body: MCPQueryRequest, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            tool = body.tool.strip().lower()

            async def run_tool(name: str, call_input: str | None, call_args: dict[str, Any]) -> MCPQueryResponse:
                normalized = name.strip().lower()
                if normalized == "health":
                    return MCPQueryResponse(
                        tool=normalized,
                        result={"status": "ok", "adapter": "mcp"},
                    )

                if normalized == "stats":
                    return MCPQueryResponse(
                        tool=normalized,
                        result=ctx.metrics.snapshot(),
                    )

                if normalized in {"sourcegraph", "ghe"}:
                    provider_id = "integration:sourcegraph" if normalized == "sourcegraph" else "integration:ghe"
                    provider = ctx.providers.get(provider_id)
                    if provider is None:
                        return MCPQueryResponse(ok=False, tool=normalized, result={"error": "provider_not_found"})
                    internal = InternalRequest(
                        messages=[Message(role="user", content=call_input or "")],
                        model=body.model or ctx.settings.models.l3,
                    )
                    provider_result = await provider.execute(internal)
                    return MCPQueryResponse(
                        ok=provider_result.daari_meta.warning is None,
                        tool=normalized,
                        result={"content": provider_result.content},
                        daari_meta=provider_result.daari_meta.model_dump(),
                    )

                route_input = call_input or call_args.get("prompt") or ""
                internal = InternalRequest(
                    messages=[Message(role="user", content=route_input)],
                    model=body.model or ctx.settings.models.l3,
                )
                routed = await ctx.router.route(internal)
                return MCPQueryResponse(
                    tool=normalized,
                    result={"content": routed.content},
                    daari_meta=routed.daari_meta.model_dump(),
                )

            if tool in {"tools/list", "list_tools"}:
                return MCPQueryResponse(tool="tools/list", result={"tools": _tool_catalog()}).model_dump()

            if tool in {"tools/call", "call_tool"}:
                name = str(body.args.get("name") or body.args.get("tool") or body.input or "").strip()
                if not name:
                    return MCPQueryResponse(ok=False, tool="tools/call", result={"error": "missing_tool_name"}).model_dump()
                arguments = body.args.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                tool_response = await run_tool(name, arguments.get("input"), arguments)
                return MCPQueryResponse(
                    ok=tool_response.ok,
                    tool="tools/call",
                    result={
                        "name": tool_response.tool,
                        "result": tool_response.result,
                        "daari_meta": tool_response.daari_meta,
                    },
                    daari_meta=tool_response.daari_meta,
                ).model_dump()

            response = await run_tool(tool, body.input, body.args)
            return response.model_dump()

        return router
