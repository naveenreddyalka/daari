from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from daari.config.project import apply_profile_to_meta, load_project_profile
from daari.gateway.client_errors import (
    backend_unavailable_message,
    request_deadline_response,
    routing_failure_detail,
    safe_detail,
)
from daari.gateway.base import GatewayAdapter
from daari.gateway.cost_tier import apply_cost_tier
from daari.gateway.content import (
    content_to_text,
    extract_audio,
    extract_images,
    sanitize_messages_for_ollama,
)
from daari.gateway.internal import (
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.gateway.provider_prefs import (
    as_openrouter_payload,
    configured_frontier_slots,
    require_zdr_slot,
    RegionUnavailable,
    ZdrUnavailable,
)
from daari.gateway.sampling import SamplingParams
from daari.gateway.cost_headers import (
    DeferredHeadersStreamingResponse,
    StreamOutcome,
    response_cost_headers,
)
from daari.gateway.embeddings_api import (
    compute_embeddings,
    embedding_texts,
    openai_embeddings_payload,
    resolve_embedding_model,
)
from daari.gateway.disconnect import (
    ClientDisconnected,
    await_unless_disconnected,
    note_request_cancelled,
)
from daari.gateway.streaming import stream_with_keepalive
from daari.gateway.request_log import log_gateway_event
from daari.router.deadline import RequestDeadlineExceeded
from daari.observability.tokens import estimate_tokens, response_token_usage
from daari.router.router import AppContext
from daari.router.capabilities import UnsupportedCapability
from daari.router.local_pool import BackendUnavailable

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
    # Agent SDK sampling knobs (#940). Same #161 pattern — declare so they
    # reach SamplingParams instead of vanishing under extra="ignore".
    parallel_tool_calls: Any | None = None
    logit_bias: Any | None = None
    top_logprobs: Any | None = None
    # Remaining OpenAI chat knobs (#1007). Same #161 pattern.
    store: Any | None = None
    metadata: Any | None = None
    prediction: Any | None = None
    modalities: Any | None = None
    audio: Any | None = None
    verbosity: Any | None = None
    web_search_options: Any | None = None
    # OpenRouter `provider` object (G2 / #224). extra="ignore" would drop it.
    provider: Any | None = None
    # OpenAI reasoning_effort (o-series / gpt-5 clients). Same #161 pattern (#297).
    reasoning_effort: Any | None = None
    # Stable end-user id. Used as a session key when routing.session_affinity is on.
    user: str | None = None
    # OpenRouter Auto `cost_tier` / `plugins: [{id: auto-router}]` (#388).
    cost_tier: str | None = None
    plugins: list[Any] | None = None
    # OpenAI/OpenRouter service_tier (flex|standard|priority|fast). Same #161
    # pattern — declare so it reaches SamplingParams (#1005).
    service_tier: str | None = None


def _to_internal_messages(messages: list[ChatMessage]) -> list[Message]:
    internal: list[Message] = []
    for message in messages:
        text = content_to_text(message.content)
        images = extract_images(message.content)
        audio = extract_audio(message.content)
        role = message.role
        if role == "developer":
            role = "system"
        if role == "assistant" and not text and not message.tool_calls:
            continue
        if role in {"user", "system"} and not text and not images and not audio:
            continue
        internal.append(
            Message(
                role=role,
                content=text,
                tool_calls=message.tool_calls,
                images=images,
                audio=audio,
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
        log_gateway_event(
            "no_user_messages_after_normalize", {"raw": raw_types, "model": body.model}
        )
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
    from daari.gateway.provider_prefs import parse_provider

    return InternalRequest(
        messages=messages,
        model=body.model or default_model,
        temperature=body.temperature,
        tools=tools,
        stream=body.stream,
        sampling=sampling,
        meta=meta,
        provider=parse_provider(body.provider),
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
    usage: dict[str, int] = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    daari_meta: dict[str, Any] | None = None


class FeedbackBody(BaseModel):
    trace_id: str
    signal: str


class BatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = "/v1/chat/completions"
    completion_window: str = "24h"
    input_file_id: str | None = None
    # Inline chat-completion bodies or OpenAI JSONL-line objects (tests / local).
    requests: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


async def _execute_batch_chat_body(
    ctx: AppContext,
    body_dict: dict[str, Any],
    *,
    governance: Any | None = None,
    rate_limiter: Any | None = None,
) -> dict[str, Any]:
    """Run one batch item through the same router path as /v1/chat/completions."""
    from daari.gateway.batches import BatchGovernance, BatchItemRejected

    acquired = False
    if rate_limiter is not None and int(getattr(rate_limiter, "max_in_flight", 0) or 0) > 0:
        slot = await rate_limiter.acquire(priority="low")
        if not slot.allowed:
            raise BatchItemRejected(
                {
                    "type": "rate_limit_error",
                    "message": "In-flight concurrency limit exceeded.",
                }
            )
        acquired = True
    try:
        body = ChatCompletionRequest.model_validate(body_dict)
        gov = governance if isinstance(governance, BatchGovernance) else None
        body_user = (body.user or "").strip() or None
        meta = RequestMeta(
            tier_cap=gov.tier_cap if gov else None,
            latency_budget_ms=gov.latency_budget_ms if gov else None,
            deadline_ms=gov.deadline_ms if gov else None,
            client_id=gov.client_id if gov else None,
            user_agent=gov.user_agent if gov else None,
            user=body_user or (gov.user if gov else None),
            session_id=gov.session_id if gov else None,
            no_frontier=bool(gov.no_frontier) if gov else False,
            boundary_profile=gov.boundary_profile if gov else None,
            key_id=gov.key_id if gov else None,
            team_id=gov.team_id if gov else None,
            cache_scope=(gov.cache_scope if gov and gov.cache_scope else "global"),
        )
        apply_cost_tier(body, meta)
        _enforce_batch_item_model_access(ctx, body, meta, governance=gov)
        _enforce_batch_item_rate_limits(ctx, body_dict, governance=gov)
        _enforce_batch_item_budgets(ctx, meta, governance=gov)
        internal = _prepare_internal_request(
            body,
            default_model=ctx.settings.models.l3,
            meta=meta,
        )
        from daari.gateway.transcriptions import inject_inline_audio_transcripts

        internal = await inject_inline_audio_transcripts(internal, ctx.settings)
        result = await ctx.router.route(internal)
        prompt_chars = sum(len(message.content or "") for message in internal.messages)
        return build_chat_completion_payload(
            result,
            prompt_chars=prompt_chars,
            include_daari_meta=False,
            client_model=body.model or None,
        )
    finally:
        if acquired:
            await rate_limiter.release()


def _batch_lookup_virtual_key(ctx: AppContext, governance: Any) -> Any | None:
    store = getattr(ctx, "virtual_key_store", None)
    if store is None or not getattr(governance, "key_id", None):
        return None
    for candidate in store.list() or []:
        if candidate.key_id == governance.key_id:
            return candidate
    return None


def _enforce_batch_item_model_access(
    ctx: AppContext,
    body: ChatCompletionRequest,
    meta: RequestMeta,
    *,
    governance: Any | None,
) -> None:
    """Reject items whose model is outside the creating key's allowlist (#840)."""
    from daari.auth.model_access import (
        denial_body,
        effective_patterns,
        model_permitted,
        record_model_denial,
    )
    from daari.gateway.batches import BatchGovernance, BatchItemRejected

    if not isinstance(governance, BatchGovernance) or governance.kind != "virtual":
        return
    key = _batch_lookup_virtual_key(ctx, governance)
    if key is None:
        return
    store = getattr(ctx, "virtual_key_store", None)
    team = store.get_team(key.team_id) if store is not None and key.team_id else None
    catalog = getattr(ctx.settings, "model_groups", None) or {}
    key_patterns = effective_patterns(key.allowed_models, key.model_groups, catalog)
    team_patterns = (
        effective_patterns(team.allowed_models, team.model_groups, catalog)
        if team is not None
        else None
    )
    meta.key_model_patterns = key_patterns
    meta.team_model_patterns = team_patterns
    model = (body.model or ctx.settings.models.l3 or "").strip()
    if model_permitted(model, key_patterns=key_patterns, team_patterns=team_patterns):
        return
    record_model_denial(
        ctx.settings,
        model=model,
        key_id=governance.key_id,
        client_id=governance.client_id,
        path="/v1/batches",
    )
    raise BatchItemRejected(denial_body(model)["error"])


def _enforce_batch_item_rate_limits(
    ctx: AppContext,
    body_dict: dict[str, Any],
    *,
    governance: Any | None,
) -> None:
    """Charge RPM/TPM/RPD (and team caps) for virtual-key batch items (#840)."""
    from daari.auth.rate_limit import estimate_request_tokens, request_model
    from daari.gateway.batches import BatchGovernance, BatchItemRejected

    if not isinstance(governance, BatchGovernance) or governance.kind != "virtual":
        return
    limiter = getattr(ctx, "rate_limiter", None)
    if limiter is None:
        return
    key = _batch_lookup_virtual_key(ctx, governance)
    if key is None:
        return
    store = getattr(ctx, "virtual_key_store", None)
    team = store.get_team(key.team_id) if store is not None and key.team_id else None
    rpm = int(getattr(key, "rpm", 0) or 0) or None
    tpm = int(getattr(key, "tpm", 0) or 0) or None
    rpd = int(getattr(key, "rpd", 0) or 0) or None
    team_rpm = int(getattr(team, "rpm", 0) or 0) or None if team is not None else None
    team_tpm = int(getattr(team, "tpm", 0) or 0) or None if team is not None else None
    team_rpd = int(getattr(team, "rpd", 0) or 0) or None if team is not None else None
    decision = limiter.check(
        key_id=governance.key_id or key.key_id,
        model=request_model(body_dict),
        tokens=estimate_request_tokens(body_dict),
        rpm=rpm,
        tpm=tpm,
        team_id=getattr(key, "team_id", None) or governance.team_id,
        team_rpm=team_rpm,
        team_tpm=team_tpm,
        rpd=rpd,
        team_rpd=team_rpd,
    )
    if decision.allowed:
        return
    raise BatchItemRejected(
        {
            "type": "rate_limit_error",
            "message": f"{decision.scope or 'rate'} limit exceeded.",
        }
    )


def _batch_frontier_allowed(ctx: AppContext, meta: RequestMeta) -> bool:
    """Whether this item's meta could escalate to L6 (mirrors router gate)."""
    router = ctx.router
    if meta.no_frontier or not getattr(router, "frontier_enabled", False):
        return False
    cap = (meta.tier_cap or "").upper()
    if cap in {"L3", "L4", "L5"}:
        return False
    frontier = getattr(router, "frontier", None)
    return frontier is not None and bool(getattr(frontier, "api_key", None))


def _enforce_batch_item_budgets(
    ctx: AppContext,
    meta: RequestMeta,
    *,
    governance: Any | None,
) -> None:
    """Fail frontier-capable items when the creating key is over budget (#441)."""
    from daari.gateway.batches import BatchGovernance, BatchItemRejected

    if not isinstance(governance, BatchGovernance) or governance.kind != "virtual":
        return
    if not _batch_frontier_allowed(ctx, meta):
        return
    store = getattr(ctx, "virtual_key_store", None)
    if store is None:
        return
    key = None
    if governance.key_id:
        for candidate in store.list() or []:
            if candidate.key_id == governance.key_id:
                key = candidate
                break
    if key is None:
        return
    ledger = getattr(ctx.router, "usage_ledger", None)
    if ledger is None or not getattr(ledger, "enabled", False):
        return
    from daari.auth.budgets import budget_error, budget_status, user_daily_cap_exceeded

    client = meta.client_id or governance.client_id or governance.key_id or ""
    pricing = getattr(ctx.settings, "pricing", None)
    fallback = float(ctx.settings.usage.frontier_price_per_1k_tokens or 0.002)
    team = store.get_team(key.team_id) if getattr(key, "team_id", None) else None
    team_ids = store.team_client_ids(team.team_id) if team is not None else []
    statuses = budget_status(
        key,
        team,
        ledger,
        client_id=client,
        team_client_ids=team_ids,
        pricing=pricing,
        fallback_per_1k=fallback,
    )
    exceeded = next((status for status in statuses if status.exceeded), None)
    if exceeded is not None:
        raise BatchItemRejected(
            budget_error(
                client_id=client,
                window=exceeded.window,
                spend=exceeded.spend,
                scope=exceeded.scope,
            )
        )
    if float(getattr(key, "user_daily_usd_cap", 0) or 0) > 0 and meta.user:
        user_err = user_daily_cap_exceeded(
            key,
            ledger,
            client_id=client,
            user_id=meta.user,
            pricing=pricing,
            fallback_per_1k=fallback,
        )
        if user_err is not None:
            raise BatchItemRejected(user_err)


def _governance_from_batch_request(request: Request, body: BatchCreateRequest) -> Any:
    """Snapshot authenticated identity + headers for every batch item (#441)."""
    from daari.gateway.agent_ua import sniff_agent_client_id
    from daari.gateway.batches import BatchGovernance
    from daari.server.auth import apply_auth_claims_to_meta

    headers = request.headers
    user_agent = headers.get("user-agent", "")
    client_id = headers.get("x-daari-client-id") or sniff_agent_client_id(user_agent)
    try:
        latency_raw = headers.get("x-daari-latency-budget")
        latency_budget_ms = int(latency_raw) if latency_raw else None
    except ValueError:
        latency_budget_ms = None
    from daari.router.deadline import parse_deadline_ms

    deadline_ms = parse_deadline_ms(headers.get("x-daari-deadline-ms"))
    meta = RequestMeta(
        tier_cap=headers.get("x-daari-tier-cap"),
        latency_budget_ms=latency_budget_ms,
        deadline_ms=deadline_ms,
        client_id=client_id,
        user_agent=user_agent[:200] or None,
        user=None,
        session_id=(headers.get("x-daari-session") or "").strip() or None,
        no_frontier=(headers.get("x-daari-no-frontier") or "").lower() == "true",
        boundary_profile=(headers.get("x-daari-boundary-profile") or "").strip() or None,
    )
    claims = getattr(request.state, "auth_claims", None)
    apply_auth_claims_to_meta(meta, claims)
    apply_profile_to_meta(meta, load_project_profile(headers.get("x-daari-project")))
    kind = getattr(claims, "kind", None) or "master"
    if kind not in {"master", "virtual"}:
        kind = "master"
    return BatchGovernance(
        key_id=getattr(claims, "key_id", None) if claims else None,
        client_id=meta.client_id,
        tier_cap=meta.tier_cap,
        no_frontier=bool(meta.no_frontier),
        user=meta.user,
        boundary_profile=meta.boundary_profile,
        kind=kind,
        latency_budget_ms=meta.latency_budget_ms,
        deadline_ms=meta.deadline_ms,
        session_id=meta.session_id,
        user_agent=meta.user_agent,
        team_id=getattr(meta, "team_id", None),
        cache_scope=getattr(meta, "cache_scope", None) or "global",
    )


def _ensure_file_store(ctx: AppContext) -> Any:
    """Return (and lazily attach) the Files API store (#442 / #465)."""
    store = getattr(ctx, "file_store", None)
    if store is not None:
        return store
    settings = ctx.settings
    pg_url = (settings.observability.postgres_url or "").strip()
    if getattr(settings.files, "backend", "sqlite") == "postgres" and pg_url:
        from daari.gateway.postgres_files import PostgresFileStore

        store = PostgresFileStore(
            pg_url,
            max_bytes=settings.files.max_bytes,
            retention_days=settings.files.retention_days,
            max_total_bytes=settings.files.max_total_bytes,
        )
    else:
        from daari.gateway.files import FileStore

        store = FileStore(
            settings.files_store_path,
            max_bytes=settings.files.max_bytes,
            retention_days=settings.files.retention_days,
            max_total_bytes=settings.files.max_total_bytes,
        )
    ctx.file_store = store
    return store


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


def _stats_team_rate_limits(request: Request) -> list[dict[str, Any]]:
    """Team rpm/tpm/rpd remaining for the dashboard. Empty when none are configured."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None or not hasattr(limiter, "team_rate_gauges"):
        return []
    ctx = getattr(request.app.state, "ctx", None)
    store = getattr(request.app.state, "virtual_key_store", None) or getattr(
        ctx, "virtual_key_store", None
    )
    list_teams = getattr(store, "list_teams", None)
    if not callable(list_teams):
        return []
    try:
        return list(limiter.team_rate_gauges(list_teams()) or [])
    except Exception:
        return []


def _stats_key_rate_limits(request: Request) -> list[dict[str, Any]]:
    """Per-key rpd remaining. Empty when no key opted into a day cap."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None or not hasattr(limiter, "key_rate_gauges"):
        return []
    ctx = getattr(request.app.state, "ctx", None)
    store = getattr(request.app.state, "virtual_key_store", None) or getattr(
        ctx, "virtual_key_store", None
    )
    list_keys = getattr(store, "list", None)
    if not callable(list_keys):
        return []
    try:
        return list(limiter.key_rate_gauges(list_keys()) or [])
    except Exception:
        return []


class OpenAIGatewayAdapter(GatewayAdapter):
    id = "openai"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/introspect")
        async def introspect(request: Request) -> dict[str, Any]:
            """RFC 7662 token introspection for master/virtual keys (#618)."""
            from daari.server.auth import extract_api_key, introspect_token, resolve_auth

            ctx: AppContext = request.app.state.ctx
            master = ctx.settings.server.api_key
            store = getattr(request.app.state, "virtual_key_store", None) or getattr(
                ctx, "virtual_key_store", None
            )
            caller = resolve_auth(
                extract_api_key(request.headers),
                master_key=master,
                store=store,
            )
            if caller is None or caller.kind not in ("master", "virtual"):
                raise HTTPException(status_code=401, detail="authentication required")

            token = ""
            content_type = (request.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                try:
                    body = await request.json()
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    token = str(body.get("token") or "")
            else:
                form = await request.form()
                token = str(form.get("token") or "")

            return introspect_token(token, master_key=master, store=store)

        @router.post("/v1/chat/completions", response_model=None)
        async def chat_completions(
            body: ChatCompletionRequest,
            request: Request,
            x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
            x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
            x_daari_tier_cap: str | None = Header(default=None, alias="X-Daari-Tier-Cap"),
            x_daari_no_frontier: str | None = Header(default=None, alias="X-Daari-No-Frontier"),
            x_daari_latency_budget: str | None = Header(
                default=None, alias="X-Daari-Latency-Budget"
            ),
            x_daari_deadline_ms: str | None = Header(default=None, alias="X-Daari-Deadline-Ms"),
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_session: str | None = Header(default=None, alias="X-Daari-Session"),
            x_daari_confirm_tool: str | None = Header(default=None, alias="X-Daari-Confirm-Tool"),
            x_daari_confirm: str | None = Header(default=None, alias="X-Daari-Confirm"),
            x_daari_rerun_command: str | None = Header(default=None, alias="X-Daari-ReRun-Command"),
            x_daari_meta: str | None = Header(default=None, alias="X-Daari-Meta"),
            x_daari_tools: str | None = Header(default=None, alias="X-Daari-Tools"),
            x_daari_project: str | None = Header(default=None, alias="X-Daari-Project"),
            x_daari_boundary_profile: str | None = Header(
                default=None, alias="X-Daari-Boundary-Profile"
            ),
        ) -> Any:
            confirm_value = (x_daari_confirm or x_daari_confirm_tool or "").strip().lower()
            confirm_tool = confirm_value in {"1", "true", "yes"}
            try:
                latency_budget_ms = int(x_daari_latency_budget) if x_daari_latency_budget else None
            except ValueError:
                latency_budget_ms = None
            from daari.router.deadline import parse_deadline_ms

            deadline_ms = parse_deadline_ms(x_daari_deadline_ms)
            include_daari_meta = (x_daari_meta or "").strip().lower() in {"1", "true", "yes"}
            include_usage = bool(body.stream_options and body.stream_options.get("include_usage"))
            client_host = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "")
            from daari.gateway.request_id import resolve_request_id

            request_id = getattr(request.state, "request_id", None) or resolve_request_id(
                request.headers
            )
            # T5b / #421: explicit header wins; otherwise attribute agent
            # traffic by user-agent so per-client reports and classify_user_turn
            # shortcuts work with zero config.
            from daari.gateway.agent_ua import sniff_agent_client_id

            client_id = x_daari_client_id or sniff_agent_client_id(user_agent)
            boundary_profile = (x_daari_boundary_profile or "").strip() or None
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
                    "request_id": request_id,
                },
            )

            ctx: AppContext = request.app.state.ctx
            meta = RequestMeta(
                no_cache=x_daari_no_cache == "true",
                tier_override=x_daari_tier_override,
                tier_cap=x_daari_tier_cap,
                latency_budget_ms=latency_budget_ms,
                deadline_ms=deadline_ms,
                client_id=client_id,
                user_agent=user_agent[:200] or None,
                user=(body.user or "").strip() or None,
                session_id=(x_daari_session or "").strip() or None,
                no_frontier=x_daari_no_frontier == "true",
                confirm_tool=confirm_tool,
                rerun_command=x_daari_rerun_command == "true",
                stream_include_usage=include_usage,
                boundary_profile=boundary_profile,
                request_id=request_id,
            )
            apply_cost_tier(body, meta)
            # Virtual-key defaults (issue #111); headers keep precedence.
            from daari.server.auth import apply_auth_claims_to_meta

            apply_auth_claims_to_meta(
                meta,
                getattr(request.state, "auth_claims", None),
                model_groups=getattr(ctx.settings, "model_groups", None),
            )
            from daari.gateway.model_access import reject_disallowed_model

            denied = reject_disallowed_model(request, body.model, ctx.settings, meta)
            if denied is not None:
                return denied
            # Per-project profile defaults (issue #91); headers keep precedence.
            apply_profile_to_meta(meta, load_project_profile(x_daari_project))
            # Per-end-user daily cap on shared virtual keys (#410). Checked here
            # (not middleware) because the OpenAI `user` field lives in the body.
            claims = getattr(request.state, "auth_claims", None)
            vk = getattr(claims, "virtual_key", None) if claims is not None else None
            if (
                vk is not None
                and float(getattr(vk, "user_daily_usd_cap", 0) or 0) > 0
                and meta.user
            ):
                from daari.auth.budgets import user_daily_cap_exceeded

                ledger = ctx.router.usage_ledger
                client = meta.client_id or getattr(claims, "key_id", None) or ""
                pricing = getattr(ctx.settings, "pricing", None)
                fallback = float(ctx.settings.usage.frontier_price_per_1k_tokens or 0.002)
                exceeded = (
                    user_daily_cap_exceeded(
                        vk,
                        ledger,
                        client_id=client,
                        user_id=meta.user,
                        pricing=pricing,
                        fallback_per_1k=fallback,
                    )
                    if ledger is not None
                    else None
                )
                if exceeded is not None:
                    return JSONResponse(status_code=402, content={"error": exceeded})
            internal = _prepare_internal_request(
                body,
                default_model=ctx.settings.models.l3,
                tools_mode=x_daari_tools,
                meta=meta,
            )
            from daari.gateway.transcriptions import inject_inline_audio_transcripts

            internal = await inject_inline_audio_transcripts(internal, ctx.settings)
            if internal.provider and internal.provider.zdr and ctx.settings.frontier.enabled:
                try:
                    require_zdr_slot(internal.provider, configured_frontier_slots(ctx.settings))
                except ZdrUnavailable as exc:
                    raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc

            from daari.gateway.idempotency import resolve_idempotency

            idem_kind, idem_response, idem_slot = await resolve_idempotency(
                request, ctx, body
            )
            if idem_kind in {"replay", "conflict"} and idem_response is not None:
                return idem_response

            if body.stream:
                try:
                    ctx.router.ensure_capable(internal)
                except UnsupportedCapability as exc:
                    if idem_slot is not None:
                        idem_slot.abandon()
                    raise HTTPException(status_code=422, detail=safe_detail(exc)) from exc

                outcome = StreamOutcome()

                async def event_stream() -> AsyncIterator[str]:
                    content_chars = 0
                    collected: list[str] = []
                    try:
                        async for chunk in stream_with_keepalive(
                            ctx.router.stream_openai_chunks(internal, outcome=outcome),
                            interval_seconds=ctx.settings.server.sse_keepalive_seconds,
                            idle_timeout_seconds=ctx.settings.server.stream_idle_timeout_seconds,
                            on_cancel=lambda: note_request_cancelled(
                                ctx.metrics, "stream", model=body.model
                            ),
                        ):
                            if '"delta": {"content":' in chunk or '"delta":{"content":' in chunk:
                                content_chars += 1
                            collected.append(chunk)
                            yield chunk
                    except Exception as exc:
                        err = f"data: {json.dumps({'error': f'stream failed: {safe_detail(exc)}'})}\n\n"
                        collected.append(err)
                        collected.append("data: [DONE]\n\n")
                        yield err
                        yield "data: [DONE]\n\n"
                    finally:
                        if idem_slot is not None:
                            from daari.gateway.idempotency import (
                                assemble_assistant_text_from_sse,
                            )

                            sse_text = "".join(collected)
                            idem_slot.complete(
                                status_code=200,
                                response_body=sse_text,
                                media_type="text/event-stream",
                                stream=True,
                                assistant_text=assemble_assistant_text_from_sse(sse_text),
                            )
                        log_gateway_event(
                            "chat_completions_stream_done",
                            {
                                "client": client_host,
                                "model": body.model,
                                "content_chunks": content_chars,
                            },
                        )

                return DeferredHeadersStreamingResponse(
                    event_stream(),
                    media_type="text/event-stream",
                    headers={**OPENAI_SSE_HEADERS, "X-Request-ID": request_id},
                    late_headers=outcome.headers,
                )

            try:
                result = await await_unless_disconnected(
                    request,
                    ctx.router.route(internal),
                    metrics=ctx.metrics,
                    phase="chat",
                    model=body.model,
                )
            except ClientDisconnected:
                if idem_slot is not None:
                    idem_slot.abandon()
                return JSONResponse(
                    status_code=499,
                    content={
                        "error": {
                            "type": "client_disconnected",
                            "message": "client disconnected.",
                        }
                    },
                )
            except ZdrUnavailable as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
            except RegionUnavailable as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
            except UnsupportedCapability as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                raise HTTPException(status_code=422, detail=safe_detail(exc)) from exc
            except BackendUnavailable as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                ctx.metrics.record_error()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "type": "backend_unavailable",
                            "message": backend_unavailable_message(exc),
                        }
                    },
                )
            except RequestDeadlineExceeded as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                return request_deadline_response(exc)
            except Exception as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=routing_failure_detail(exc)) from exc

            if internal.provider and result.daari_meta.provider_prefs is None:
                result.daari_meta.provider_prefs = as_openrouter_payload(internal.provider)
            if getattr(request.state, "request_quota_soft", False):
                # Soft request quota beats other soft warnings so agents back off (#498).
                result.daari_meta.warning = "request_quota_warning"
            elif getattr(request.state, "budget_soft", False):
                result.daari_meta.warning = "budget_warning"
            elif getattr(request.state, "rate_limit_soft", False):
                result.daari_meta.warning = "rate_limit_warning"
            prompt_chars = sum(len(message.content or "") for message in body.messages)
            payload = _openai_completion_body(
                body=body,
                result_content=result.content,
                result_model=result.model,
                daari_meta=result.daari_meta.model_dump(exclude_none=True),
                include_daari_meta=include_daari_meta,
                usage=response_token_usage(result, prompt_chars),
            )
            if idem_slot is not None:
                idem_slot.complete(
                    status_code=200,
                    response_body=json.dumps(payload, separators=(",", ":")),
                    media_type="application/json",
                    stream=False,
                    assistant_text=result.content,
                )
            return JSONResponse(
                payload,
                headers={
                    **response_cost_headers(
                        result.daari_meta,
                        ctx.settings,
                        prompt_chars=prompt_chars,
                        completion_chars=len(result.content or ""),
                        session_id=internal.meta.session_id,
                        savings=ctx.router.session_savings,
                    ),
                    "X-Request-ID": request_id,
                },
            )

        @router.post("/v1/audio/transcriptions", response_model=None)
        async def audio_transcriptions(
            request: Request,
            file: UploadFile = File(...),
            model: str = Form(default=""),
            language: str | None = Form(default=None),
            prompt: str | None = Form(default=None),
            response_format: str = Form(default="json"),
        ) -> Any:
            from daari.gateway.transcriptions import handle_transcription

            return await handle_transcription(
                request,
                file=file,
                model=model,
                language=language,
                prompt=prompt,
                response_format=response_format,
            )

        @router.post("/v1/audio/translations", response_model=None)
        async def audio_translations(
            request: Request,
            file: UploadFile = File(...),
            model: str = Form(default=""),
            prompt: str | None = Form(default=None),
            response_format: str = Form(default="json"),
        ) -> Any:
            from daari.gateway.transcriptions import handle_translation

            return await handle_translation(
                request,
                file=file,
                model=model,
                prompt=prompt,
                response_format=response_format,
            )

        @router.post("/v1/audio/speech", response_model=None)
        async def audio_speech(request: Request) -> Any:
            """OpenAI-compatible local TTS proxy (#847)."""
            from daari.gateway.speech import handle_speech

            try:
                body = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "type": "invalid_request_error",
                            "message": "request body must be JSON",
                        }
                    },
                )
            if not isinstance(body, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "type": "invalid_request_error",
                            "message": "request body must be a JSON object",
                        }
                    },
                )
            return await handle_speech(
                request,
                model=str(body.get("model") or ""),
                input_text=str(body.get("input") or ""),
                voice=(str(body["voice"]) if body.get("voice") is not None else None),
                response_format=str(body.get("response_format") or "mp3"),
            )

        @router.post("/v1/moderations", response_model=None)
        async def moderations(body: dict[str, Any], request: Request) -> Any:
            """OpenAI-shaped moderations via configured L6 (#1050)."""
            from daari.gateway.moderations import ModerationsRequest, handle_moderations

            parsed = ModerationsRequest.model_validate(body)
            return await handle_moderations(request, parsed)

        @router.post("/v1/embeddings")
        async def embeddings(
            body: EmbeddingsRequest,
            request: Request,
            x_daari_deadline_ms: str | None = Header(default=None, alias="X-Daari-Deadline-Ms"),
        ) -> Any:
            ctx: AppContext = request.app.state.ctx
            from daari.gateway.model_access import reject_disallowed_model
            from daari.router.deadline import (
                RequestDeadlineExceeded,
                bind_request_deadline,
                deadline_active,
                guard_upstream,
                parse_deadline_ms,
                resolve_deadline_seconds,
            )

            denied = reject_disallowed_model(request, body.model or "daari", ctx.settings)
            if denied is not None:
                return denied
            model = resolve_embedding_model(ctx, body.model)
            texts = embedding_texts(body.input)
            deadline_ms = parse_deadline_ms(x_daari_deadline_ms)
            seconds = resolve_deadline_seconds(
                deadline_ms,
                getattr(ctx.settings.upstream, "request_deadline_seconds", None),
            )

            async def _run() -> Any:
                if deadline_active():
                    guard_upstream("embed")
                try:
                    vectors = await await_unless_disconnected(
                        request,
                        compute_embeddings(ctx, texts, model=model, request=request),
                        metrics=ctx.metrics,
                        phase="embed",
                        model=model,
                    )
                except ClientDisconnected:
                    return JSONResponse(
                        status_code=499,
                        content={
                            "error": {
                                "type": "client_disconnected",
                                "message": "client disconnected.",
                            }
                        },
                    )
                return openai_embeddings_payload(model, vectors, texts)

            try:
                if seconds is not None and not deadline_active():
                    with bind_request_deadline(seconds, metrics=ctx.metrics):
                        return await _run()
                return await _run()
            except RequestDeadlineExceeded as exc:
                return request_deadline_response(exc)

        @router.get("/v1/models")
        async def list_models(request: Request) -> dict[str, Any]:
            from daari.gateway.anthropic import wants_anthropic_models
            from daari.router.capabilities import anthropic_models_payload, openai_model_cards

            ctx: AppContext = request.app.state.ctx
            # Claude Code / Desktop send anthropic-version and/or x-api-key (#454).
            if wants_anthropic_models(request):
                return anthropic_models_payload(ctx.settings)
            return {"object": "list", "data": openai_model_cards(ctx.settings)}

        @router.get("/v1/models/{model_id}")
        async def retrieve_model(model_id: str, request: Request) -> dict[str, Any]:
            from daari.router.capabilities import openai_model_cards

            ctx: AppContext = request.app.state.ctx
            for card in openai_model_cards(ctx.settings):
                if card["id"] == model_id:
                    return card
            return {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "daari" if model_id == "daari" else "ollama",
                "capabilities": [],
            }

        @router.get("/health")
        async def health() -> dict[str, str]:
            from daari import __version__

            return {"status": "ok", "version": __version__}

        @router.get("/metrics")
        async def prometheus_metrics(request: Request):
            """Prometheus exposition (issue #107). Disabled via
            observability.prometheus=false. Auth follows server.api_key —
            open when unset, required otherwise (middleware). Optional
            observability.metrics_port serves the same body without auth (#594)."""
            from fastapi.responses import PlainTextResponse

            from daari.observability.metrics_listen import prometheus_text_for_app

            body = prometheus_text_for_app(request.app)
            if body is None:
                raise HTTPException(status_code=404, detail="prometheus metrics disabled")
            return PlainTextResponse(
                content=body,
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

        @router.get("/ready")
        async def ready(request: Request) -> JSONResponse:
            """Readiness probe (issue #105 / #170): cache handles plus local
            pool health. Degraded (some hosts down) is 200; no serving host
            is 503. When ``cache.backend=redis``, also probe Redis — down with
            rate-limit fallback active is degraded-but-200 (#463)."""
            ctx: AppContext = request.app.state.ctx
            cache_ok = ctx.cache is not None
            pool = getattr(ctx, "local_pool", None) or getattr(ctx.router, "local_pool", None)
            backends: list[dict[str, Any]] = []
            if pool is not None:
                if not pool.checked:
                    await pool.check_health()
                snap = pool.readiness()
                model_backend = snap["model_backend"]
                backends = snap["backends"]
                status = snap["status"] if cache_ok else "not_ready"
                http_status = snap["http_status"] if cache_ok else 503
            else:
                base_url = ctx.ollama_l3.base_url.rstrip("/")
                probe = (
                    f"{base_url}/v1/models"
                    if type(ctx.ollama_l3).__name__ == "MLXExecutor"
                    else f"{base_url}/api/version"
                )
                model_backend = await check_model_backend(probe)
                ready_now = cache_ok and model_backend == "ok"
                status = "ready" if ready_now else "not_ready"
                http_status = 200 if ready_now else 503
            checks = {
                "cache": "ok" if cache_ok else "missing",
                "model_backend": model_backend,
            }
            if getattr(ctx.settings.cache, "backend", "disk") == "redis":
                limiter = getattr(request.app.state, "rate_limiter", None)
                if limiter is not None and hasattr(limiter, "probe_redis"):
                    redis_check = await asyncio.to_thread(limiter.probe_redis)
                else:
                    redis_check = await asyncio.to_thread(
                        _probe_redis_url,
                        getattr(ctx.settings.cache, "redis_url", ""),
                        float(getattr(ctx.settings.cache, "redis_timeout_seconds", 2.0) or 2.0),
                    )
                checks["redis"] = redis_check
                if redis_check != "ok" and http_status == 200 and status == "ready":
                    status = "degraded"
            content: dict[str, Any] = {"status": status, "checks": checks}
            if backends:
                content["backends"] = backends
            return JSONResponse(status_code=http_status, content=content)

        @router.get("/v1/daari/route/preview")
        async def daari_route_preview_get(
            request: Request,
            prompt: str = "",
            model: str | None = None,
        ) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            text = (prompt or "").strip() or "hi"
            internal = InternalRequest(
                messages=[Message(role="user", content=text)],
                model=model or ctx.settings.models.l3,
            )
            return ctx.router.preview_initial_tier(internal)

        @router.post("/v1/daari/route/preview")
        async def daari_route_preview_post(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            payload = {}
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if payload.get("messages"):
                body = ChatCompletionRequest.model_validate(
                    {
                        "model": payload.get("model") or ctx.settings.models.l3,
                        "messages": payload["messages"],
                    }
                )
                internal = _prepare_internal_request(
                    body,
                    default_model=ctx.settings.models.l3,
                    meta=RequestMeta(),
                )
            else:
                text = str(payload.get("prompt") or "hi").strip() or "hi"
                internal = InternalRequest(
                    messages=[Message(role="user", content=text)],
                    model=str(payload.get("model") or ctx.settings.models.l3),
                )
            return ctx.router.preview_initial_tier(internal)

        @router.get("/v1/daari/stats")
        async def daari_stats(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_role(request, ctx, "analyst")
            from daari.observability.metrics import histogram_percentile_ms

            full = ctx.metrics.snapshot(include_histograms=True)
            tiers = {}
            for tier, stats in full["tiers"].items():
                count = int(stats["count"])
                buckets = stats.get("latency_buckets") or {}
                entry: dict[str, Any] = {
                    "count": count,
                    "cache_hits": stats["cache_hits"],
                    "avg_latency_ms": stats["avg_latency_ms"],
                }
                p50 = histogram_percentile_ms(buckets, count=count, percentile=0.50)
                p95 = histogram_percentile_ms(buckets, count=count, percentile=0.95)
                if p50 is not None and p50 != float("inf"):
                    entry["p50_ms"] = float(p50)
                if p95 is not None and p95 != float("inf"):
                    entry["p95_ms"] = float(p95)
                tiers[tier] = entry
            total = sum(t["count"] for t in tiers.values())
            pool = getattr(ctx, "local_pool", None) or getattr(ctx.router, "local_pool", None)
            backends = list((pool.snapshot() if pool is not None else {}).get("backends") or [])
            healthy = sum(1 for b in backends if b.get("healthy") is True)
            open_circuit = sum(1 for b in backends if b.get("circuit") == "open")
            backend_summary = {
                "total": len(backends),
                "healthy": healthy,
                "unhealthy": len(backends) - healthy,
                "open_circuit": open_circuit,
            }
            mcp_tasks: dict[str, int] = {}
            store = getattr(ctx, "mcp_task_store", None)
            if store is not None and hasattr(store, "snapshot"):
                try:
                    mcp_tasks = dict(store.snapshot() or {})
                except Exception:
                    mcp_tasks = {}
            return {
                "total_requests": total,
                "errors": full["errors"],
                "tiers": tiers,
                "backends": backends,
                "backend_summary": backend_summary,
                "soft_warnings": full.get("soft_warnings") or {},
                "rejects": full.get("rejects") or {},
                "team_rate_limits": _stats_team_rate_limits(request),
                "key_rate_limits": _stats_key_rate_limits(request),
                "mcp_tool_calls": full.get("mcp_tool_calls") or {},
                "mcp_tasks": mcp_tasks,
            }

        @router.get("/v1/daari/traces")
        async def daari_traces(request: Request, limit: int = 20) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_role(request, ctx, "analyst")
            store = ctx.router.trace_store
            if store is None:
                raise HTTPException(status_code=404, detail="trace store is not configured")
            return {"traces": store.list(limit=max(1, min(limit, 200)))}

        @router.get("/v1/daari/traces/{trace_id}")
        async def daari_trace_detail(trace_id: str, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_role(request, ctx, "analyst")
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
            _require_role(request, ctx, "analyst")
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
            by_user = getattr(ledger, "by_user", None)
            payload["users"] = (
                by_user(
                    days=max(1, days),
                    frontier_price_per_1k_tokens=ctx.settings.usage.frontier_price_per_1k_tokens,
                )
                if callable(by_user)
                else []
            )
            store = getattr(request.app.state, "virtual_key_store", None)
            if store is not None and getattr(store, "report_by_team", None):
                payload["teams"] = store.report_by_team(payload["clients"])
            else:
                payload["teams"] = []
            from daari.auth.budgets import request_quota_report_rows

            payload["request_quotas"] = request_quota_report_rows(
                store,
                ledger,
                soft_ratio=float(ctx.settings.frontier.soft_budget_ratio or 0.0),
                pricing=getattr(ctx.settings, "pricing", None),
                fallback_per_1k=float(
                    getattr(ctx.settings.usage, "frontier_price_per_1k_tokens", 0.002) or 0.002
                ),
            )
            # Trust PRD T1d: false-hit rates + answer diversity per category.
            trust: dict[str, Any] = {}
            feedback = ctx.router.feedback_store
            payload["tier_divergence"] = {}
            if feedback is not None:
                try:
                    trust["false_hit_rates"] = feedback.shadow_stats(days=max(1, days))
                except Exception:
                    trust["false_hit_rates"] = {}
                # #318: per-category tier divergence from shadow replays.
                try:
                    payload["tier_divergence"] = feedback.tier_shadow_stats(days=max(1, days))
                except Exception:
                    pass
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
            try:
                tier_shadow = store.tier_shadow_stats(days=max(1, days))
            except Exception:
                tier_shadow = {}
            return {
                "days": max(1, days),
                "categories": store.stats(days=max(1, days)),
                "shadow": shadow,
                "tier_shadow": tier_shadow,
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
                raise HTTPException(status_code=422, detail=safe_detail(exc)) from exc
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
            _require_admin_role(request, ctx)
            payload = ctx.reload_cache_handles()
            return {"status": "ok", **payload}

        @router.post("/v1/daari/cache/invalidate")
        async def daari_cache_invalidate(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_admin_role(request, ctx)
            raw = await request.body()
            payload: dict[str, Any] = {}
            if raw:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise HTTPException(status_code=400, detail="invalid json") from exc
                if not isinstance(parsed, dict):
                    raise HTTPException(status_code=422, detail="JSON object required")
                payload = parsed
            model = payload.get("model")
            entry_hash = payload.get("hash")
            team_id = payload.get("team_id")
            key_id = payload.get("key_id")
            if model is not None and not isinstance(model, str):
                raise HTTPException(status_code=422, detail="model must be a string")
            if entry_hash is not None and not isinstance(entry_hash, str):
                raise HTTPException(status_code=422, detail="hash must be a string")
            if team_id is not None and not isinstance(team_id, str):
                raise HTTPException(status_code=422, detail="team_id must be a string")
            if key_id is not None and not isinstance(key_id, str):
                raise HTTPException(status_code=422, detail="key_id must be a string")
            model_s = model.strip() if isinstance(model, str) and model.strip() else None
            hash_s = entry_hash.strip() if isinstance(entry_hash, str) and entry_hash.strip() else None
            team_s = team_id.strip() if isinstance(team_id, str) and team_id.strip() else None
            key_s = key_id.strip() if isinstance(key_id, str) and key_id.strip() else None
            l0 = getattr(ctx.router, "cache", None)
            l1 = getattr(ctx.router, "semantic_cache", None)
            l0_removed = (
                int(
                    l0.invalidate(
                        model=model_s, entry_hash=hash_s, team_id=team_s, key_id=key_s
                    )
                )
                if l0 is not None and hasattr(l0, "invalidate")
                else 0
            )
            l1_removed = (
                int(
                    l1.invalidate(
                        model=model_s, entry_hash=hash_s, team_id=team_s, key_id=key_s
                    )
                )
                if l1 is not None and hasattr(l1, "invalidate")
                else 0
            )
            log_gateway_event(
                "cache_invalidate",
                {
                    "model": model_s or "",
                    "hash": hash_s or "",
                    "team_id": team_s or "",
                    "key_id": key_s or "",
                    "l0_removed": l0_removed,
                    "l1_removed": l1_removed,
                },
            )
            return {
                "l0_removed": l0_removed,
                "l1_removed": l1_removed,
                "removed": l0_removed + l1_removed,
            }

        def _require_config_editor(ctx: AppContext) -> None:
            if not ctx.settings.observability.config_editor:
                raise HTTPException(status_code=404, detail="config editor disabled")

        def _require_role(request: Request, ctx: AppContext, minimum: str) -> str:
            """SSO role gate for admin/ops surfaces when enterprise.sso.enabled."""
            sso = ctx.settings.enterprise.sso
            oidc_ready = bool(
                sso.jwks_url.strip()
                or any(str(u or "").strip() for u in (sso.jwks_urls or []))
                or sso.discovery_url.strip()
            )
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
            from daari.server.auth import master_key_matches

            master_keys = ctx.settings.server.master_keys()
            if master_key_matches(token, master_keys):
                return "admin"
            try:
                claims = verify_access_token(token, sso)
            except Exception as exc:  # noqa: BLE001 — surface auth failures as 401
                raise HTTPException(status_code=401, detail=safe_detail(exc)) from exc
            role = role_from_claims(claims, role_claim=sso.role_claim)
            if not role_at_least(role, minimum):
                raise HTTPException(status_code=403, detail="insufficient role")
            request.state.sso_claims = claims
            return role

        def _require_admin_role(request: Request, ctx: AppContext) -> str:
            """Require enterprise.sso.admin_min_role (default admin) when SSO is on."""
            return _require_role(request, ctx, ctx.settings.enterprise.sso.admin_min_role)

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
                raise HTTPException(status_code=401, detail=safe_detail(exc)) from exc
            subject = str(claims.get("sub") or "")
            role = role_from_claims(claims, role_claim=sso.role_claim)
            result: dict[str, Any] = {
                "sub": subject,
                "role": role,
                "issuer": claims.get("iss"),
            }
            if sso.mint_virtual_key_on_login and subject:
                from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings
                from daari.enterprise.postgres_audit import audit_log_from_settings
                from daari.enterprise.sso_keys import UnmappedSsoPolicy, sync_sso_virtual_key

                store = getattr(request.app.state, "virtual_key_store", None) or getattr(
                    ctx, "virtual_key_store", None
                )
                if store is None:
                    store = virtual_key_store_from_settings(ctx.settings)
                try:
                    minted = sync_sso_virtual_key(
                        store,
                        subject=subject,
                        claims=claims,
                        sso=sso,
                        audit=audit_log_from_settings(ctx.settings),
                        role=role,
                    )
                except UnmappedSsoPolicy as exc:
                    raise HTTPException(status_code=403, detail=safe_detail(exc)) from exc
                result.update(minted)
            return result

        @router.get("/v1/daari/config")
        async def daari_config_get(request: Request) -> dict[str, Any]:
            """Safe config subset for the web UI editor (issue #115)."""
            ctx: AppContext = request.app.state.ctx
            _require_config_editor(ctx)
            _require_role(request, ctx, "analyst")
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
                raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
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
                ctx.router.semantic_cache.similarity_threshold = cache["l1_similarity_threshold"]
            if new_boundaries is not None:
                from daari.gateway.boundaries import (
                    copy_runtime_hooks,
                    default_local_judge,
                    engine_from_settings,
                )

                prev = ctx.router.boundaries
                ctx.settings.boundaries = new_boundaries
                ctx.router.boundaries = engine_from_settings(
                    ctx.settings, judge=default_local_judge
                )
                copy_runtime_hooks(ctx.router.boundaries, prev)
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
            from daari.enterprise.postgres_audit import audit_log_from_settings

            audit_log_from_settings(ctx.settings).record(
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
            _require_role(request, ctx, "analyst")
            from daari.enterprise.postgres_audit import audit_log_from_settings

            entries = audit_log_from_settings(ctx.settings).list(limit=100)
            return {"entries": entries}

        @router.post("/v1/org-learning/sync")
        async def org_learning_sync(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _require_admin_role(request, ctx)
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

        @router.post("/v1/files")
        async def upload_file(
            request: Request,
            file: UploadFile = File(...),
            purpose: str = Form(default="batch"),
            expires_after: str | None = Form(default=None),
        ) -> dict[str, Any]:
            from daari.gateway.files import FileStoreFull

            ctx: AppContext = request.app.state.ctx
            store = _ensure_file_store(ctx)
            raw = await file.read()
            claims = getattr(request.state, "auth_claims", None)
            owner_key_id = (
                getattr(claims, "key_id", None)
                if getattr(claims, "kind", None) == "virtual"
                else None
            )
            try:
                stored = store.create(
                    content=raw,
                    filename=file.filename or "upload",
                    purpose=purpose or "batch",
                    owner_key_id=owner_key_id,
                    expires_after=expires_after,
                )
            except FileStoreFull as exc:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error": {
                            "message": str(exc),
                            "type": "invalid_request_error",
                            "code": "files_store_full",
                            "max_total_bytes": exc.max_total_bytes,
                            "current_bytes": exc.current_bytes,
                            "upload_bytes": exc.incoming_bytes,
                        }
                    },
                ) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            log_gateway_event(
                "file.uploaded",
                {"file_id": stored.id, "bytes": stored.bytes, "purpose": stored.purpose},
            )
            return stored.as_public()

        @router.get("/v1/files")
        async def list_files(
            request: Request,
            purpose: str | None = None,
            limit: int = 10000,
        ) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.file_store
            if store is None:
                return {"object": "list", "data": [], "has_more": False}
            claims = getattr(request.state, "auth_claims", None)
            owner_filter = (
                getattr(claims, "key_id", None)
                if getattr(claims, "kind", None) == "virtual"
                else None
            )
            # Virtual keys pass owner_key_id so limit applies within their scope.
            # Master / no-auth leave owner_filter None and see every file.
            data = [
                item.as_public()
                for item in store.list_files(
                    purpose=purpose,
                    limit=limit,
                    owner_key_id=owner_filter,
                )
            ]
            return {"object": "list", "data": data, "has_more": False}

        @router.get("/v1/files/{file_id}")
        async def retrieve_file(file_id: str, request: Request) -> dict[str, Any]:
            from daari.enterprise.audit import maybe_audit_tenancy_denied
            from daari.gateway.files import file_visible_to_caller

            ctx: AppContext = request.app.state.ctx
            store = ctx.file_store
            stored = store.get(file_id) if store is not None else None
            claims = getattr(request.state, "auth_claims", None)
            visible = stored is not None and file_visible_to_caller(stored, claims)
            maybe_audit_tenancy_denied(
                ctx.settings,
                claims=claims,
                kind="file",
                artifact_id=file_id,
                stored=stored,
                visible=visible,
            )
            if stored is None or not visible:
                raise HTTPException(status_code=404, detail="file not found")
            return stored.as_public()

        @router.get("/v1/files/{file_id}/content")
        async def download_file_content(file_id: str, request: Request) -> Response:
            from daari.enterprise.audit import maybe_audit_tenancy_denied
            from daari.gateway.files import file_visible_to_caller

            ctx: AppContext = request.app.state.ctx
            store = ctx.file_store
            stored = store.get(file_id) if store is not None else None
            claims = getattr(request.state, "auth_claims", None)
            visible = stored is not None and file_visible_to_caller(stored, claims)
            maybe_audit_tenancy_denied(
                ctx.settings,
                claims=claims,
                kind="file",
                artifact_id=file_id,
                stored=stored,
                visible=visible,
            )
            if stored is None or not visible:
                raise HTTPException(status_code=404, detail="file not found")
            raw = store.read_bytes(file_id) if store is not None else None
            if raw is None:
                raise HTTPException(status_code=404, detail="file not found")
            filename = stored.filename if stored is not None else file_id
            return Response(
                content=raw,
                media_type="application/jsonl",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

        @router.delete("/v1/files/{file_id}")
        async def delete_file(file_id: str, request: Request) -> dict[str, Any]:
            from daari.enterprise.audit import maybe_audit_tenancy_denied
            from daari.gateway.files import file_visible_to_caller

            ctx: AppContext = request.app.state.ctx
            store = ctx.file_store
            stored = store.get(file_id) if store is not None else None
            claims = getattr(request.state, "auth_claims", None)
            visible = (
                store is not None and stored is not None and file_visible_to_caller(stored, claims)
            )
            maybe_audit_tenancy_denied(
                ctx.settings,
                claims=claims,
                kind="file",
                artifact_id=file_id,
                stored=stored,
                visible=visible,
            )
            if store is None or stored is None or not visible:
                raise HTTPException(status_code=404, detail="file not found")
            if not store.delete(file_id):
                raise HTTPException(status_code=404, detail="file not found")
            return {"id": file_id, "object": "file", "deleted": True}

        @router.post("/v1/batches")
        async def create_batch(body: BatchCreateRequest, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.batch_store
            if store is None:
                settings = ctx.settings
                pg_url = (settings.observability.postgres_url or "").strip()
                file_store = _ensure_file_store(ctx) if settings.files.enabled else None
                if (
                    settings.batches.enabled
                    and getattr(settings.batches, "backend", "sqlite") == "postgres"
                    and pg_url
                ):
                    from daari.gateway.postgres_batches import PostgresBatchStore

                    store = PostgresBatchStore(
                        pg_url,
                        file_store=file_store,
                        yield_to_interactive=settings.batches.yield_to_interactive,
                        idle_poll_seconds=settings.batches.idle_poll_seconds,
                        claim_ttl_seconds=int(
                            getattr(settings.batches, "claim_ttl_seconds", 90) or 90
                        ),
                    )
                else:
                    from daari.gateway.batches import BatchStore

                    batch_path = settings.batches_store_path if settings.batches.enabled else None
                    store = BatchStore(
                        file_store=file_store,
                        path=batch_path,
                        yield_to_interactive=settings.batches.yield_to_interactive,
                        idle_poll_seconds=settings.batches.idle_poll_seconds,
                    )
                ctx.batch_store = store
            elif store.file_store is None and ctx.file_store is not None:
                store.file_store = ctx.file_store
            try:
                job = store.create(
                    endpoint=body.endpoint,
                    completion_window=body.completion_window,
                    input_file_id=body.input_file_id,
                    requests=body.requests,
                    metadata=body.metadata,
                    governance=_governance_from_batch_request(request, body),
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            governance = job.governance

            async def execute_one(item_body: dict[str, Any]) -> dict[str, Any]:
                return await _execute_batch_chat_body(
                    ctx,
                    item_body,
                    governance=governance,
                    rate_limiter=getattr(request.app.state, "rate_limiter", None),
                )

            store.schedule(job.id, execute_one)
            return store.as_public(job)

        @router.get("/v1/batches")
        async def list_batches(request: Request, limit: int = 100) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store = ctx.batch_store
            if store is None:
                return {
                    "object": "list",
                    "data": [],
                    "first_id": None,
                    "last_id": None,
                    "has_more": False,
                }
            claims = getattr(request.state, "auth_claims", None)
            owner_filter = (
                getattr(claims, "key_id", None)
                if getattr(claims, "kind", None) == "virtual"
                else None
            )
            jobs = store.list_batches(limit=limit, owner_key_id=owner_filter)
            data = [store.as_public(job) for job in jobs]
            return {
                "object": "list",
                "data": data,
                "first_id": data[0]["id"] if data else None,
                "last_id": data[-1]["id"] if data else None,
                "has_more": False,
            }

        @router.get("/v1/batches/{batch_id}")
        async def retrieve_batch(batch_id: str, request: Request) -> dict[str, Any]:
            from daari.enterprise.audit import maybe_audit_tenancy_denied
            from daari.gateway.batches import batch_visible_to_caller

            ctx: AppContext = request.app.state.ctx
            store = ctx.batch_store
            job = store.get(batch_id) if store is not None else None
            claims = getattr(request.state, "auth_claims", None)
            visible = job is not None and batch_visible_to_caller(job, claims)
            maybe_audit_tenancy_denied(
                ctx.settings,
                claims=claims,
                kind="batch",
                artifact_id=batch_id,
                stored=job,
                visible=visible,
            )
            if job is None or not visible:
                raise HTTPException(status_code=404, detail="batch not found")
            return store.as_public(job)

        @router.post("/v1/batches/{batch_id}/cancel")
        async def cancel_batch(batch_id: str, request: Request) -> dict[str, Any]:
            from daari.enterprise.audit import maybe_audit_tenancy_denied
            from daari.gateway.batches import batch_visible_to_caller

            ctx: AppContext = request.app.state.ctx
            store = ctx.batch_store
            if store is None:
                raise HTTPException(status_code=404, detail="batch not found")
            job = store.get(batch_id)
            claims = getattr(request.state, "auth_claims", None)
            visible = job is not None and batch_visible_to_caller(job, claims)
            maybe_audit_tenancy_denied(
                ctx.settings,
                claims=claims,
                kind="batch",
                artifact_id=batch_id,
                stored=job,
                visible=visible,
            )
            if job is None or not visible:
                raise HTTPException(status_code=404, detail="batch not found")
            cancelled = store.cancel(batch_id)
            if cancelled is None:
                raise HTTPException(status_code=404, detail="batch not found")
            return store.as_public(cancelled)

        return router


def _probe_redis_url(redis_url: str, timeout_seconds: float = 2.0) -> str:
    """Best-effort Redis PING for /ready when no rate limiter is wired."""
    if not redis_url:
        return "missing_url"
    try:
        from daari.cache.redis_client import connect_redis

        client = connect_redis(redis_url, timeout_seconds=timeout_seconds)
        client.ping()
        return "ok"
    except Exception as exc:
        return type(exc).__name__


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
