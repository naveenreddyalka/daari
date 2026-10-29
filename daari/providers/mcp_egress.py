"""MCP egress client — daari calls external MCP servers as tools (issue #121).

Minimal JSON-RPC over HTTP (streamable HTTP / simple POST). Configured via
`integrations.mcp_servers` list. Triggered with `@mcp <server> <tool> ...`.

Outbound calls reuse frontier-style `RetryPolicy` + per-server `CircuitBreaker`
and emit an OTel client span (`mcp.tools/call` / `mcp.tools/list`) (#1203).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_guardrails import McpGuardrails, first_rule
from daari.providers.integrations import HttpIntegrationProvider
from daari.router.breaker_redis import share_key_for
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.retry import RetryPolicy, run_upstream


@dataclass
class McpServerConfig:
    id: str
    url: str
    token: str = ""
    triggers: list[str] = field(default_factory=list)
    auth_type: str = ""
    token_exchange_endpoint: str = ""
    client_id: str = ""
    client_secret: str = ""
    audience: str = ""
    scopes: list[str] = field(default_factory=list)
    subject_token_type: str = "access_token"
    rpm: int = 0
    tpm: int = 0


WARNING_SERVER_RATE_LIMITED = "mcp_server_rate_limited"


class McpServerRateLimited(Exception):
    """Egress per-server rpm/tpm ceiling tripped (#1620)."""

    def __init__(self, decision: Any, server_id: str) -> None:
        self.decision = decision
        self.server_id = server_id
        super().__init__(f"mcp_server:{server_id} rate limited")


def record_mcp_server_rate_limit_reject(
    exc: McpServerRateLimited,
    *,
    metrics: Any = None,
    settings: Any = None,
) -> None:
    """Bump ``daari_rejects_total`` + ``rate_limit.exceeded`` audit (#1654)."""
    if metrics is not None and hasattr(metrics, "record_reject"):
        try:
            metrics.record_reject("rate_limit")
        except Exception:  # noqa: BLE001 — metrics must never break a request
            pass
    if settings is None:
        return
    try:
        from daari.enterprise.audit import record_rate_limit_exceeded
        from daari.enterprise.postgres_audit import audit_log_from_settings

        decision = exc.decision
        bucket = getattr(decision, "bucket", None) or f"mcp_server:{exc.server_id}"
        record_rate_limit_exceeded(
            audit_log_from_settings(settings),
            scope=getattr(decision, "scope", None) or None,
            bucket=bucket,
            remaining=int(getattr(decision, "remaining", 0) or 0),
            limit=int(getattr(decision, "limit", 0) or 0),
        )
    except Exception:  # noqa: BLE001 — audit must never break a request
        pass


# A misbehaving upstream that always returns nextCursor must not hang listing.
LIST_PAGE_CAP = 20
LIST_TIMEOUT_SECONDS = 15.0


class McpEgressProvider(HttpIntegrationProvider):
    def __init__(
        self,
        server: McpServerConfig,
        guardrails: McpGuardrails | None = None,
        *,
        tool_search: Any = None,
        embedder: Any = None,
        tool_policy: Any = None,
        server_policy: Any = None,
        allow_private_networks: bool = False,
        retry: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        metrics: Any = None,
        rate_limiter: Any = None,
        settings: Any = None,
    ) -> None:
        super().__init__(
            id=f"mcp:{server.id}",
            base_url=server.url.rstrip("/"),
            token_env_var="",
        )
        self.server = server
        # Same rules as the ingress (#317): outbound arguments are checked before
        # they leave the machine, results before they reach the model.
        self.guardrails = guardrails or McpGuardrails(transport="egress")
        self.list_page_cap = LIST_PAGE_CAP
        self.list_timeout_seconds = LIST_TIMEOUT_SECONDS
        from daari.gateway.mcp_tool_search import ToolEmbeddingCache, settings_from_block

        self.tool_search = settings_from_block(tool_search)
        self.embedder = embedder
        self.tool_policy = tool_policy
        self.server_policy = server_policy
        self.allow_private_networks = allow_private_networks
        self.retry = retry or RetryPolicy()
        self.breaker = breaker or CircuitBreaker(
            share_key=share_key_for("mcp", server.id),
        )
        self.metrics = metrics
        self.rate_limiter = rate_limiter
        self.settings = settings
        self._tool_embed_cache = ToolEmbeddingCache()
        self._http: httpx.AsyncClient | None = None
        from daari.providers.mcp_token_exchange import TokenExchangeCache

        self._token_exchange_cache = TokenExchangeCache()

    def _ensure_egress_url_allowed(self) -> None:
        from daari.security.egress_url import validate_egress_url

        validate_egress_url(
            self.base_url, allow_private_networks=self.allow_private_networks
        )

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            from daari.security.egress_tls import resolve_httpx_verify

            self._http = httpx.AsyncClient(
                timeout=30.0,
                verify=resolve_httpx_verify(settings=self.settings),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    def _guardrail_blocked(
        self,
        request: InternalRequest,
        tool: str,
        rule: str,
        *,
        denial: str | None = None,
    ) -> InternalResponse:
        content = denial or f"{self.id} call to {tool} blocked by guardrail {rule}."
        return InternalResponse(
            content=content,
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="guardrail_blocked",
            ),
        )

    def _circuit_open(self, request: InternalRequest, tool: str) -> InternalResponse:
        circuit = self.breaker.state
        if self.metrics is not None and hasattr(self.metrics, "record_mcp_egress"):
            try:
                self.metrics.record_mcp_egress(
                    server=self.server.id, outcome="circuit_open", circuit=circuit
                )
            except Exception:  # noqa: BLE001 — metrics must never break a request
                pass
        return InternalResponse(
            content=f"{self.id} circuit open; skipping call to {tool}.",
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning="mcp_circuit_open",
            ),
        )

    def _record_egress(self, outcome: str) -> None:
        if self.metrics is None or not hasattr(self.metrics, "record_mcp_egress"):
            return
        try:
            self.metrics.record_mcp_egress(
                server=self.server.id,
                outcome=outcome,
                circuit=self.breaker.state,
            )
        except Exception:  # noqa: BLE001
            pass

    async def health(self) -> bool:
        return True

    async def _post_json(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        async def once() -> httpx.Response:
            client = self._client()
            response = await client.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            return response

        return await run_upstream(
            once,
            upstream=self.id,
            policy=self.retry,
            metrics=self.metrics,
        )

    def _policy_denied_response(self, request: InternalRequest) -> InternalResponse | None:
        if self.server_policy is not None and not self.server_policy.allows(self.server.id):
            return InternalResponse(
                content=f"MCP server '{self.server.id}' denied by policy.",
                model=request.model,
                daari_meta=DaariMeta(
                    tier=self.tier,
                    executor="integration",
                    provider_id=self.id,
                    task_type="tool",
                    warning="mcp_server_denied",
                ),
            )
        return None

    def _auth_failure(
        self, request: InternalRequest, warning: str, message: str
    ) -> InternalResponse:
        return InternalResponse(
            content=message,
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning=warning,
            ),
        )

    async def _resolve_authorization(
        self, request: InternalRequest
    ) -> tuple[str | None, InternalResponse | None]:
        """Return Bearer token for upstream, or a fail-closed InternalResponse."""
        from daari.gateway.request_log import log_gateway_event
        from daari.providers.mcp_token_exchange import (
            AUTH_TYPE_TOKEN_EXCHANGE,
            WARNING_MISSING_SUBJECT,
            TokenExchangeError,
            exchange_access_token,
        )

        auth_type = (self.server.auth_type or "").strip().lower()
        if auth_type == AUTH_TYPE_TOKEN_EXCHANGE:
            subject = getattr(request.meta, "authorization_bearer", None) or ""
            subject = str(subject).strip()
            if not subject:
                log_gateway_event(
                    "mcp_token_exchange_missing_subject",
                    {"server_id": self.server.id},
                )
                return None, self._auth_failure(
                    request,
                    WARNING_MISSING_SUBJECT,
                    f"{self.id} token exchange requires an inbound Authorization bearer.",
                )
            try:
                token = await exchange_access_token(
                    server_id=self.server.id,
                    endpoint=self.server.token_exchange_endpoint,
                    client_id=self.server.client_id,
                    client_secret=self.server.client_secret,
                    subject_token=subject,
                    subject_token_type=self.server.subject_token_type,
                    audience=self.server.audience,
                    scopes=list(self.server.scopes or []),
                    allow_private_networks=self.allow_private_networks,
                    cache=self._token_exchange_cache,
                    client=self._client(),
                )
            except TokenExchangeError as exc:
                return None, self._auth_failure(request, exc.warning, f"{self.id}: {exc}")
            return token, None
        if self.server.token:
            return self.server.token, None
        return None, None

    async def _request_headers(
        self, request: InternalRequest
    ) -> tuple[dict[str, str] | None, InternalResponse | None]:
        headers = {"Content-Type": "application/json"}
        token, err = await self._resolve_authorization(request)
        if err is not None:
            return None, err
        if token:
            headers["Authorization"] = f"Bearer {token}"
        from daari.observability.otel import inject_trace_headers

        return (
            inject_trace_headers(
                headers, request_id=getattr(request.meta, "request_id", None)
            ),
            None,
        )

    def _enforce_server_rate_limit(self, *, tokens: int = 1) -> None:
        """Raise when per-server rpm/tpm is exhausted (#1620)."""
        rpm = int(getattr(self.server, "rpm", 0) or 0)
        tpm = int(getattr(self.server, "tpm", 0) or 0)
        if rpm <= 0 and tpm <= 0:
            return
        limiter = self.rate_limiter
        if limiter is None or not hasattr(limiter, "check_mcp_server"):
            return
        decision = limiter.check_mcp_server(
            server_id=self.server.id,
            tokens=max(1, int(tokens)),
            rpm=rpm,
            tpm=tpm,
        )
        if not decision.allowed:
            raise McpServerRateLimited(decision, self.server.id)

    async def _prepare_egress(
        self, request: InternalRequest, *, tool: str, tokens: int = 1
    ) -> tuple[dict[str, str] | None, InternalResponse | None]:
        denied = self._policy_denied_response(request)
        if denied is not None:
            return None, denied
        self._enforce_server_rate_limit(tokens=tokens)
        headers, auth_err = await self._request_headers(request)
        if auth_err is not None:
            return None, auth_err
        assert headers is not None
        try:
            self._ensure_egress_url_allowed()
        except Exception as exc:  # noqa: BLE001 — surface as tool failure
            return None, self._failure(request, exc)
        if not self.breaker.allow():
            return None, self._circuit_open(request, tool)
        return headers, None

    def _rate_limited_response(self, request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=f"{self.id} rate limited (mcp_server:{self.server.id}).",
            model=request.model,
            daari_meta=DaariMeta(
                tier=self.tier,
                executor="integration",
                provider_id=self.id,
                task_type="tool",
                warning=WARNING_SERVER_RATE_LIMITED,
            ),
        )

    async def list_tools_catalog(
        self, request: InternalRequest
    ) -> tuple[list[dict[str, Any]] | None, InternalResponse | None]:
        """Structured tools/list for Responses server-side MCP (#1232)."""
        try:
            headers, err = await self._prepare_egress(request, tool="tools/list")
        except McpServerRateLimited as exc:
            record_mcp_server_rate_limit_reject(
                exc, metrics=self.metrics, settings=self.settings
            )
            return None, self._rate_limited_response(request)
        if err is not None:
            return None, err
        assert headers is not None
        from daari.observability.otel import mcp_client_span

        with mcp_client_span("mcp.tools/list", server_id=self.server.id, tool_name=None):
            try:
                tools = await self._list_tools({**headers, "Mcp-Method": "tools/list"})
            except Exception as exc:  # noqa: BLE001
                self.breaker.record_failure()
                self._record_egress("error")
                return None, self._failure(request, exc)
            self.breaker.record_success()
            self._record_egress("ok")
            from daari.gateway.mcp_tool_search import extract_list_query, maybe_rank_tools

            query = extract_list_query(arg_text="", messages=request.messages)
            tools = await maybe_rank_tools(
                tools,
                query=query,
                settings=self.tool_search,
                policy=self.tool_policy,
                embedder=self.embedder,
                server_id=self.server.id,
                cache=self._tool_embed_cache,
            )
            return tools, None

    async def call_tool(
        self,
        request: InternalRequest,
        *,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> InternalResponse:
        """Structured tools/call for Responses server-side MCP (#1232)."""
        import json as _json

        args = dict(arguments or {})
        token_est = max(1, len(_json.dumps(args, default=str)) // 4)
        headers, err = await self._prepare_egress(
            request, tool=tool, tokens=token_est
        )
        if err is not None:
            return err
        assert headers is not None
        from daari.observability.otel import mcp_client_span

        with mcp_client_span(
            "mcp.tools/call", server_id=self.server.id, tool_name=tool
        ):
            return await self._call_tool_under_span(
                request,
                tool=tool,
                arguments=args,
                headers=headers,
            )

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

        try:
            headers, err = await self._prepare_egress(request, tool=tool)
        except McpServerRateLimited as exc:
            record_mcp_server_rate_limit_reject(
                exc, metrics=self.metrics, settings=self.settings
            )
            return self._rate_limited_response(request)
        if err is not None:
            return err
        assert headers is not None

        from daari.observability.otel import mcp_client_span

        span_name = "mcp.tools/list" if tool in {"tools/list", "list"} else "mcp.tools/call"
        span_tool = None if tool in {"tools/list", "list"} else tool
        with mcp_client_span(
            span_name, server_id=self.server.id, tool_name=span_tool
        ):
            return await self._execute_under_span(
                request, tool=tool, arg_text=arg_text, headers=headers
            )

    async def _call_tool_under_span(
        self,
        request: InternalRequest,
        *,
        tool: str,
        arguments: dict[str, Any],
        headers: dict[str, str],
    ) -> InternalResponse:
        # MCP 2026-07-28 routing headers: let upstream gateways apply
        # per-tool policy without parsing the JSON-RPC body (issue #277).
        headers = {**headers, "Mcp-Method": "tools/call", "Mcp-Name": tool}
        checked = self.guardrails.check_arguments(tool, arguments)
        if checked.blocked:
            rule = first_rule(checked)
            denial = self.guardrails.denial_text(
                checked,
                legacy=f"{self.id} call to {tool} blocked by guardrail {rule}.",
            )
            return self._guardrail_blocked(request, tool, rule, denial=denial)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        try:
            response = await self._post_json(payload, headers)
            data = response.json()
            if "error" in data:
                self.breaker.record_failure()
                self._record_egress("error")
                return self._failure(request, RuntimeError(str(data["error"])))
            result = data.get("result", data)
            text, _outcome = self.guardrails.check_result_text(tool, str(result)[:4000])
            self.breaker.record_success()
            self._record_egress("ok")
            return self._ok_response(request, self.id, text)
        except Exception as exc:  # noqa: BLE001
            self.breaker.record_failure()
            self._record_egress("error")
            return self._failure(request, exc)

    async def _execute_under_span(
        self,
        request: InternalRequest,
        *,
        tool: str,
        arg_text: str,
        headers: dict[str, str],
    ) -> InternalResponse:
        if tool in {"tools/list", "list"}:
            headers = {**headers, "Mcp-Method": "tools/list"}
            try:
                tools = await self._list_tools(headers)
            except Exception as exc:  # noqa: BLE001
                self.breaker.record_failure()
                self._record_egress("error")
                return self._failure(request, exc)
            self.breaker.record_success()
            self._record_egress("ok")
            from daari.gateway.mcp_tool_search import extract_list_query, maybe_rank_tools

            query = extract_list_query(arg_text=arg_text, messages=request.messages)
            tools = await maybe_rank_tools(
                tools,
                query=query,
                settings=self.tool_search,
                policy=self.tool_policy,
                embedder=self.embedder,
                server_id=self.server.id,
                cache=self._tool_embed_cache,
            )
            catalog = {"tools": tools}
            text, _outcome = self.guardrails.check_result_text(tool, str(catalog)[:4000])
            return self._ok_response(request, self.id, text)

        arguments = {"query": arg_text} if arg_text else {}
        return await self._call_tool_under_span(
            request, tool=tool, arguments=arguments, headers=headers
        )

    async def _list_tools(self, headers: dict[str, str]) -> list[dict[str, Any]]:
        """Follow tools/list nextCursor until absent, capped so a bad upstream stops."""
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()
        cursor: str | None = None
        started = time.monotonic()
        for page in range(self.list_page_cap):
            if page and time.monotonic() - started >= self.list_timeout_seconds:
                break
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            payload = {
                "jsonrpc": "2.0",
                "id": page + 1,
                "method": "tools/list",
                "params": params,
            }
            response = await self._post_json(payload, headers)
            data = response.json()
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            result = data.get("result", data)
            if not isinstance(result, dict):
                break
            for tool in result.get("tools") or []:
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name") or "")
                if name and name in seen:
                    continue
                if name:
                    seen.add(name)
                tools.append(tool)
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
        return tools


def _entry_get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def wire_mcp_egress_rate_limiters(providers: Any, rate_limiter: Any) -> None:
    """Attach the gateway rate limiter to MCP egress providers (#1620)."""
    if rate_limiter is None or providers is None:
        return
    list_ids = getattr(providers, "list_ids", None)
    get = getattr(providers, "get", None)
    if not callable(list_ids) or not callable(get):
        return
    for provider_id in list_ids():
        provider = get(provider_id)
        if isinstance(provider, McpEgressProvider):
            provider.rate_limiter = rate_limiter


def build_mcp_providers(
    servers: list[Any],
    guardrails: McpGuardrails | None = None,
    *,
    tool_search: Any = None,
    embedder: Any = None,
    tool_policy: Any = None,
    server_policy: Any = None,
    allow_private_networks: bool = False,
    retry: RetryPolicy | None = None,
    failure_threshold: int = 3,
    cooldown_seconds: float = 30.0,
    metrics: Any = None,
    rate_limiter: Any = None,
    settings: Any = None,
) -> list[McpEgressProvider]:
    providers: list[McpEgressProvider] = []
    policy = retry or RetryPolicy()
    for entry in servers or []:
        if isinstance(entry, McpServerConfig):
            cfg = entry
        else:
            cfg = McpServerConfig(
                id=str(_entry_get(entry, "id") or ""),
                url=str(_entry_get(entry, "url") or ""),
                token=str(_entry_get(entry, "token") or ""),
                triggers=list(_entry_get(entry, "triggers") or []),
                auth_type=str(_entry_get(entry, "auth_type") or ""),
                token_exchange_endpoint=str(
                    _entry_get(entry, "token_exchange_endpoint") or ""
                ),
                client_id=str(_entry_get(entry, "client_id") or ""),
                client_secret=str(_entry_get(entry, "client_secret") or ""),
                audience=str(_entry_get(entry, "audience") or ""),
                scopes=[str(s) for s in (_entry_get(entry, "scopes") or [])],
                subject_token_type=str(
                    _entry_get(entry, "subject_token_type") or "access_token"
                ),
                rpm=max(0, int(_entry_get(entry, "rpm") or 0)),
                tpm=max(0, int(_entry_get(entry, "tpm") or 0)),
            )
        if not cfg.id or not cfg.url:
            continue
        if not cfg.triggers:
            cfg.triggers = [f"@mcp:{cfg.id}", f"@mcp {cfg.id}"]
        providers.append(
            McpEgressProvider(
                cfg,
                guardrails=guardrails,
                tool_search=tool_search,
                embedder=embedder,
                tool_policy=tool_policy,
                server_policy=server_policy,
                allow_private_networks=allow_private_networks,
                retry=policy,
                breaker=CircuitBreaker(
                    failure_threshold=max(1, int(failure_threshold)),
                    cooldown_seconds=max(1.0, float(cooldown_seconds)),
                    share_key=share_key_for("mcp", cfg.id),
                ),
                metrics=metrics,
                rate_limiter=rate_limiter,
                settings=settings,
            )
        )
    return providers
