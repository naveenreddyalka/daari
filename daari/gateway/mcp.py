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


def _error(code: str, message: str, *, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True


def _validate_input(schema: dict[str, Any], arguments: Any) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if schema.get("type") == "object":
        if not isinstance(arguments, dict):
            return [_error("MCP_ERR_INVALID_ARGUMENTS", "Arguments must be an object.")]
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in arguments:
                errors.append(_error("MCP_ERR_MISSING_ARGUMENT", f"Missing required argument: {key}", details={"path": key}))
        additional_allowed = schema.get("additionalProperties", True)
        for key, value in arguments.items():
            prop = properties.get(key)
            if prop is None and additional_allowed is False:
                errors.append(
                    _error(
                        "MCP_ERR_UNKNOWN_ARGUMENT",
                        f"Unexpected argument: {key}",
                        details={"path": key},
                    )
                )
                continue
            expected_type = (prop or {}).get("type")
            if expected_type and not _matches_type(value, expected_type):
                errors.append(
                    _error(
                        "MCP_ERR_INVALID_ARGUMENT_TYPE",
                        f"Invalid type for {key}: expected {expected_type}.",
                        details={"path": key, "expected": expected_type},
                    )
                )
    return errors


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
        {
            "name": "gitlab",
            "description": "Run GitLab self-hosted search",
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
            catalog_by_name = {item["name"]: item for item in _tool_catalog()}

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

                if normalized in {"sourcegraph", "ghe", "gitlab"}:
                    provider_id = {
                        "sourcegraph": "integration:sourcegraph",
                        "ghe": "integration:ghe",
                        "gitlab": "integration:gitlab",
                    }[normalized]
                    provider = ctx.providers.get(provider_id)
                    if provider is None:
                        return MCPQueryResponse(
                            ok=False,
                            tool=normalized,
                            result={"error": _error("MCP_ERR_PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}")},
                        )
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

                if normalized not in {"route"}:
                    return MCPQueryResponse(
                        ok=False,
                        tool=normalized,
                        result={"error": _error("MCP_ERR_UNKNOWN_TOOL", f"Unsupported tool: {normalized}")},
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
                    return MCPQueryResponse(
                        ok=False,
                        tool="tools/call",
                        result={"error": _error("MCP_ERR_MISSING_TOOL_NAME", "Missing tool name in tools/call.")},
                    ).model_dump()
                arguments = body.args.get("arguments") or {}
                if not isinstance(arguments, dict):
                    return MCPQueryResponse(
                        ok=False,
                        tool="tools/call",
                        result={"error": _error("MCP_ERR_INVALID_ARGUMENTS", "tools/call.arguments must be an object.")},
                    ).model_dump()
                normalized_name = name.strip().lower()
                schema = (catalog_by_name.get(normalized_name) or {}).get("input_schema")
                if schema is not None:
                    validation_errors = _validate_input(schema, arguments)
                    if validation_errors:
                        return MCPQueryResponse(
                            ok=False,
                            tool="tools/call",
                            result={
                                "name": normalized_name,
                                "error": _error(
                                    "MCP_ERR_SCHEMA_VALIDATION",
                                    "Tool input validation failed.",
                                    details=validation_errors,
                                ),
                            },
                        ).model_dump()
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
