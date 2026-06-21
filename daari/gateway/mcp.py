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


class MCPGatewayAdapter(GatewayAdapter):
    id = "mcp"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/mcp/query", response_model=None)
        async def mcp_query(body: MCPQueryRequest, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            tool = body.tool.strip().lower()

            if tool == "health":
                return MCPQueryResponse(
                    tool=tool,
                    result={"status": "ok", "adapter": "mcp"},
                ).model_dump()

            if tool == "stats":
                return MCPQueryResponse(
                    tool=tool,
                    result=ctx.metrics.snapshot(),
                ).model_dump()

            if tool in {"sourcegraph", "ghe"}:
                provider_id = "integration:sourcegraph" if tool == "sourcegraph" else "integration:ghe"
                provider = ctx.providers.get(provider_id)
                if provider is None:
                    return MCPQueryResponse(ok=False, tool=tool, result={"error": "provider_not_found"}).model_dump()
                internal = InternalRequest(
                    messages=[Message(role="user", content=body.input or "")],
                    model=body.model or ctx.settings.models.l3,
                )
                provider_result = await provider.execute(internal)
                return MCPQueryResponse(
                    ok=provider_result.daari_meta.warning is None,
                    tool=tool,
                    result={"content": provider_result.content},
                    daari_meta=provider_result.daari_meta.model_dump(),
                ).model_dump()

            route_input = body.input or body.args.get("prompt") or ""
            internal = InternalRequest(
                messages=[Message(role="user", content=route_input)],
                model=body.model or ctx.settings.models.l3,
            )
            routed = await ctx.router.route(internal)
            return MCPQueryResponse(
                tool=tool,
                result={"content": routed.content},
                daari_meta=routed.daari_meta.model_dump(),
            ).model_dump()

        return router
