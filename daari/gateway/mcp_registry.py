"""Opt-in MCP Registry advertisement at GET /v1/mcp/registry.json (#1277).

Advertisement-only: lists the built-in `/mcp` ingress and configured
`integrations.mcp_servers` streamable HTTP URLs. Actual `/mcp` access still
enforces API-key / allowlist checks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def mcp_registry_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    registry = getattr(integrations, "mcp_registry", None)
    return bool(getattr(registry, "enabled", False))


def _public_base(settings: Any, request: Request | None = None) -> str:
    registry = getattr(getattr(settings, "integrations", None), "mcp_registry", None)
    configured = str(getattr(registry, "public_base_url", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    host = getattr(getattr(settings, "server", None), "host", None) or "127.0.0.1"
    port = getattr(getattr(settings, "server", None), "port", None) or 11435
    return f"http://{host}:{port}"


def build_registry_document(
    settings: Any, *, request: Request | None = None
) -> dict[str, Any]:
    """Build an MCP registry.json document (LiteLLM-compatible servers list)."""
    base = _public_base(settings, request)
    servers: list[dict[str, str]] = [
        {
            "name": "daari",
            "description": "daari first-party MCP ingress (tools/resources/prompts)",
            "url": f"{base}/mcp",
        }
    ]
    integrations = getattr(settings, "integrations", None)
    for entry in list(getattr(integrations, "mcp_servers", None) or []):
        sid = str(getattr(entry, "id", "") or "").strip()
        url = str(getattr(entry, "url", "") or "").strip()
        if not sid or not url:
            continue
        servers.append(
            {
                "name": sid,
                "description": f"Configured MCP egress server {sid!r}",
                "url": url,
            }
        )
    return {"servers": servers}


def build_mcp_registry_router(settings: Any) -> APIRouter:
    router = APIRouter(tags=["mcp-registry"])

    @router.get("/v1/mcp/registry.json")
    async def mcp_registry(request: Request) -> Any:
        if not mcp_registry_enabled(settings):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        return build_registry_document(settings, request=request)

    return router
