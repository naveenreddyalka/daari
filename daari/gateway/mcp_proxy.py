"""POST /mcp/proxy — opt-in OpenAPI → MCP tools schema discovery (#1264)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from daari.gateway.request_log import log_gateway_event
from daari.security.egress_url import EgressUrlBlocked, validate_egress_url

_DISABLED = (
    "OpenAPI MCP proxy is disabled. Set integrations.mcp_openapi_proxy.enabled=true "
    "and configure at least one spec under integrations.mcp_openapi_proxy.specs."
)

_http: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _http
    if _http is None or getattr(_http, "is_closed", False):
        from daari.router.http_pool import build_async_client

        _http = build_async_client(httpx)
    return _http


async def aclose_http() -> None:
    global _http
    if _http is not None and not getattr(_http, "is_closed", True):
        await _http.aclose()
    _http = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def proxy_settings(settings: Any):
    from daari.config.settings import McpOpenApiProxySettings

    integrations = getattr(settings, "integrations", None)
    raw = getattr(integrations, "mcp_openapi_proxy", None) if integrations else None
    if raw is None:
        return McpOpenApiProxySettings()
    if isinstance(raw, McpOpenApiProxySettings):
        return raw
    return McpOpenApiProxySettings.model_validate(raw)


def _allow_private(settings: Any) -> bool:
    integrations = getattr(settings, "integrations", None)
    egress = getattr(integrations, "mcp_egress", None) if integrations else None
    return bool(getattr(egress, "allow_private_networks", False))


def _find_spec(settings: Any, spec_id: str):
    from daari.config.settings import McpOpenApiSpecSettings

    cfg = proxy_settings(settings)
    needle = (spec_id or "").strip()
    for item in cfg.specs:
        if item.id == needle:
            return item if isinstance(item, McpOpenApiSpecSettings) else McpOpenApiSpecSettings.model_validate(item)
    return None


def _parse_spec_document(raw: bytes, content_type: str = "") -> dict[str, Any]:
    text = raw.decode("utf-8")
    ctype = (content_type or "").lower()
    if "yaml" in ctype or "yml" in ctype or text.lstrip().startswith(("openapi:", "swagger:")):
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("OpenAPI document must be an object")
    return data


def _tool_name(path: str, method: str, operation: dict[str, Any]) -> str:
    op_id = str(operation.get("operationId") or "").strip()
    if op_id:
        return op_id
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{method}_{path}").strip("_")
    return cleaned or f"{method}_op"


def _param_schema(param: dict[str, Any]) -> dict[str, Any]:
    schema = param.get("schema")
    if isinstance(schema, dict):
        return dict(schema)
    return {"type": "string"}


def openapi_operations_to_tools(
    spec: dict[str, Any], *, operation_filter: list[str] | None = None
) -> list[dict[str, Any]]:
    """Convert OpenAPI 3 paths into MCP tools/list entries."""
    paths = spec.get("paths") if isinstance(spec.get("paths"), dict) else {}
    allow = {item.strip() for item in (operation_filter or []) if item and item.strip()}
    tools: list[dict[str, Any]] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method.startswith("x-") or method in {"parameters", "summary", "description"}:
                continue
            if not isinstance(operation, dict):
                continue
            name = _tool_name(str(path), str(method).lower(), operation)
            if allow and name not in allow and str(operation.get("operationId") or "") not in allow:
                continue
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param in operation.get("parameters") or []:
                if not isinstance(param, dict):
                    continue
                pname = str(param.get("name") or "").strip()
                if not pname:
                    continue
                properties[pname] = _param_schema(param)
                if param.get("required"):
                    required.append(pname)
            body = operation.get("requestBody")
            if isinstance(body, dict):
                content = body.get("content") if isinstance(body.get("content"), dict) else {}
                json_body = content.get("application/json") if isinstance(content, dict) else None
                schema = (
                    json_body.get("schema")
                    if isinstance(json_body, dict) and isinstance(json_body.get("schema"), dict)
                    else None
                )
                if schema is not None:
                    properties["body"] = schema
                    if body.get("required"):
                        required.append("body")
            input_schema: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                input_schema["required"] = required
            tools.append(
                {
                    "name": name,
                    "description": str(
                        operation.get("summary")
                        or operation.get("description")
                        or f"{method.upper()} {path}"
                    ),
                    "inputSchema": input_schema,
                    "_daari": {
                        "path": path,
                        "method": str(method).upper(),
                        "operationId": operation.get("operationId"),
                    },
                }
            )
    return tools


def _base_url_from_spec(spec: dict[str, Any], override: str) -> str:
    if override.strip():
        return override.strip().rstrip("/")
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict):
            url = str(first.get("url") or "").strip().rstrip("/")
            if url:
                return url
    return ""


async def _load_spec(
    settings: Any, entry: Any
) -> tuple[dict[str, Any], str]:
    url = (entry.openapi_url or "").strip()
    if not url:
        raise ValueError(f"spec {entry.id!r} has empty openapi_url")
    validate_egress_url(url, allow_private_networks=_allow_private(settings))
    client = _shared_client()
    response = await client.get(url, timeout=30.0)
    response.raise_for_status()
    document = _parse_spec_document(
        response.content, content_type=response.headers.get("content-type", "")
    )
    base = _base_url_from_spec(document, entry.base_url)
    if not base:
        raise ValueError(f"spec {entry.id!r} has no base_url and OpenAPI servers[] is empty")
    validate_egress_url(base, allow_private_networks=_allow_private(settings))
    return document, base


def _resolve_tool_policy(request: Request, ctx: Any) -> Any:
    from daari.gateway.mcp_policy import resolve_policy

    claims = getattr(request.state, "auth_claims", None)
    return resolve_policy(claims, ctx.settings)


def _meter_proxy_call(ctx: Any, request: Request, *, tool: str, arguments: dict[str, Any]) -> None:
    from daari.gateway.mcp import _meter_mcp_tool_call

    prompt = json.dumps(arguments, sort_keys=True, default=str)
    _meter_mcp_tool_call(
        ctx,
        request,
        tool=f"openapi:{tool}",
        call_input=prompt,
        model="mcp-openapi-proxy",
        provider_id="mcp:openapi_proxy",
    )


async def handle_proxy(request: Request, body: dict[str, Any]) -> JSONResponse:
    ctx = request.app.state.ctx
    settings = ctx.settings
    cfg = proxy_settings(settings)
    if not cfg.enabled or not cfg.specs:
        log_gateway_event("mcp_openapi_proxy_disabled", {})
        return _error(503, "service_unavailable", _DISABLED)

    action = str(body.get("action") or "tools/list").strip().lower()
    spec_id = str(body.get("spec_id") or "").strip()
    if not spec_id:
        return _error(400, "invalid_request_error", "spec_id is required")
    entry = _find_spec(settings, spec_id)
    if entry is None:
        return _error(400, "invalid_request_error", f"unknown spec_id {spec_id!r}")

    try:
        document, base_url = await _load_spec(settings, entry)
    except EgressUrlBlocked as exc:
        log_gateway_event("mcp_openapi_proxy_ssrf", {"spec_id": spec_id, "error": str(exc)})
        return _error(400, "egress_blocked", str(exc))
    except Exception as exc:
        log_gateway_event(
            "mcp_openapi_proxy_fetch_error", {"spec_id": spec_id, "error": str(exc)[:200]}
        )
        return _error(502, "bad_gateway", f"failed to load OpenAPI spec: {exc}")

    tools = openapi_operations_to_tools(document, operation_filter=list(entry.operations or []))
    # Strip internal routing metadata from list responses.
    public_tools = [
        {k: v for k, v in tool.items() if k != "_daari"} for tool in tools
    ]

    if action in {"tools/list", "list"}:
        log_gateway_event(
            "mcp_openapi_proxy_list", {"spec_id": spec_id, "tools": len(public_tools)}
        )
        return JSONResponse({"tools": public_tools})

    if action not in {"tools/call", "call"}:
        return _error(400, "invalid_request_error", "action must be tools/list or tools/call")

    name = str(body.get("name") or "").strip()
    if not name:
        return _error(400, "invalid_request_error", "name is required for tools/call")
    arguments = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}

    policy = _resolve_tool_policy(request, ctx)
    if policy is not None and hasattr(policy, "allows") and not policy.allows(name):
        log_gateway_event("mcp_openapi_proxy_denied", {"spec_id": spec_id, "tool": name})
        return _error(403, "tool_denied", f"tool {name!r} denied by mcp policy")

    match = next((tool for tool in tools if tool["name"] == name), None)
    if match is None:
        return _error(404, "not_found", f"tool {name!r} not in spec {spec_id!r}")

    meta = match.get("_daari") if isinstance(match.get("_daari"), dict) else {}
    method = str(meta.get("method") or "GET").upper()
    path_template = str(meta.get("path") or "/")
    path = path_template
    query: dict[str, Any] = {}
    json_body: Any = None
    for key, value in arguments.items():
        token = "{" + key + "}"
        if token in path:
            path = path.replace(token, str(value))
        elif key == "body":
            json_body = value
        else:
            query[key] = value
    url = f"{base_url.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    try:
        validate_egress_url(url, allow_private_networks=_allow_private(settings))
    except EgressUrlBlocked as exc:
        return _error(400, "egress_blocked", str(exc))

    client = _shared_client()
    try:
        upstream = await client.request(
            method, url, params=query or None, json=json_body, timeout=30.0
        )
    except Exception as exc:
        log_gateway_event(
            "mcp_openapi_proxy_call_error",
            {"spec_id": spec_id, "tool": name, "error": str(exc)[:200]},
        )
        return _error(503, "upstream_error", f"upstream request failed: {exc}")

    _meter_proxy_call(ctx, request, tool=name, arguments=arguments)
    try:
        payload = upstream.json()
    except Exception:
        payload = {"text": upstream.text[:4000]}
    log_gateway_event(
        "mcp_openapi_proxy_call",
        {"spec_id": spec_id, "tool": name, "status": upstream.status_code},
    )
    return JSONResponse(
        {
            "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
            "isError": upstream.status_code >= 400,
            "status_code": upstream.status_code,
        }
    )


def build_mcp_proxy_router() -> APIRouter:
    router = APIRouter()

    @router.post("/mcp/proxy", response_model=None)
    async def mcp_proxy(body: dict[str, Any], request: Request) -> JSONResponse:
        return await handle_proxy(request, body)

    return router
