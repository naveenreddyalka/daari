from __future__ import annotations

from fastapi import APIRouter, HTTPException

from daari.gateway.base import GatewayAdapter


class MCPGatewayAdapter(GatewayAdapter):
    id = "mcp"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/mcp/query", response_model=None)
        async def mcp_query() -> dict[str, str]:
            raise HTTPException(status_code=501, detail="MCP gateway is planned for Phase C1.")

        return router
