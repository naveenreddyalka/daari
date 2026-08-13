from __future__ import annotations

import hmac
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from daari.config.project import apply_profile_to_meta, load_project_profile
from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text, sanitize_messages_for_ollama
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.gateway.sampling import SamplingParams
from daari.gateway.request_log import log_gateway_event
from daari.observability.tokens import estimate_tokens, response_token_usage
from daari.router.router import AppContext

OPENAI_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# Leads the message list when tools are stripped (issue #1). Must be the first
# system instruction so small local models don't mimic tool use described later
# in the client's own system prompt.
NO_TOOLS_HINT = (
    "IMPORTANT: You have NO tools available. Any tool, function, or capability "
    "descriptions elsewhere in this conversation are inactive and must be ignored. "
    "Respond in plain natural language only. Do not call tools, do not return JSON "
    "tool calls, and do not narrate or pretend to use tools."
)

# Backward-compat alias (pre-issue-#1 name).
PLAIN_TEXT_HINT = NO_TOOLS_HINT


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str | list[dict[str, Any]] | dict[str, Any] | None = None
    tool_calls: list[Any] | None = None


class EmbeddingsRequest(BaseModel):
    model: str = ""
    input: str | list[str]


def _embedding_texts(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _embedding_cache_request(model: str, text: str) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model=f"__embed__:{model}",
    )


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None
    # Declared so they reach SamplingParams instead of being dropped by
    # extra="ignore" (#161). Kept permissive: a client sending an odd shape used
    # to be ignored, and turning that into a 422 would trade silence for a hard
    # failure. SamplingParams validates and discards what it cannot use.
    max_tokens: Any | None = None
    max_completion_tokens: Any | None = None
    top_p: Any | None = None
    stop: Any | None = None
    seed: Any | None = None
    frequency_penalty: Any | None = None
    presence_penalty: Any | None = None
    response_format: Any | None = None
    tool_choice: Any | None = None
    n: Any | None = None
    logprobs: Any | None = None


def _to_internal_messages(messages: list[ChatMessage]) -> list[Message]:
    internal: list[Message] = []
    for message in messages:
        text = content_to_text(message.content)
        role = message.role
        if role == "developer":
            role = "system"
        if role == "assistant" and not text and not message.tool_calls:
            continue
        if role in {"user", "system"} and not text:
            continue
        internal.append(
            Message(
                role=role,
                content=text,
                tool_calls=message.tool_calls,
            )
        )
    return internal


def _prepare_internal_request(
    body: ChatCompletionRequest,
    *,
    default_model: str,
    meta: RequestMeta,
    tools_mode: str | None = None,
) -> InternalRequest:
    """Normalize Cursor/BYOK payloads for local text chat.

    Ask vs Agent split (issue #2 / ADR-0004): a request with tool_calls or tool
    role messages in history is an active agent loop — tools pass through
    untouched. Fresh tool-bearing requests (Cursor Ask) keep the strip + hint
    behavior. `X-Daari-Tools: passthrough|strip` overrides the detection.
    """
    sampling = SamplingParams.from_openai_body(body.model_dump())
    messages = _to_internal_messages(body.messages)
    user_messages = sum(1 for message in messages if message.role == "user")
    if user_messages == 0:
        raw_types = [
            {
                "role": message.role,
                "content_type": type(message.content).__name__,
                "block_types": [
                    block.get("type")
                    for block in (message.content if isinstance(message.content, list) else [])
                    if isinstance(block, dict)
                ],
            }
            for message in body.messages
        ]
        log_gateway_event("no_user_messages_after_normalize", {"raw": raw_types, "model": body.model})
    tools = body.tools
    mode = (tools_mode or "").strip().lower()
    has_tool_history = any(
        message.tool_calls or message.role == "tool" for message in body.messages
    )
    passthrough = mode == "passthrough" or (mode != "strip" and has_tool_history)
    if tools and passthrough:
        log_gateway_event(
            "tools_passthrough",
            {
                "count": len(tools),
                "model": body.model,
                "reason": mode if mode == "passthrough" else "tool_history",
            },
        )
    elif tools or (has_tool_history and mode == "strip"):
        if tools:
            log_gateway_event("tools_stripped", {"count": len(tools), "model": body.model})
        tools = None
        already_hinted = any(
            message.role == "system" and NO_TOOLS_HINT in (message.content or "")
            for message in messages
        )
        if not already_hinted:
            messages.insert(0, Message(role="system", content=NO_TOOLS_HINT))
        messages = sanitize_messages_for_ollama(messages)
    if sampling.tool_choice == "none" and tools:
        # The client explicitly opted out of tools for this turn.
        log_gateway_event("tools_disabled_by_tool_choice", {"count": len(tools)})
        tools = None
    return InternalRequest(
        messages=messages,
        model=body.model or default_model,
        temperature=body.temperature,
        tools=tools,
        stream=body.stream,
        sampling=sampling,
        meta=meta,
    )


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    daari_meta: dict[str, Any] | None = None


class FeedbackBody(BaseModel):
    trace_id: str
    signal: str


def build_chat_completion_payload(
    response: InternalResponse,
    *,
    prompt_chars: int,
    include_daari_meta: bool,
    client_model: str | None = None,
) -> dict[str, Any]:
    """Serialize an InternalResponse as an OpenAI chat completion.

    Token counts come from the provider when it reported them; `usage_estimated`
    in daari_meta says whether they had to be derived from chars (#156).
    """
    input_tokens, output_tokens, estimated = response_token_usage(response, prompt_chars)
    meta = response.daari_meta.model_dump(exclude_none=True)
    meta["usage_estimated"] = estimated
    payload = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=client_model or response.model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=response.content),
                finish_reason=response.finish_reason or "stop",
            )
        ],
        usage={
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        daari_meta=meta if include_daari_meta else None,
    )
    return payload.model_dump(exclude_none=True)


def _openai_completion_body(
    *,
    body: ChatCompletionRequest,
    result_content: str,
    result_model: str,
    daari_meta: dict[str, Any] | None,
    include_daari_meta: bool,
    usage: tuple[int, int, bool] | None = None,
) -> dict[str, Any]:
    prompt_chars = sum(len(message.content or "") for message in body.messages)
    if usage is not None:
        input_tokens, output_tokens, estimated = usage
    else:
        input_tokens = estimate_tokens(prompt_chars)
        output_tokens = estimate_tokens(len(result_content))
        estimated = True
    meta = dict(daari_meta) if daari_meta else None
    if meta is not None:
        meta["usage_estimated"] = estimated
    payload = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=body.model or result_model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=result_content),
                finish_reason="stop",
            )
        ],
        usage={
            "prompt_tokens": max(1, input_tokens),
            "completion_tokens": max(0, output_tokens),
            "total_tokens": max(1, input_tokens + output_tokens),
        },
        daari_meta=meta if include_daari_meta else None,
    )
    return payload.model_dump(exclude_none=True)


class OpenAIGatewayAdapter(GatewayAdapter):
    id = "openai"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/chat/completions", response_model=None)
        async def chat_completions(
            body: ChatCompletionRequest,
            request: Request,
            x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
            x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
            x_daari_tier_cap: str | None = Header(default=None, alias="X-Daari-Tier-Cap"),
            x_daari_no_frontier: str | None = Header(default=None, alias="X-Daari-No-Frontier"),
            x_daari_latency_budget: str | None = Header(default=None, alias="X-Daari-Latency-Budget"),
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_confirm_tool: str | None = Header(default=None, alias="X-Daari-Confirm-Tool"),
            x_daari_confirm: str | None = Header(default=None, alias="X-Daari-Confirm"),
            x_daari_rerun_command: str | None = Header(default=None, alias="X-Daari-ReRun-Command"),
            x_daari_meta: str | None = Header(default=None, alias="X-Daari-Meta"),
            x_daari_tools: str | None = Header(default=None, alias="X-Daari-Tools"),
            x_daari_project: str | None = Header(default=None, alias="X-Daari-Project"),
        ) -> Any:
            confirm_value = (x_daari_confirm or x_daari_confirm_tool or "").strip().lower()
            confirm_tool = confirm_value in {"1", "true", "yes"}
            try:
                latency_budget_ms = int(x_daari_latency_budget) if x_daari_latency_budget else None
            except ValueError:
                latency_budget_ms = None
            include_daari_meta = (x_daari_meta or "").strip().lower() in {"1", "true", "yes"}
            include_usage = bool(body.stream_options and body.stream_options.get("include_usage"))
            client_host = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "")
            # T5b: explicit header wins; otherwise attribute Cursor traffic
            # by user-agent so per-client reports work with zero config.
            client_id = x_daari_client_id or (
                "cursor" if "cursor" in user_agent.lower() else None
            )
            log_gateway_event(
                "chat_completions_request",
                {
                    "client": client_host,
                    "user_agent": user_agent[:200],
                    "model": body.model,
                    "stream": body.stream,
                    "stream_options": body.stream_options,
                    "message_count": len(body.messages),
                    "roles": [message.role for message in body.messages],
                    "tools": len(body.tools or []),
                },
            )

            ctx: AppContext = request.app.state.ctx
            meta = RequestMeta(
                no_cache=x_daari_no_cache == "true",
                tier_override=x_daari_tier_override,
                tier_cap=x_daari_tier_cap,
                latency_budget_ms=latency_budget_ms,
                client_id=client_id,
                no_frontier=x_daari_no_frontier == "true",
                confirm_tool=confirm_tool,
                rerun_command=x_daari_rerun_command == "true",
                stream_include_usage=include_usage,
            )
            # Virtual-key defaults (issue #111); headers keep precedence.
            from daari.server.auth import apply_auth_claims_to_meta

            apply_auth_claims_to_meta(meta, getattr(request.state, "auth_claims", None))
            # Per-project profile defaults (issue #91); headers keep precedence.
            apply_profile_to_meta(meta, load_project_profile(x_daari_project))
            internal = _prepare_internal_request(
                body,
                default_model=ctx.settings.models.l3,
                tools_mode=x_daari_tools,
                meta=meta,
            )

            if body.stream:

                async def event_stream() -> AsyncIterator[str]:
                    content_chars = 0
                    try:
                        async for chunk in ctx.router.stream_openai_chunks(internal):
                            if '"delta": {"content":' in chunk or '"delta":{"content":' in chunk:
                                content_chars += 1
                            yield chunk
                    except Exception as exc:
                        yield f"data: {json.dumps({'error': f'stream failed: {exc}'})}\n\n"
                        yield "data: [DONE]\n\n"
                    finally:
                        log_gateway_event(
                            "chat_completions_stream_done",
                            {
                                "client": client_host,
                                "model": body.model,
                                "content_chunks": content_chars,
                            },
                        )

                return StreamingResponse(
                    event_stream(),
                    media_type="text/event-stream",
                    headers=OPENAI_SSE_HEADERS,
                )

            try:
                result = await ctx.router.route(internal)
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc

            prompt_chars = sum(len(message.content or "") for message in body.messages)
            return _openai_completion_body(
                body=body,
                result_content=result.content,
                result_model=result.model,
                daari_meta=result.daari_meta.model_dump(exclude_none=True),
                include_daari_meta=include_daari_meta,
                usage=response_token_usage(result, prompt_chars),
            )

        @router.post("/v1/embeddings")
        async def embeddings(body: EmbeddingsRequest, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            configured = ctx.settings.cache.l1.embedding_model
            requested = (body.model or "").strip() or "daari"
            if requested not in {"daari", configured}:
                raise HTTPException(
                    status_code=400, detail=f"unknown embedding model: {requested}"
                )
            model = configured
            embedder = ctx.router.semantic_cache.embedder
            texts = _embedding_texts(body.input)
            vectors: list[list[float]] = []
            cache_hits = 0
            for text in texts:
                cached = ctx.router.cache.get(_embedding_cache_request(model, text))
                if cached is not None:
                    vectors.append(json.loads(cached.content))
                    cache_hits += 1
                    continue
                embedding = await embedder.embed(text, model=model)
                if embedding is None:
                    raise HTTPException(
                        status_code=502, detail=f"embedding model {model} returned no vector"
                    )
                ctx.router.cache.put(
                    _embedding_cache_request(model, text),
                    InternalResponse(
                        content=json.dumps(embedding),
                        model=model,
                        daari_meta=DaariMeta(
                            tier="embed",
                            cache_hit=False,
                            executor="ollama",
                            provider_id="ollama",
                            model=model,
                        ),
                    ),
                )
                vectors.append(embedding)
            prompt_chars = sum(len(text) for text in texts)
            ctx.metrics.record(
                "embed",
                cache_hit=bool(texts) and cache_hits == len(texts),
                latency_ms=0,
            )
            if ctx.router.usage_ledger is not None:
                ctx.router.usage_ledger.record(
                    tier="embed",
                    cache_hit=bool(texts) and cache_hits == len(texts),
                    prompt_chars=prompt_chars,
                    model=model,
                    provider="ollama",
                    input_tokens=estimate_tokens(prompt_chars),
                    output_tokens=0,
                )
            return {
                "object": "list",
                "data": [
                    {"object": "embedding", "index": index, "embedding": vector}
                    for index, vector in enumerate(vectors)
                ],
                "model": model,
                "usage": {
                    "prompt_tokens": estimate_tokens(prompt_chars),
                    "total_tokens": estimate_tokens(prompt_chars),
                },
            }

        @router.get("/v1/models")
        async def list_models(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            created = int(time.time())
            model_ids = [
                "daari",
                ctx.settings.models.l3,
                ctx.settings.models.l4,
                ctx.settings.models.l5,
                ctx.settings.cache.l1.embedding_model,
            ]
            unique_ids: list[str] = []
            for model_id in model_ids:
                if model_id not in unique_ids:
                    unique_ids.append(model_id)
            return {
                "object": "list",
                "data": [
                    {
                        "id": model_id,
                        "object": "model",
                        "created": created,
                        "owned_by": "daari" if model_id == "daari" else "ollama",
                    }
                    for model_id in unique_ids
                ],
            }

        @router.get("/v1/models/{model_id}")
        async def retrieve_model(model_id: str) -> dict[str, Any]:
            return {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "daari" if model_id == "daari" else "ollama",
            }

        @router.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @router.get("/metrics")
        async def prometheus_metrics(request: Request):
            """Prometheus exposition (issue #107). Disabled via
            observability.prometheus=false. Auth follows server.api_key —
            open when unset, required otherwise (middleware)."""
            from fastapi.responses import PlainTextResponse

            from daari.observability.prometheus import render_prometheus

            ctx: AppContext = request.app.state.ctx
            settings = ctx.settings
            if not settings.observability.prometheus:
                raise HTTPException(status_code=404, detail="prometheus metrics disabled")

            budget_state: dict[str, Any] | None = None
            false_hit_rate: float | None = None
            price = float(settings.frontier.price_per_1k_tokens or 0.002)
            ledger = getattr(ctx.router, "usage_ledger", None)
            if ledger is not None and getattr(ledger, "enabled", False):
                try:
                    daily = float(ledger.frontier_spend_usd(price_per_1k_tokens=price))
                    monthly = float(ledger.frontier_spend_usd_month(price_per_1k_tokens=price))
                    daily_cap = float(settings.frontier.daily_budget_usd or 0.0)
                    monthly_cap = float(settings.frontier.monthly_budget_usd or 0.0)
                    state = "ok"
                    soft = settings.frontier.soft_budget_ratio
                    for spend, cap in ((daily, daily_cap), (monthly, monthly_cap)):
                        if cap <= 0:
                            continue
                        ratio = spend / cap
                        if ratio >= 1.0:
                            state = "exceeded"
                            break
                        if ratio >= soft and state == "ok":
                            state = "soft"
                    budget_state = {
                        "daily_spend_usd": daily,
                        "monthly_spend_usd": monthly,
                        "daily_budget_usd": daily_cap,
                        "monthly_budget_usd": monthly_cap,
                        "state": state,
                    }
                except Exception:
                    budget_state = None
            feedback = getattr(ctx.router, "feedback_store", None)
            if feedback is not None and getattr(feedback, "enabled", False):
                try:
                    shadow = feedback.shadow_stats(days=7)
                    samples = sum(row.get("samples", 0) for row in shadow.values())
                    disagrees = sum(row.get("disagreements", 0) for row in shadow.values())
                    if samples:
                        false_hit_rate = round(disagrees / samples, 4)
                except Exception:
                    false_hit_rate = None

            body = render_prometheus(
                ctx.metrics, budget_state=budget_state, false_hit_rate=false_hit_rate
            )
            return PlainTextResponse(
                content=body,
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

        @router.get("/ready")
        async def ready(request: Request) -> JSONResponse:
            """Readiness probe (issue #105): unlike /health liveness, this
            verifies the daemon can actually serve — cache handles exist and
            the L3 model backend answers. Returns 503 while dependencies are
            down so orchestrators keep traffic away."""
            ctx: AppContext = request.app.state.ctx
            base_url = ctx.ollama_l3.base_url.rstrip("/")
            probe = (
                f"{base_url}/v1/models"
                if type(ctx.ollama_l3).__name__ == "MLXExecutor"
                else f"{base_url}/api/version"
            )
            checks = {
                "cache": "ok" if ctx.cache is not None else "missing",
                "model_backend": await check_model_backend(probe),
            }
            ready_now = all(value == "ok" for value in checks.values())
            return JSONResponse(
                status_code=200 if ready_now else 503,
                content={"status": "ready" if ready_now else "not_ready", "checks": checks},
            )

        @router.get("/v1/daari/stats")
        async def daari_stats(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            snapshot = ctx.metrics.snapshot()
            total = sum(t["count"] for t in snapshot.values())
            return {"total_requests": total, "errors": ctx.metrics.errors, "tiers": snapshot}

        @router.get("/v1/daari/traces")
        async def daari_traces(request: Request, limit: int = 20) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.router.trace_store
            if store is None:
                raise HTTPException(status_code=404, detail="trace store is not configured")
            return {"traces": store.list(limit=max(1, min(limit, 200)))}

        @router.get("/v1/daari/traces/{trace_id}")
        async def daari_trace_detail(trace_id: str, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.router.trace_store
            if store is None:
                raise HTTPException(status_code=404, detail="trace store is not configured")
            trace = store.get(trace_id)
            if trace is None:
                raise HTTPException(status_code=404, detail=f"trace {trace_id} not found")
            return trace

        @router.get("/v1/daari/report")
        async def daari_report(request: Request, days: int = 7) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            ledger = ctx.router.usage_ledger
            if ledger is None:
                raise HTTPException(status_code=404, detail="usage ledger is not configured")
            payload = ledger.report(
                days=max(1, days),
                frontier_price_per_1k_tokens=ctx.settings.usage.frontier_price_per_1k_tokens,
            )
            payload["frontier"] = {
                "today_spend_usd": round(
                    ledger.frontier_spend_usd(
                        price_per_1k_tokens=ctx.settings.frontier.price_per_1k_tokens
                    ),
                    4,
                ),
                "daily_budget_usd": ctx.settings.frontier.daily_budget_usd,
                "month_spend_usd": round(
                    ledger.frontier_spend_usd_month(
                        price_per_1k_tokens=ctx.settings.frontier.price_per_1k_tokens
                    ),
                    4,
                ),
                "monthly_budget_usd": ctx.settings.frontier.monthly_budget_usd,
                "soft_budget_ratio": ctx.settings.frontier.soft_budget_ratio,
                "budget_state": ctx.router._frontier_budget_state(),
            }
            payload["clients"] = ledger.by_client(
                days=max(1, days),
                frontier_price_per_1k_tokens=ctx.settings.usage.frontier_price_per_1k_tokens,
            )
            # Trust PRD T1d: false-hit rates + answer diversity per category.
            trust: dict[str, Any] = {}
            feedback = ctx.router.feedback_store
            if feedback is not None:
                try:
                    trust["false_hit_rates"] = feedback.shadow_stats(days=max(1, days))
                except Exception:
                    trust["false_hit_rates"] = {}
            try:
                trust["diversity"] = ctx.router.semantic_cache.diversity_stats()
            except Exception:
                trust["diversity"] = {}
            payload["cache_trust"] = trust
            return payload

        @router.get("/v1/daari/cache/diversity")
        async def daari_cache_diversity(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            try:
                categories = ctx.router.semantic_cache.diversity_stats()
            except Exception:
                categories = {}
            return {"categories": categories}

        @router.get("/v1/daari/learn/stats")
        async def daari_learn_stats(request: Request, days: int = 7) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.router.feedback_store
            if store is None:
                raise HTTPException(status_code=404, detail="feedback store is not configured")
            try:
                shadow = store.shadow_stats(days=max(1, days))
            except Exception:
                shadow = {}
            return {
                "days": max(1, days),
                "categories": store.stats(days=max(1, days)),
                "shadow": shadow,
            }

        @router.post("/v1/daari/feedback")
        async def daari_feedback(request: Request, body: FeedbackBody) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.router.feedback_store
            if store is None:
                raise HTTPException(status_code=404, detail="feedback store is not configured")
            try:
                recorded = store.record_signal(body.trace_id, body.signal)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if not recorded:
                raise HTTPException(
                    status_code=404, detail=f"no outcome recorded for trace {body.trace_id}"
                )
            # D2a: accepted examples become training data; rejected ones are
            # deleted so they can never be trained on.
            example_store = getattr(ctx.router, "example_store", None)
            if example_store is not None:
                try:
                    if body.signal == "accept":
                        example_store.mark_accepted(body.trace_id)
                    else:
                        example_store.delete(body.trace_id)
                except Exception:
                    pass
            return {"trace_id": body.trace_id, "signal": body.signal, "recorded": True}

        @router.post("/v1/daari/reload-caches")
        async def daari_reload_caches(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            payload = ctx.reload_cache_handles()
            return {"status": "ok", **payload}

        def _require_config_editor(ctx: AppContext) -> None:
            if not ctx.settings.observability.config_editor:
                raise HTTPException(status_code=404, detail="config editor disabled")

        def _require_admin_role(request: Request, ctx: AppContext) -> str:
            """SSO role gate for admin surfaces when enterprise.sso.enabled."""
            sso = ctx.settings.enterprise.sso
            oidc_ready = bool(sso.jwks_url.strip() or sso.discovery_url.strip())
            if not sso.enabled or (not sso.secret and not oidc_ready):
                return "admin"
            from daari.enterprise.rbac import role_at_least, role_from_claims
            from daari.enterprise.sso import verify_access_token

            auth = request.headers.get("authorization", "")
            token = ""
            if auth.lower().startswith("bearer "):
                token = auth[len("bearer ") :].strip()
            if not token:
                raise HTTPException(status_code=401, detail="SSO token required")
            # Master API key still counts as admin when it matches.
            master = ctx.settings.server.api_key.strip()
            if master and hmac.compare_digest(token, master):
                return "admin"
            try:
                claims = verify_access_token(token, sso)
            except Exception as exc:  # noqa: BLE001 — surface auth failures as 401
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            role = role_from_claims(claims, role_claim=sso.role_claim)
            if not role_at_least(role, sso.admin_min_role):
                raise HTTPException(status_code=403, detail="insufficient role")
            request.state.sso_claims = claims
            return role

        @router.post("/v1/daari/sso/session")
        async def daari_sso_session(request: Request) -> dict[str, Any]:
            """Validate SSO token; optionally mint a virtual key for the subject (#136)."""
            ctx: AppContext = request.app.state.ctx
            sso = ctx.settings.enterprise.sso
            if not sso.enabled:
                raise HTTPException(status_code=404, detail="SSO disabled")
            from daari.enterprise.rbac import role_from_claims
            from daari.enterprise.sso import verify_access_token

            auth = request.headers.get("authorization", "")
            token = auth[len("bearer ") :].strip() if auth.lower().startswith("bearer ") else ""
            if not token:
                raise HTTPException(status_code=401, detail="Bearer token required")
            try:
                claims = verify_access_token(token, sso)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            subject = str(claims.get("sub") or "")
            role = role_from_claims(claims, role_claim=sso.role_claim)
            result: dict[str, Any] = {
                "sub": subject,
                "role": role,
                "issuer": claims.get("iss"),
            }
            if sso.mint_virtual_key_on_login and subject:
                from daari.auth.virtual_keys import VirtualKeyStore
                from daari.enterprise.audit import AuditLog

                store = VirtualKeyStore(
                    ctx.settings.virtual_keys_path,
                    enabled=True,
                )
                existing = [
                    k for k in store.list() if (k.client_id or "") == f"sso:{subject}" and not k.revoked
                ]
                if existing:
                    result["virtual_key_id"] = existing[0].key_id
                    result["virtual_key_minted"] = False
                else:
                    created = store.create(
                        name=f"sso:{subject}",
                        client_id=f"sso:{subject}",
                        tier_cap=None,
                    )
                    result["virtual_key_id"] = created.key.key_id
                    result["virtual_key_prefix"] = created.key.prefix
                    result["virtual_key"] = created.plaintext
                    result["virtual_key_minted"] = True
                    AuditLog(ctx.settings.enterprise.audit_path).record(
                        actor=subject,
                        role=role,
                        action="sso.mint_virtual_key",
                        detail={"key_id": created.key.key_id},
                    )
            return result

        @router.get("/v1/daari/config")
        async def daari_config_get(request: Request) -> dict[str, Any]:
            """Safe config subset for the web UI editor (issue #115)."""
            ctx: AppContext = request.app.state.ctx
            _require_config_editor(ctx)
            _require_admin_role(request, ctx)
            s = ctx.settings
            return {
                "routing": {
                    "prefer": s.routing.prefer,
                    "confidence_threshold": s.routing.confidence_threshold,
                    "latency_budget_ms": s.routing.latency_budget_ms,
                    "max_tier_for_chat": s.routing.max_tier_for_chat,
                },
                "frontier": {
                    "daily_budget_usd": s.frontier.daily_budget_usd,
                    "monthly_budget_usd": s.frontier.monthly_budget_usd,
                    "soft_budget_ratio": s.frontier.soft_budget_ratio,
                },
                "cache": {
                    "l0_ttl_seconds": s.cache.l0.ttl_seconds,
                    "l1_ttl_seconds": s.cache.l1.ttl_seconds,
                    "l1_similarity_threshold": s.cache.l1.similarity_threshold,
                },
                "boundaries": {
                    "enabled": s.boundaries.enabled,
                    "mode": s.boundaries.mode,
                    "product_name": s.boundaries.product_name,
                    "product_description": s.boundaries.product_description,
                    "allow_topics": list(s.boundaries.allow_topics),
                    "deny_topics": list(s.boundaries.deny_topics),
                    "examples_in": list(s.boundaries.examples_in),
                    "examples_out": list(s.boundaries.examples_out),
                    "refuse_message": s.boundaries.refuse_message,
                    "clear_out_threshold": s.boundaries.clear_out_threshold,
                    "clear_in_threshold": s.boundaries.clear_in_threshold,
                    "stages_b0": s.boundaries.stages_b0,
                    "stages_b1": s.boundaries.stages_b1,
                    "stages_b2": s.boundaries.stages_b2,
                    "stages_b3": s.boundaries.stages_b3,
                },
            }

        @router.patch("/v1/daari/config")
        async def daari_config_patch(request: Request) -> dict[str, Any]:
            """Apply a safe config subset; optional `persist: true` writes config.yaml."""
            ctx: AppContext = request.app.state.ctx
            _require_config_editor(ctx)
            role = _require_admin_role(request, ctx)
            body = await request.json()
            persist = bool(body.pop("persist", False)) if isinstance(body, dict) else False
            from daari.config.validate import (
                ConfigValidationError,
                merged_boundaries,
                validated_cache,
                validated_frontier,
                validated_routing,
            )

            # Validate the whole patch before touching live settings, so a bad
            # field is a 400 instead of a half-applied config.
            try:
                routing = validated_routing(body.get("routing") or {})
                frontier = validated_frontier(body.get("frontier") or {})
                cache = validated_cache(body.get("cache") or {})
                raw_boundaries = body.get("boundaries") or {}
                new_boundaries = (
                    merged_boundaries(ctx.settings.boundaries, raw_boundaries)
                    if raw_boundaries
                    else None
                )
            except ConfigValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            boundaries = raw_boundaries
            if "confidence_threshold" in routing:
                ctx.router.confidence_threshold = routing["confidence_threshold"]
                ctx.settings.routing.confidence_threshold = routing["confidence_threshold"]
            if "latency_budget_ms" in routing:
                ctx.router.latency_budget_ms = routing["latency_budget_ms"]
                ctx.settings.routing.latency_budget_ms = routing["latency_budget_ms"]
            if "max_tier_for_chat" in routing:
                ctx.router.max_tier_for_chat = routing["max_tier_for_chat"]
                ctx.settings.routing.max_tier_for_chat = routing["max_tier_for_chat"]
            if "prefer" in routing:
                ctx.router.model_preference = routing["prefer"]
                ctx.settings.routing.prefer = routing["prefer"]
            for key in ("daily_budget_usd", "monthly_budget_usd", "soft_budget_ratio"):
                if key in frontier:
                    setattr(ctx.settings.frontier, key, frontier[key])
                    if hasattr(ctx.router, f"frontier_{key}"):
                        setattr(ctx.router, f"frontier_{key}", frontier[key])
            if "l0_ttl_seconds" in cache:
                ctx.settings.cache.l0.ttl_seconds = cache["l0_ttl_seconds"]
            if "l1_ttl_seconds" in cache:
                ctx.settings.cache.l1.ttl_seconds = cache["l1_ttl_seconds"]
            if "l1_similarity_threshold" in cache:
                ctx.settings.cache.l1.similarity_threshold = cache["l1_similarity_threshold"]
                ctx.router.semantic_cache.similarity_threshold = cache[
                    "l1_similarity_threshold"
                ]
            if new_boundaries is not None:
                from daari.gateway.boundaries import default_local_judge, engine_from_settings

                ctx.settings.boundaries = new_boundaries
                ctx.router.boundaries = engine_from_settings(
                    ctx.settings, judge=default_local_judge
                )
            persisted_path = None
            if persist:
                from daari.config.persist import persist_safe_config

                persisted_path = str(
                    persist_safe_config(
                        {
                            "routing": routing,
                            "frontier": frontier,
                            "cache": cache,
                            "boundaries": boundaries,
                        }
                    )
                )
            from daari.enterprise.audit import AuditLog

            AuditLog(ctx.settings.enterprise.audit_path).record(
                actor=request.headers.get("x-daari-actor", "api"),
                role=role,
                action="config.patch",
                detail={"keys": sorted(body.keys()), "persist": persist},
            )
            result = await daari_config_get(request)
            if persisted_path:
                result["persisted_to"] = persisted_path
            return result

        @router.get("/v1/daari/audit")
        async def daari_audit_list(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_admin_role(request, ctx)
            from daari.enterprise.audit import AuditLog

            entries = AuditLog(ctx.settings.enterprise.audit_path).list(limit=100)
            return {"entries": entries}

        @router.post("/v1/org-learning/sync")
        async def org_learning_sync(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            if ctx.org_learning_client is None:
                raise HTTPException(status_code=404, detail="org learning is not configured")
            changed = await ctx.sync_org_learning_profile_once()
            return {
                "status": "ok",
                "changed": changed,
                "routing": {
                    "prefer": ctx.router.model_preference,
                    "confidence_threshold": ctx.router.confidence_threshold,
                },
            }

        return router


async def check_model_backend(probe_url: str, timeout: float = 2.0) -> str:
    """Readiness dependency check (issue #105). Returns "ok" or a short
    diagnostic; module-level so tests and future backends can override."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(probe_url)
    except Exception as exc:
        return type(exc).__name__
    if response.status_code >= 500:
        return f"http {response.status_code}"
    return "ok"


def create_gateway_router() -> APIRouter:
    return OpenAIGatewayAdapter().router()
