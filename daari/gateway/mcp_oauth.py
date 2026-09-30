"""RFC 9728 OAuth protected-resource discovery for MCP ingress (#1262).

Opt-in via ``integrations.mcp_oauth.protected_resource``. When enabled, daari
serves ``/.well-known/oauth-protected-resource`` (and the ``/mcp``-scoped
variant) and shapes unauthenticated ``/mcp`` 401 responses with a
``WWW-Authenticate`` challenge that points at the metadata URL.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def mcp_oauth_enabled(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    oauth = getattr(integrations, "mcp_oauth", None)
    return bool(getattr(oauth, "protected_resource", False))


def _public_base(settings: Any, request: Request | None = None) -> str:
    oauth = getattr(getattr(settings, "integrations", None), "mcp_oauth", None)
    configured = str(getattr(oauth, "resource", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return str(request.base_url).rstrip("/")
    host = getattr(getattr(settings, "server", None), "host", None) or "127.0.0.1"
    port = getattr(getattr(settings, "server", None), "port", None) or 11435
    return f"http://{host}:{port}"


def protected_resource_metadata(
    settings: Any, *, request: Request | None = None, path_suffix: str = ""
) -> dict[str, Any]:
    """Build an RFC 9728 protected-resource metadata document."""
    oauth = getattr(getattr(settings, "integrations", None), "mcp_oauth", None)
    base = _public_base(settings, request)
    resource = f"{base}/mcp" if not path_suffix else f"{base}{path_suffix}"
    # When path_suffix is empty we still advertise the /mcp resource.
    if not path_suffix:
        resource = f"{base}/mcp"
    auth_servers = list(getattr(oauth, "authorization_servers", None) or [])
    scopes = list(getattr(oauth, "scopes_supported", None) or [])
    if not scopes:
        scopes = ["mcp"]
    doc: dict[str, Any] = {
        "resource": resource,
        "authorization_servers": auth_servers,
        "scopes_supported": scopes,
    }
    return doc


def metadata_url(settings: Any, *, request: Request | None = None) -> str:
    base = _public_base(settings, request)
    return urljoin(f"{base}/", ".well-known/oauth-protected-resource")


def www_authenticate_header(settings: Any, *, request: Request | None = None) -> str:
    url = metadata_url(settings, request=request)
    return f'Bearer realm="mcp", resource_metadata="{url}"'


def mcp_oauth_challenge_response(
    settings: Any, *, request: Request | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "type": "authentication_error",
                "message": "Invalid or missing daari API key.",
            }
        },
        headers={"WWW-Authenticate": www_authenticate_header(settings, request=request)},
    )


def build_mcp_oauth_router(settings: Any) -> APIRouter:
    router = APIRouter(tags=["mcp-oauth"])

    @router.get("/.well-known/oauth-protected-resource")
    async def oauth_protected_resource(request: Request) -> dict[str, Any]:
        return protected_resource_metadata(settings, request=request)

    @router.get("/.well-known/oauth-protected-resource/mcp")
    async def oauth_protected_resource_mcp(request: Request) -> dict[str, Any]:
        return protected_resource_metadata(settings, request=request, path_suffix="/mcp")

    return router
