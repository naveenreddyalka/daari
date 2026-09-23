from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from daari import __version__
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.gateway.base import GatewayAdapter
from daari.gateway.client_errors import request_deadline_response, safe_detail
from daari.gateway.disconnect import ClientDisconnected, await_unless_disconnected
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.mcp_guardrails import (
    GUARDRAIL_BLOCKED,
    LEGACY_ERROR_CODE,
    McpGuardrails,
    first_rule,
)
from daari.gateway.mcp_policy import TOOL_DENIED, McpToolPolicy, audit_tool_call, resolve_policy
from daari.gateway.mcp_tasks import (
    client_opted_into_tasks,
    create_task_result,
    initialize_capabilities,
    spawn_tool_task,
    tool_should_become_task,
)
from daari.router.deadline import (
    RequestDeadlineExceeded,
    bind_request_deadline,
    deadline_active,
    guard_upstream,
    parse_deadline_ms,
    resolve_deadline_seconds,
)
from daari.router.router import AppContext

JSONRPC_VERSION = "2.0"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

DEFAULT_PROTOCOL_VERSION = "2025-03-26"
SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
    "2026-07-28",
}

LEGACY_HEADERS = {
    "Deprecation": "true",
    "Link": '</mcp>; rel="successor-version"',
}


def _record_mcp_tool(ctx: AppContext, tool: str, outcome: str) -> None:
    """Bump MCP Prometheus counters when exposition is enabled (#603)."""
    if not getattr(ctx.settings.observability, "prometheus", True):
        return
    metrics = getattr(ctx.router, "metrics", None)
    if metrics is None or not hasattr(metrics, "record_mcp_tool_call"):
        return
    metrics.record_mcp_tool_call(tool=tool.strip().lower() or "unknown", outcome=outcome)


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
                errors.append(
                    _error(
                        "MCP_ERR_MISSING_ARGUMENT",
                        f"Missing required argument: {key}",
                        details={"path": key},
                    )
                )
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


def _basic_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"input": {"type": "string"}},
        "additionalProperties": True,
    }


def _empty_input_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _tool_name_for_provider(provider_id: str) -> str | None:
    if provider_id.startswith("integration:"):
        return provider_id.split(":", 1)[1].replace(":", "_")
    if provider_id.startswith("mcp:"):
        return "mcp_" + provider_id.split(":", 1)[1].replace(":", "_")
    return None


def _core_catalog() -> list[dict[str, Any]]:
    basic_output = {
        "type": "object",
        "properties": {"content": {"type": "string"}, "daari_meta": {"type": "object"}},
    }
    return [
        {
            "name": "health",
            "description": "MCP adapter health check",
            "input_schema": _empty_input_schema(),
            "output_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
        },
        {
            "name": "stats",
            "description": "Current daari tier metrics snapshot",
            "input_schema": _empty_input_schema(),
            "output_schema": {"type": "object"},
        },
        {
            "name": "route",
            "description": "Route a prompt through daari's local-first pipeline",
            "input_schema": _basic_input_schema(),
            "output_schema": basic_output,
        },
    ]


def _provider_catalog(ctx: AppContext) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    seen: set[str] = set()
    for provider_id in ctx.providers.list_ids():
        name = _tool_name_for_provider(provider_id)
        if not name or name in seen:
            continue
        seen.add(name)
        tools.append(
            {
                "name": name,
                "description": f"Call configured provider {provider_id}",
                "input_schema": _basic_input_schema(),
                "output_schema": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}, "daari_meta": {"type": "object"}},
                },
                "provider_id": provider_id,
            }
        )
    return tools


def _tool_catalog(ctx: AppContext, policy: McpToolPolicy | None = None) -> list[dict[str, Any]]:
    catalog = [*_core_catalog(), *_provider_catalog(ctx)]
    if policy is None:
        return catalog
    return [item for item in catalog if policy.allows(item["name"])]


def _mcp_list_tools(ctx: AppContext, policy: McpToolPolicy | None = None) -> list[dict[str, Any]]:
    listed: list[dict[str, Any]] = []
    for item in _tool_catalog(ctx, policy):
        if item["name"] == "health":
            continue
        listed.append(
            {
                "name": item["name"],
                "description": item["description"],
                "inputSchema": item["input_schema"],
            }
        )
    return listed


def _list_cache_scope(policy: McpToolPolicy | None) -> str:
    """Kong-style: public only when no ACL allow/deny filters the catalog (#979)."""
    if policy is None:
        return "public"
    if policy.allow or policy.deny:
        return "private"
    return "public"


def _tools_list_payload(
    ctx: AppContext,
    policy: McpToolPolicy | None = None,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    """tools/list body with MCP 2026-07-28 _meta cache hints (#979)."""
    tools = _tool_catalog(ctx, policy) if legacy else _mcp_list_tools(ctx, policy)
    cache = getattr(getattr(ctx.settings, "integrations", None), "mcp_list_cache", None)
    ttl_ms = int(getattr(cache, "ttl_ms", 60_000) or 0)
    return {
        "tools": tools,
        "_meta": {
            "ttlMs": ttl_ms,
            "cacheScope": _list_cache_scope(policy),
        },
    }


def _legacy(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(payload, headers=LEGACY_HEADERS)


def _jsonrpc_result(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": rpc_id, "result": result}


def _jsonrpc_error(rpc_id: Any, code: int, message: str, *, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": rpc_id, "error": error}


def _wants_sse(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept and "application/json" not in accept


def _rpc_response(request: Request, payload: dict[str, Any], *, status_code: int = 200) -> Response:
    if _wants_sse(request) and "error" not in payload:
        body = f"event: message\ndata: {json.dumps(payload)}\n\n"
        return Response(content=body, media_type="text/event-stream", status_code=status_code)
    return JSONResponse(payload, status_code=status_code)


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class _Governance:
    """Per-request policy, guardrails and audit sink for the MCP ingress (#277, #317)."""

    def __init__(self, request: Request, ctx: AppContext, *, transport: str) -> None:
        self.claims = getattr(request.state, "auth_claims", None)
        self.policy = resolve_policy(self.claims, ctx.settings)
        self._audit = audit_log_from_settings(ctx.settings)
        self.guardrails = McpGuardrails.from_settings(
            ctx.settings, audit=self._audit, claims=self.claims, transport=transport
        )
        # MCP 2026-07-28 lets infrastructure route/limit on these without
        # parsing JSON-RPC; when a client sends them they govern too.
        self.header_method = (request.headers.get("mcp-method") or "").strip()
        self.header_name = (request.headers.get("mcp-name") or "").strip()

    def denied_tool(self, name: str) -> str | None:
        """Return the first tool name the caller may not call, else None."""
        candidates = [self.header_name] if self.header_method in ("", "tools/call") else []
        candidates.append(name)
        for candidate in candidates:
            if candidate and not self.policy.allows(candidate):
                return candidate.strip().lower()
        return None

    def audit(self, *, tool: str, decision: str, transport: str) -> None:
        audit_tool_call(
            self._audit,
            self.claims,
            tool=tool.strip().lower(),
            decision=decision,
            method="tools/call",
            transport=transport,
        )

    def check(self, name: str, *, transport: str) -> str | None:
        """Audit the call and return the denied tool name, if any."""
        denied = self.denied_tool(name)
        if denied is not None:
            self.audit(tool=denied, decision="deny", transport=transport)
            return denied
        self.audit(tool=name, decision="allow", transport=transport)
        return None

    def tripped_rule(self, name: str, arguments: Any) -> str | None:
        """Run input guardrails over the arguments; return the blocking rule name."""
        result = self.guardrails.check_arguments(name.strip().lower(), arguments)
        return first_rule(result) if result.blocked else None

    def guard_tool_result(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.guardrails.check_tool_result(name.strip().lower(), payload)[0]

    def guard_legacy(self, tool_response: MCPQueryResponse) -> MCPQueryResponse:
        if not tool_response.ok:
            return tool_response
        result, outcome = self.guardrails.check_legacy_result(tool_response.tool, tool_response.result)
        if not outcome.hits:
            return tool_response
        return tool_response.model_copy(update={"result": result, "ok": not outcome.blocked})


def _legacy_guardrail_blocked(name: str, rule: str) -> JSONResponse:
    payload = MCPQueryResponse(
        ok=False,
        tool="tools/call",
        result={
            "name": name,
            "error": _error(
                LEGACY_ERROR_CODE,
                f"Tool call blocked by guardrail {rule}: {name}",
                details={"tool": name, "rule": rule, "direction": "input"},
            ),
        },
    ).model_dump()
    return JSONResponse(payload, status_code=403, headers=LEGACY_HEADERS)


def _legacy_denied(name: str) -> JSONResponse:
    payload = MCPQueryResponse(
        ok=False,
        tool="tools/call",
        result={
            "name": name,
            "error": _error("MCP_ERR_TOOL_DENIED", f"Tool denied by policy: {name}", details={"tool": name}),
        },
    ).model_dump()
    return JSONResponse(payload, status_code=403, headers=LEGACY_HEADERS)


def _negotiate_protocol(params: Any) -> str:
    requested = ""
    if isinstance(params, dict):
        requested = str(params.get("protocolVersion") or "")
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return DEFAULT_PROTOCOL_VERSION


class ModelNotAllowed(Exception):
    """Raised when a virtual-key allowlist rejects the MCP model (#839)."""

    def __init__(self, response: JSONResponse) -> None:
        self.response = response
        super().__init__("model_not_allowed")


def _governed_meta(request: Request | None, ctx: AppContext, deadline_ms: int | None) -> RequestMeta:
    """Build RequestMeta with virtual-key claims (tier_cap, cache_scope, key/team)."""
    meta = RequestMeta(deadline_ms=deadline_ms)
    if request is None:
        return meta
    from daari.server.auth import apply_auth_claims_to_meta

    apply_auth_claims_to_meta(
        meta,
        getattr(request.state, "auth_claims", None),
        model_groups=getattr(ctx.settings, "model_groups", None),
    )
    return meta


def _resolve_tool_model(
    ctx: AppContext,
    model: str | None,
    call_args: dict[str, Any],
) -> str:
    arg_model = call_args.get("model")
    if isinstance(arg_model, str) and arg_model.strip():
        return arg_model.strip()
    if model and str(model).strip():
        return str(model).strip()
    return ctx.settings.models.l3


def _enforce_mcp_model(request: Request | None, ctx: AppContext, meta: RequestMeta, model: str) -> None:
    if request is None:
        return
    from daari.gateway.model_access import reject_disallowed_model

    denied = reject_disallowed_model(request, model, ctx.settings, meta)
    if denied is not None:
        raise ModelNotAllowed(denied)


async def _run_tool(
    ctx: AppContext,
    name: str,
    call_input: str | None,
    call_args: dict[str, Any],
    *,
    model: str | None,
    request: Request | None = None,
) -> MCPQueryResponse:
    normalized = name.strip().lower()
    if normalized == "health":
        return MCPQueryResponse(tool=normalized, result={"status": "ok", "adapter": "mcp"})

    if normalized == "stats":
        return MCPQueryResponse(tool=normalized, result=ctx.metrics.snapshot())

    catalog_by_name = {item["name"]: item for item in _tool_catalog(ctx)}
    provider_id = (catalog_by_name.get(normalized) or {}).get("provider_id")
    resolved_model = _resolve_tool_model(ctx, model, call_args)
    deadline_ms = None
    if request is not None:
        deadline_ms = parse_deadline_ms(request.headers.get("x-daari-deadline-ms"))
    meta = _governed_meta(request, ctx, deadline_ms)
    if provider_id or normalized == "route":
        _enforce_mcp_model(request, ctx, meta, resolved_model)

    async def _await_work(coro: Any) -> Any:
        if request is None:
            return await coro
        return await await_unless_disconnected(
            request,
            coro,
            metrics=ctx.metrics,
            phase="mcp",
            model=resolved_model,
        )

    if provider_id:
        provider = ctx.providers.get(provider_id)
        if provider is None:
            return MCPQueryResponse(
                ok=False,
                tool=normalized,
                result={"error": _error("MCP_ERR_PROVIDER_NOT_FOUND", f"Provider not found: {provider_id}")},
            )
        internal = InternalRequest(
            messages=[Message(role="user", content=call_input or "")],
            model=resolved_model,
            meta=meta,
        )
        provider_result = await _await_work(provider.execute(internal))
        return MCPQueryResponse(
            ok=provider_result.daari_meta.warning is None,
            tool=normalized,
            result={"content": provider_result.content},
            daari_meta=provider_result.daari_meta.model_dump(),
        )

    if normalized != "route":
        return MCPQueryResponse(
            ok=False,
            tool=normalized,
            result={"error": _error("MCP_ERR_UNKNOWN_TOOL", f"Unsupported tool: {normalized}")},
        )

    route_input = call_input or call_args.get("prompt") or ""
    internal = InternalRequest(
        messages=[Message(role="user", content=route_input)],
        model=resolved_model,
        meta=meta,
    )
    routed = await _await_work(ctx.router.route(internal))
    return MCPQueryResponse(
        tool=normalized,
        result={"content": routed.content},
        daari_meta=routed.daari_meta.model_dump(),
    )


def _deadline_seconds_for_request(request: Request, ctx: AppContext) -> float | None:
    header_ms = parse_deadline_ms(request.headers.get("x-daari-deadline-ms"))
    return resolve_deadline_seconds(
        header_ms,
        getattr(ctx.settings.upstream, "request_deadline_seconds", None),
    )


async def _run_tool_with_deadline(
    ctx: AppContext,
    name: str,
    call_input: str | None,
    call_args: dict[str, Any],
    *,
    model: str | None,
    request: Request,
) -> MCPQueryResponse:
    """Bind wall-clock budget for tools/call, then run the tool (#827)."""
    seconds = _deadline_seconds_for_request(request, ctx)
    if seconds is not None and not deadline_active():
        with bind_request_deadline(seconds, metrics=ctx.metrics):
            guard_upstream("mcp")
            return await _run_tool(
                ctx, name, call_input, call_args, model=model, request=request
            )
    return await _run_tool(ctx, name, call_input, call_args, model=model, request=request)


def _client_disconnected_response() -> JSONResponse:
    return JSONResponse(
        status_code=499,
        content={
            "error": {
                "type": "client_disconnected",
                "message": "client disconnected.",
            }
        },
    )


def _tool_call_result_payload(name: str, tool_response: MCPQueryResponse) -> dict[str, Any]:
    if not tool_response.ok:
        err = (
            tool_response.result.get("error")
            if isinstance(tool_response.result, dict)
            else tool_response.result
        )
        return _text_result(json.dumps(err), is_error=True)
    if name.strip().lower() == "stats":
        text = json.dumps(tool_response.result)
    elif isinstance(tool_response.result, dict) and "content" in tool_response.result:
        text = str(tool_response.result.get("content") or "")
    else:
        text = json.dumps(tool_response.result)
    return _text_result(text)


async def _handle_tasks_get(
    ctx: AppContext, request: Request, rpc_id: Any, params: dict[str, Any]
) -> Response:
    store = getattr(ctx, "mcp_task_store", None)
    task_id = str(params.get("taskId") or params.get("task_id") or "").strip()
    if store is None or not task_id:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, "Missing taskId"),
        )
    task = store.get(task_id)
    if task is None:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, f"Unknown taskId: {task_id}"),
        )
    return _rpc_response(request, _jsonrpc_result(rpc_id, store.as_public(task)))


async def _handle_tasks_update(
    ctx: AppContext, request: Request, rpc_id: Any, params: dict[str, Any]
) -> Response:
    """Report current state (input-required flow minimum for #289)."""
    store = getattr(ctx, "mcp_task_store", None)
    task_id = str(params.get("taskId") or params.get("task_id") or "").strip()
    if store is None or not task_id:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, "Missing taskId"),
        )
    task = store.get(task_id)
    if task is None:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, f"Unknown taskId: {task_id}"),
        )
    # Input-required acknowledgement: echo status; no mutation required for MVP.
    return _rpc_response(request, _jsonrpc_result(rpc_id, store.as_public(task)))


async def _handle_tasks_cancel(
    ctx: AppContext, request: Request, rpc_id: Any, params: dict[str, Any]
) -> Response:
    store = getattr(ctx, "mcp_task_store", None)
    task_id = str(params.get("taskId") or params.get("task_id") or "").strip()
    if store is None or not task_id:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, "Missing taskId"),
        )
    task = store.request_cancel(task_id)
    if task is None:
        return _rpc_response(
            request,
            _jsonrpc_error(rpc_id, INVALID_PARAMS, f"Unknown taskId: {task_id}"),
        )
    return _rpc_response(request, _jsonrpc_result(rpc_id, store.as_public(task)))


class MCPGatewayAdapter(GatewayAdapter):
    id = "mcp"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/mcp/query", response_model=None)
        async def mcp_query(body: MCPQueryRequest, request: Request) -> JSONResponse:
            ctx: AppContext = request.app.state.ctx
            tool = body.tool.strip().lower()
            governance = _Governance(request, ctx, transport="rest")
            catalog_by_name = {item["name"]: item for item in _tool_catalog(ctx)}

            if tool in {"tools/list", "list_tools"}:
                return _legacy(
                    MCPQueryResponse(
                        tool="tools/list",
                        result=_tools_list_payload(ctx, governance.policy, legacy=True),
                    ).model_dump()
                )

            if tool in {"tools/call", "call_tool"}:
                name = str(body.args.get("name") or body.args.get("tool") or body.input or "").strip()
                if not name:
                    return _legacy(
                        MCPQueryResponse(
                            ok=False,
                            tool="tools/call",
                            result={"error": _error("MCP_ERR_MISSING_TOOL_NAME", "Missing tool name in tools/call.")},
                        ).model_dump()
                    )
                arguments = body.args.get("arguments") or {}
                if not isinstance(arguments, dict):
                    return _legacy(
                        MCPQueryResponse(
                            ok=False,
                            tool="tools/call",
                            result={
                                "error": _error(
                                    "MCP_ERR_INVALID_ARGUMENTS",
                                    "tools/call.arguments must be an object.",
                                )
                            },
                        ).model_dump()
                    )
                normalized_name = name.strip().lower()
                denied = governance.check(normalized_name, transport="rest")
                if denied is not None:
                    _record_mcp_tool(ctx, denied, "deny")
                    return _legacy_denied(denied)
                schema = (catalog_by_name.get(normalized_name) or {}).get("input_schema")
                if schema is not None:
                    validation_errors = _validate_input(schema, arguments)
                    if validation_errors:
                        return _legacy(
                            MCPQueryResponse(
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
                        )
                rule = governance.tripped_rule(normalized_name, arguments)
                if rule is not None:
                    _record_mcp_tool(ctx, normalized_name, "guardrail")
                    return _legacy_guardrail_blocked(normalized_name, rule)
                try:
                    tool_response = governance.guard_legacy(
                        await _run_tool_with_deadline(
                            ctx,
                            name,
                            arguments.get("input"),
                            arguments,
                            model=body.model,
                            request=request,
                        )
                    )
                except ModelNotAllowed as exc:
                    return exc.response
                except ClientDisconnected:
                    return _client_disconnected_response()
                except RequestDeadlineExceeded as exc:
                    return request_deadline_response(exc)
                _record_mcp_tool(
                    ctx, tool_response.tool or normalized_name, "ok" if tool_response.ok else "error"
                )
                return _legacy(
                    MCPQueryResponse(
                        ok=tool_response.ok,
                        tool="tools/call",
                        result={
                            "name": tool_response.tool,
                            "result": tool_response.result,
                            "daari_meta": tool_response.daari_meta,
                        },
                        daari_meta=tool_response.daari_meta,
                    ).model_dump()
                )

            denied = governance.check(tool, transport="rest")
            if denied is not None:
                _record_mcp_tool(ctx, denied, "deny")
                return _legacy_denied(denied)
            rule = governance.tripped_rule(tool, {"input": body.input, **body.args})
            if rule is not None:
                _record_mcp_tool(ctx, tool, "guardrail")
                return _legacy_guardrail_blocked(tool, rule)
            try:
                response = governance.guard_legacy(
                    await _run_tool_with_deadline(
                        ctx, tool, body.input, body.args, model=body.model, request=request
                    )
                )
            except ModelNotAllowed as exc:
                return exc.response
            except ClientDisconnected:
                return _client_disconnected_response()
            except RequestDeadlineExceeded as exc:
                return request_deadline_response(exc)
            _record_mcp_tool(ctx, response.tool or tool, "ok" if response.ok else "error")
            return _legacy(response.model_dump())

        @router.post("/mcp")
        async def mcp_jsonrpc(request: Request) -> Response:
            raw = await request.body()
            try:
                message = json.loads(raw.decode("utf-8") or "null")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return JSONResponse(
                    _jsonrpc_error(None, PARSE_ERROR, "Parse error"),
                    status_code=400,
                )
            if not isinstance(message, dict):
                return JSONResponse(
                    _jsonrpc_error(None, INVALID_REQUEST, "Invalid Request"),
                    status_code=400,
                )
            if message.get("jsonrpc") != JSONRPC_VERSION or not message.get("method"):
                return JSONResponse(
                    _jsonrpc_error(message.get("id"), INVALID_REQUEST, "Invalid Request"),
                    status_code=400,
                )

            method = str(message["method"])
            rpc_id = message.get("id")
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            if "id" not in message:
                return Response(status_code=202)

            ctx: AppContext = request.app.state.ctx
            governance = _Governance(request, ctx, transport="jsonrpc")
            try:
                if method == "initialize":
                    protocol = _negotiate_protocol(params)
                    return _rpc_response(
                        request,
                        _jsonrpc_result(
                            rpc_id,
                            {
                                "protocolVersion": protocol,
                                "capabilities": initialize_capabilities(protocol),
                                "serverInfo": {"name": "daari", "version": __version__},
                            },
                        ),
                    )
                if method == "ping":
                    return _rpc_response(request, _jsonrpc_result(rpc_id, {}))
                if method == "tools/list":
                    return _rpc_response(
                        request,
                        _jsonrpc_result(
                            rpc_id, _tools_list_payload(ctx, governance.policy)
                        ),
                    )
                if method == "tasks/get":
                    return await _handle_tasks_get(ctx, request, rpc_id, params)
                if method == "tasks/update":
                    return await _handle_tasks_update(ctx, request, rpc_id, params)
                if method == "tasks/cancel":
                    return await _handle_tasks_cancel(ctx, request, rpc_id, params)
                if method == "tools/call":
                    name = str(params.get("name") or "").strip()
                    if not name:
                        return _rpc_response(
                            request,
                            _jsonrpc_error(rpc_id, INVALID_PARAMS, "Missing tool name"),
                        )
                    arguments = params.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        return _rpc_response(
                            request,
                            _jsonrpc_error(rpc_id, INVALID_PARAMS, "arguments must be an object"),
                        )
                    denied = governance.check(name, transport="jsonrpc")
                    if denied is not None:
                        _record_mcp_tool(ctx, denied, "deny")
                        return _rpc_response(
                            request,
                            _jsonrpc_error(
                                rpc_id,
                                TOOL_DENIED,
                                f"Tool denied by policy: {denied}",
                                data={"tool": denied},
                            ),
                        )
                    catalog_by_name = {item["name"]: item for item in _tool_catalog(ctx)}
                    schema = (catalog_by_name.get(name.strip().lower()) or {}).get("input_schema")
                    if schema is not None:
                        validation_errors = _validate_input(schema, arguments)
                        if validation_errors:
                            return _rpc_response(
                                request,
                                _jsonrpc_result(
                                    rpc_id,
                                    _text_result(json.dumps(validation_errors), is_error=True),
                                ),
                            )
                    normalized_name = name.strip().lower()
                    rule = governance.tripped_rule(normalized_name, arguments)
                    if rule is not None:
                        _record_mcp_tool(ctx, normalized_name, "guardrail")
                        return _rpc_response(
                            request,
                            _jsonrpc_error(
                                rpc_id,
                                GUARDRAIL_BLOCKED,
                                f"Tool call blocked by guardrail {rule}: {normalized_name}",
                                data={"tool": normalized_name, "rule": rule, "direction": "input"},
                            ),
                        )
                    task_cfg = ctx.settings.integrations.mcp_tasks
                    store = getattr(ctx, "mcp_task_store", None)
                    if (
                        task_cfg.enabled
                        and store is not None
                        and client_opted_into_tasks(params)
                        and tool_should_become_task(
                            name,
                            long_running_tools=list(task_cfg.long_running_tools),
                            threshold_ms=int(task_cfg.threshold_ms),
                        )
                    ):
                        task = store.create(tool=name.strip().lower())

                        async def _runner() -> dict[str, Any]:
                            tool_response = await _run_tool(
                                ctx,
                                name,
                                arguments.get("input"),
                                arguments,
                                model=None,
                                request=request,
                            )
                            _record_mcp_tool(
                                ctx,
                                name,
                                "ok" if tool_response.ok else "error",
                            )
                            return governance.guard_tool_result(
                                name, _tool_call_result_payload(name, tool_response)
                            )

                        await spawn_tool_task(store, task, _runner)
                        return _rpc_response(
                            request,
                            _jsonrpc_result(rpc_id, create_task_result(task)),
                        )
                    tool_response = await _run_tool_with_deadline(
                        ctx, name, arguments.get("input"), arguments, model=None, request=request
                    )
                    _record_mcp_tool(
                        ctx, name, "ok" if tool_response.ok else "error"
                    )
                    payload = governance.guard_tool_result(
                        name, _tool_call_result_payload(name, tool_response)
                    )
                    return _rpc_response(request, _jsonrpc_result(rpc_id, payload))
                return _rpc_response(
                    request,
                    _jsonrpc_error(rpc_id, METHOD_NOT_FOUND, f"Method not found: {method}"),
                )
            except ModelNotAllowed as exc:
                return exc.response
            except ClientDisconnected:
                return _client_disconnected_response()
            except RequestDeadlineExceeded as exc:
                return request_deadline_response(exc)
            except Exception as exc:  # noqa: BLE001 — JSON-RPC must not leak a 500
                return _rpc_response(
                    request,
                    _jsonrpc_error(rpc_id, INTERNAL_ERROR, safe_detail(exc)[:200]),
                )

        return router
