from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx

from daari.cache.command_context import CommandContextStore
from daari.cache.exact import ExactCache
from daari.cache.semantic import OllamaEmbedder, SemanticCache
from daari.config.settings import Settings
from daari.enterprise.cache import resolve_org_scoped_path
from daari.enterprise.client import OrgCacheClient, OrgLearningClient, OrgLearningFeedback
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.policy.engine import PolicyEngine
from daari.providers.integrations import GitHubEnterpriseProvider, GitLabProvider, SourcegraphProvider
from daari.providers.registry import ProviderRegistry
from daari.rules.dev_commands import DevCommandMatch, match_dev_command
from daari.rules.engine import apply_l2_rules
from daari.router.confidence import score_l3_confidence
from daari.router.frontier import FrontierExecutor
from daari.tools.shell import ShellExecutor


def _openai_tool_call_deltas(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Convert Ollama-native tool calls (dict arguments, no id) to OpenAI delta shape."""
    deltas: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {})
        deltas.append(
            {
                "index": index,
                "id": call.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": function.get("name", ""), "arguments": arguments},
            }
        )
    return deltas


@dataclass
class OllamaExecutor:
    base_url: str
    default_model: str
    tier: str = "L3"
    timeout: float = 120.0

    async def execute(self, request: InternalRequest) -> InternalResponse:
        model = request.model or self.default_model
        started = time.perf_counter()
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": False,
        }
        if request.tools:
            payload["tools"] = request.tools
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return InternalResponse(
            content=content,
            model=model,
            daari_meta=DaariMeta(
                tier=self.tier,
                cache_hit=False,
                executor="ollama",
                provider_id=f"ollama:{self.tier.lower()}",
                latency_ms=latency_ms,
                model=model,
            ),
        )

    async def stream(self, request: InternalRequest) -> AsyncIterator[dict]:
        model = request.model or self.default_model
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    yield json.loads(line)


@dataclass
class CallableProvider:
    id: str
    tier: str
    execute_fn: Callable[[InternalRequest], Awaitable[InternalResponse]]

    async def health(self) -> bool:
        return True

    async def execute(self, request: InternalRequest) -> InternalResponse:
        return await self.execute_fn(request)


class Router:
    def __init__(
        self,
        cache: ExactCache,
        semantic_cache: SemanticCache,
        metrics: Metrics,
        ollama_l3: OllamaExecutor | None = None,
        ollama_l4: OllamaExecutor | None = None,
        ollama_l5: OllamaExecutor | None = None,
        ollama: OllamaExecutor | None = None,
        frontier: FrontierExecutor | None = None,
        command_context: CommandContextStore | None = None,
        shell_executor: ShellExecutor | None = None,
        policy: PolicyEngine | None = None,
        provider_registry: ProviderRegistry | None = None,
        model_preference: str = "balanced",
        model_weights: dict[str, dict[str, float]] | None = None,
        integration_triggers: dict[str, list[str]] | None = None,
        skills_system_prefix: str = "",
        org_cache_client: OrgCacheClient | None = None,
        org_learning_client: OrgLearningClient | None = None,
        org_learning_enabled: bool = False,
        *,
        frontier_enabled: bool = False,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.cache = cache
        self.semantic_cache = semantic_cache
        self.ollama_l3 = ollama_l3 or ollama or OllamaExecutor(
            base_url="http://127.0.0.1:11434",
            default_model="llama3.2:3b",
            tier="L3",
        )
        self.ollama_l4 = ollama_l4 or ollama_l3 or ollama or OllamaExecutor(
            base_url=self.ollama_l3.base_url,
            default_model=self.ollama_l3.default_model,
            tier="L4",
        )
        self.ollama_l5 = ollama_l5 or ollama_l4 or ollama_l3 or ollama or OllamaExecutor(
            base_url=self.ollama_l3.base_url,
            default_model=self.ollama_l4.default_model,
            tier="L5",
        )
        self.metrics = metrics
        self.frontier = frontier
        self.command_context = command_context
        self.shell_executor = shell_executor or ShellExecutor()
        self.policy = policy or PolicyEngine()
        self.provider_registry = provider_registry or ProviderRegistry()
        self.model_preference = model_preference
        self.model_weights = model_weights or {}
        self.integration_triggers = integration_triggers or {}
        self.skills_system_prefix = skills_system_prefix.strip()
        self.org_cache_client = org_cache_client
        self.org_learning_client = org_learning_client
        self.org_learning_enabled = org_learning_enabled
        self.frontier_enabled = frontier_enabled
        self.confidence_threshold = confidence_threshold

    @property
    def ollama(self) -> OllamaExecutor:
        return self.ollama_l3

    async def route(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()
        request = self._with_skills_prefix(request)
        last_user = self._last_user_text(request.messages)

        if request.has_tool_calls_in_history:
            response = await self._run_model_tier("L3", request)
            self._record(response, started)
            return response

        dev_match = match_dev_command(last_user)

        if not request.meta.no_cache:
            try:
                cached = self.cache.get(request)
            except Exception:
                cached = None
            if cached is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                cached.daari_meta.tier = "L0"
                cached.daari_meta.cache_hit = True
                cached.daari_meta.executor = "cache"
                cached.daari_meta.provider_id = "cache"
                cached.daari_meta.latency_ms = latency_ms
                self.metrics.record("L0", cache_hit=True, latency_ms=latency_ms)
                self._emit_org_feedback(last_user, cached)
                return cached
            if self.org_cache_client is not None:
                org_l0_hit = await self.org_cache_client.get_l0(request)
                if org_l0_hit is not None:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    org_l0_hit.daari_meta.tier = "L0-org"
                    org_l0_hit.daari_meta.cache_hit = True
                    org_l0_hit.daari_meta.executor = "cache"
                    org_l0_hit.daari_meta.provider_id = "org-cache"
                    org_l0_hit.daari_meta.latency_ms = latency_ms
                    self.metrics.record("L0-org", cache_hit=True, latency_ms=latency_ms)
                    self._emit_org_feedback(last_user, org_l0_hit)
                    return org_l0_hit

        ccs_hit = self._resolve_ccs_hit(dev_match, request)
        if ccs_hit is not None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            ccs_hit.daari_meta.latency_ms = latency_ms
            self.metrics.record("CCS", cache_hit=True, latency_ms=latency_ms)
            self._emit_org_feedback(last_user, ccs_hit)
            return ccs_hit

        if not request.meta.no_cache:
            try:
                semantic_hit, _similarity = await self.semantic_cache.get(request)
            except Exception:
                semantic_hit = None
            if semantic_hit is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                semantic_hit.daari_meta.tier = "L1"
                semantic_hit.daari_meta.cache_hit = True
                semantic_hit.daari_meta.executor = "cache"
                semantic_hit.daari_meta.provider_id = "cache"
                semantic_hit.daari_meta.latency_ms = latency_ms
                semantic_hit.daari_meta.task_type = "cache_hit"
                self.metrics.record("L1", cache_hit=True, latency_ms=latency_ms)
                self._emit_org_feedback(last_user, semantic_hit)
                return semantic_hit
            if self.org_cache_client is not None:
                org_l1_hit = await self.org_cache_client.get_l1(request)
                if org_l1_hit is not None:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    org_l1_hit.daari_meta.tier = "L1-org"
                    org_l1_hit.daari_meta.cache_hit = True
                    org_l1_hit.daari_meta.executor = "cache"
                    org_l1_hit.daari_meta.provider_id = "org-cache"
                    org_l1_hit.daari_meta.latency_ms = latency_ms
                    org_l1_hit.daari_meta.task_type = "cache_hit"
                    self.metrics.record("L1-org", cache_hit=True, latency_ms=latency_ms)
                    self._emit_org_feedback(last_user, org_l1_hit)
                    return org_l1_hit

        if dev_match is not None and dev_match.action == "execute" and dev_match.command:
            confirmed = request.meta.confirm_tool or bool(re.search(r"(?i)(?:^|\s)--yes(?:\s|$)", last_user))
            policy = self.policy.evaluate(dev_match.command, confirmed=confirmed)
            if policy.outcome == "deny":
                denial = InternalResponse(
                    content=f"Command denied by policy: {policy.reason}",
                    model=request.model,
                    daari_meta=DaariMeta(
                        tier="Lt",
                        executor="policy",
                        provider_id="policy",
                        task_type="tool",
                        rule_id=dev_match.rule_id,
                        policy="deny",
                    ),
                )
                self._record(denial, started)
                return denial
            if policy.outcome == "ask":
                prompt = (
                    "Command requires confirmation. Re-send the same request with "
                    "header X-Daari-Confirm: yes (or X-Daari-Confirm-Tool: true)."
                )
                ask = InternalResponse(
                    content=prompt,
                    model=request.model,
                    daari_meta=DaariMeta(
                        tier="Lt",
                        executor="policy",
                        provider_id="policy",
                        task_type="tool",
                        rule_id=dev_match.rule_id,
                        policy="ask",
                        pending_command=dev_match.command,
                        confirmation_prompt=prompt,
                        confirmation_header="X-Daari-Confirm: yes",
                    ),
                )
                self._record(ask, started)
                return ask

            shell = await self.shell_executor.run(dev_match.command, cwd=os.getcwd())
            if self.command_context and not request.meta.no_cache:
                try:
                    self.command_context.put(
                        repo_root=os.getcwd(),
                        cwd=os.getcwd(),
                        command=dev_match.command,
                        output=shell.output,
                        exit_code=shell.exit_code,
                        ttl_seconds=dev_match.ttl_seconds,
                    )
                except Exception:
                    # CCS failures should not fail the primary Lt execution path.
                    pass
            result = InternalResponse(
                content=shell.output or "(no output)",
                model=request.model,
                daari_meta=DaariMeta(
                    tier="Lt",
                    executor="shell",
                    provider_id="shell",
                    tool=dev_match.command,
                    task_type="tool",
                    rule_id=dev_match.rule_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    policy="allow",
                ),
            )
            self._record(result, started)
            return result

        fetch_url = self._match_live_fetch_url(last_user)
        if fetch_url:
            fetched = await self._run_live_fetch(request, fetch_url, started)
            self._record(fetched, started)
            return fetched

        l2_result = apply_l2_rules(last_user)
        if l2_result is not None:
            rule_id, transformed = l2_result
            out = InternalResponse(
                content=transformed,
                model=request.model,
                daari_meta=DaariMeta(
                    tier="L2",
                    executor="rules",
                    provider_id="rules",
                    task_type="rule",
                    rule_id=rule_id,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ),
            )
            self._record(out, started)
            return out

        integration_provider_id = self._match_integration_provider(last_user)
        if integration_provider_id:
            provider = self.provider_registry.get(integration_provider_id)
            if provider is not None:
                integrated = await provider.execute(request)
                self._record(integrated, started)
                return integrated

        initial_tier = self._choose_initial_tier(request)
        try:
            response = await self._run_model_tier(initial_tier, request)
        except Exception:
            if initial_tier == "L4":
                response = await self._run_model_tier("L3", request)
                response.daari_meta.warning = "l4_unavailable_fell_back_to_l3"
            elif initial_tier == "L5":
                try:
                    response = await self._run_model_tier("L4", request)
                    response.daari_meta.warning = "l5_unavailable_fell_back_to_l4"
                except Exception:
                    response = await self._run_model_tier("L3", request)
                    response.daari_meta.warning = "l5_unavailable_fell_back_to_l3"
            else:
                raise
        response = await self._maybe_escalate(request, response, started)
        if not request.meta.no_cache and response.daari_meta.tier in {"L3", "L4", "L5"} and response.content.strip():
            try:
                self.cache.put(request, response)
            except Exception:
                pass
            if self.org_cache_client is not None:
                try:
                    await self.org_cache_client.put_l0(request, response)
                except Exception:
                    pass
            try:
                await self.semantic_cache.put(request, response)
            except Exception:
                pass
            if self.org_cache_client is not None:
                try:
                    await self.org_cache_client.put_l1(request, response)
                except Exception:
                    pass
        self._record(response, started)
        return response

    def _with_skills_prefix(self, request: InternalRequest) -> InternalRequest:
        if not self.skills_system_prefix:
            return request
        if request.messages and request.messages[0].role == "system" and request.messages[0].content == self.skills_system_prefix:
            return request
        req = request.model_copy(deep=True)
        req.messages = [Message(role="system", content=self.skills_system_prefix), *req.messages]
        return req

    def _match_integration_provider(self, text: str) -> str | None:
        text_lower = text.strip().lower()
        trigger_map = {
            "integration:sourcegraph": self.integration_triggers.get("integration:sourcegraph", ["@sourcegraph"]),
            "integration:ghe": self.integration_triggers.get("integration:ghe", ["@ghe"]),
            "integration:gitlab": self.integration_triggers.get("integration:gitlab", ["@gitlab"]),
        }
        for provider_id, triggers in trigger_map.items():
            for trigger in triggers:
                normalized = trigger.strip().lower()
                if not normalized:
                    continue
                if text_lower.startswith(normalized):
                    return provider_id
        return None

    async def stream_openai_chunks(self, request: InternalRequest) -> AsyncIterator[str]:
        """Emit OpenAI-compatible SSE chunks (strict shape for Cursor and other clients)."""
        from daari.gateway.content import sanitize_messages_for_ollama
        from daari.gateway.request_log import log_gateway_event

        started = time.perf_counter()
        created = int(time.time())
        chunk_id = f"chatcmpl-{int(time.time() * 1000)}"
        client_model = request.model or self.ollama_l3.default_model
        tier_chain = self._stream_tier_chain(request)
        # Agent flows (tools passed through by the gateway, or tool history)
        # keep the full tool protocol; Ask flows get plain-text sanitization.
        agent_flow = bool(request.tools) or request.has_tool_calls_in_history
        # ADR-0004: agent turns skip L0 entirely; explicit no-cache also bypasses.
        cacheable = not agent_flow and not request.meta.no_cache
        stream_request = request.model_copy(deep=True)
        if not agent_flow:
            stream_request.tools = None
            stream_request.messages = sanitize_messages_for_ollama(stream_request.messages)
        prompt_chars = sum(len(message.content or "") for message in stream_request.messages)
        completion_chars = 0

        log_gateway_event(
            "stream_tier_chain",
            {"tiers": tier_chain, "model": client_model, "message_count": len(stream_request.messages)},
        )

        def chunk_payload(*, delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
            choice: dict[str, Any] = {"index": 0, "delta": delta}
            if finish_reason is not None:
                choice["finish_reason"] = finish_reason
            return {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": client_model,
                "choices": [choice],
            }

        def usage_chunk(completion_len: int) -> str:
            payload = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": client_model,
                "choices": [],
                "usage": {
                    "prompt_tokens": max(1, prompt_chars // 4),
                    "completion_tokens": max(0, completion_len // 4),
                    "total_tokens": max(1, (prompt_chars + completion_len) // 4),
                },
            }
            return f"data: {json.dumps(payload)}\n\n"

        if cacheable:
            try:
                cached = self.cache.get(request)
            except Exception:
                cached = None
            if cached is not None and cached.content.strip():
                latency_ms = int((time.perf_counter() - started) * 1000)
                self.metrics.record("L0", cache_hit=True, latency_ms=latency_ms)
                log_gateway_event("stream_cache_hit", {"tier": "L0", "model": client_model})
                yield f"data: {json.dumps(chunk_payload(delta={'role': 'assistant'}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={'content': cached.content}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={}, finish_reason='stop'))}\n\n"
                yield usage_chunk(len(cached.content))
                yield "data: [DONE]\n\n"
                return

        last_error: Exception | None = None
        for tier_index, tier in enumerate(tier_chain):
            stream_executor = self._executor_for_tier(tier)
            ollama_model = stream_executor.default_model
            stream_request.model = ollama_model
            log_gateway_event("stream_attempt", {"tier": tier, "ollama_model": ollama_model})

            role_chunk = f"data: {json.dumps(chunk_payload(delta={'role': 'assistant'}))}\n\n"
            pending_chunks: list[str] = []
            tier_text_parts: list[str] = []
            content_sent = False
            tool_calls_sent = False
            tier_completion_chars = 0
            try:
                async for event in stream_executor.stream(stream_request):
                    message = event.get("message", {})
                    delta = message.get("content", "")
                    raw_tool_calls = message.get("tool_calls")
                    if raw_tool_calls and agent_flow:
                        if not content_sent:
                            pending_chunks.append(role_chunk)
                            content_sent = True
                        tool_calls_sent = True
                        deltas = _openai_tool_call_deltas(raw_tool_calls)
                        pending_chunks.append(
                            f"data: {json.dumps(chunk_payload(delta={'tool_calls': deltas}))}\n\n"
                        )
                    elif not delta and raw_tool_calls:
                        # Ask mode: model ignored the no-tools hint; degrade to text.
                        delta = json.dumps(raw_tool_calls)
                    if delta:
                        if not content_sent:
                            pending_chunks.append(role_chunk)
                            content_sent = True
                        tier_completion_chars += len(delta)
                        tier_text_parts.append(delta)
                        pending_chunks.append(
                            f"data: {json.dumps(chunk_payload(delta={'content': delta}))}\n\n"
                        )
                    if event.get("done"):
                        break
            except Exception as exc:
                last_error = exc
                log_gateway_event(
                    "stream_attempt_failed",
                    {"tier": tier, "ollama_model": ollama_model, "error": str(exc)[:300]},
                )
                if tier_index < len(tier_chain) - 1:
                    continue
                yield f"data: {json.dumps({'error': f'stream failed: {exc}'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            if not content_sent and tier_index < len(tier_chain) - 1:
                log_gateway_event("stream_empty_retry", {"tier": tier, "ollama_model": ollama_model})
                continue

            if tier_index > 0 and content_sent:
                log_gateway_event("stream_fallback_ok", {"tier": tier, "ollama_model": ollama_model})

            completion_chars = tier_completion_chars
            if content_sent:
                for chunk in pending_chunks:
                    yield chunk
            else:
                yield role_chunk
            finish_reason = "tool_calls" if tool_calls_sent else "stop"
            yield f"data: {json.dumps(chunk_payload(delta={}, finish_reason=finish_reason))}\n\n"
            yield usage_chunk(completion_chars)
            yield "data: [DONE]\n\n"

            latency_ms = int((time.perf_counter() - started) * 1000)
            self.metrics.record(tier, cache_hit=False, latency_ms=latency_ms)
            streamed_text = "".join(tier_text_parts)
            if cacheable and not tool_calls_sent and streamed_text.strip() and tier in {"L3", "L4", "L5"}:
                try:
                    self.cache.put(
                        request,
                        InternalResponse(
                            content=streamed_text,
                            model=ollama_model,
                            daari_meta=DaariMeta(
                                tier=tier,
                                cache_hit=False,
                                executor="ollama",
                                provider_id=f"ollama:{tier.lower()}",
                                latency_ms=latency_ms,
                                model=ollama_model,
                            ),
                        ),
                    )
                except Exception:
                    pass
            return

        if last_error is not None:
            raise last_error

    def _stream_tier_chain(self, request: InternalRequest) -> list[str]:
        initial = self._choose_initial_tier(request)
        chain = [initial]
        if initial == "L5":
            chain.extend(["L4", "L3"])
        elif initial == "L4":
            chain.append("L3")
        deduped: list[str] = []
        for tier in chain:
            if tier not in deduped:
                deduped.append(tier)
        return deduped

    async def stream_anthropic_events(self, request: InternalRequest) -> AsyncIterator[str]:
        """Emit Anthropic-compatible SSE events with daari metadata."""
        created = int(time.time())
        message_id = f"msg_{int(time.time() * 1000)}"
        stream_tier = self._choose_initial_tier(request)
        stream_executor = self._executor_for_tier(stream_tier)
        model_name = stream_executor.default_model
        meta = {
            "tier": stream_tier,
            "executor": "ollama",
            "provider_id": f"ollama:{stream_tier.lower()}",
            "model": model_name,
            "stream": True,
        }

        message_start = {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
            "daari_meta": meta,
        }
        yield f"event: message_start\ndata: {json.dumps(message_start)}\n\n"

        block_start = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
            "daari_meta": meta,
        }
        yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"

        async for event in stream_executor.stream(request):
            delta = event.get("message", {}).get("content", "")
            if delta:
                block_delta = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": delta},
                    "daari_meta": meta,
                }
                yield f"event: content_block_delta\ndata: {json.dumps(block_delta)}\n\n"
            if event.get("done"):
                break

        block_stop = {"type": "content_block_stop", "index": 0, "daari_meta": meta}
        yield f"event: content_block_stop\ndata: {json.dumps(block_stop)}\n\n"

        message_delta = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 0},
            "daari_meta": meta,
        }
        yield f"event: message_delta\ndata: {json.dumps(message_delta)}\n\n"

        message_stop = {"type": "message_stop", "daari_meta": meta}
        yield f"event: message_stop\ndata: {json.dumps(message_stop)}\n\n"

    def _resolve_ccs_hit(self, dev_match: DevCommandMatch | None, request: InternalRequest) -> InternalResponse | None:
        if self.command_context is None or request.meta.no_cache:
            return None

        if dev_match is None:
            return None

        known_commands = ["git status", "git diff", "pytest", "eslint ."]
        if dev_match.action == "ccs_read":
            for command in known_commands:
                try:
                    entry = self.command_context.get(repo_root=os.getcwd(), cwd=os.getcwd(), command=command)
                except Exception:
                    return None
                if entry is not None:
                    return InternalResponse(
                        content=entry.output or "(cached command had no output)",
                        model=request.model,
                        daari_meta=DaariMeta(
                            tier="CCS",
                            cache_hit=True,
                            executor="cache",
                            provider_id="ccs",
                            task_type="tool",
                            tool=entry.command,
                            rule_id=dev_match.rule_id,
                        ),
                    )
            return None

        if dev_match.action == "execute" and dev_match.command and not (dev_match.needs_rerun or request.meta.rerun_command):
            try:
                entry = self.command_context.get(
                    repo_root=os.getcwd(),
                    cwd=os.getcwd(),
                    command=dev_match.command,
                )
            except Exception:
                return None
            if entry is None:
                return None
            return InternalResponse(
                content=entry.output or "(cached command had no output)",
                model=request.model,
                daari_meta=DaariMeta(
                    tier="CCS",
                    cache_hit=True,
                    executor="cache",
                    provider_id="ccs",
                    task_type="tool",
                    tool=entry.command,
                    rule_id=dev_match.rule_id,
                ),
            )
        return None

    async def _run_model_tier(self, tier: str, request: InternalRequest) -> InternalResponse:
        provider = self.provider_registry.get(f"ollama:{tier.lower()}")
        if provider is not None:
            provider_request = request.model_copy(deep=True)
            if tier == "L3":
                provider_request.model = self.ollama_l3.default_model
            elif tier == "L4":
                provider_request.model = self.ollama_l4.default_model
            elif tier == "L5":
                provider_request.model = self.ollama_l5.default_model
            response = await provider.execute(provider_request)
            response.daari_meta.tier = tier
            return response
        executor = self._executor_for_tier(tier)
        req = request.model_copy(deep=True)
        req.model = executor.default_model
        return await executor.execute(req)

    def _executor_for_tier(self, tier: str) -> OllamaExecutor:
        if tier == "L4":
            return self.ollama_l4
        if tier == "L5":
            return self.ollama_l5
        return self.ollama_l3

    def _choose_initial_tier(self, request: InternalRequest) -> str:
        override = (request.meta.tier_override or "").upper()
        if override in {"L3", "L4", "L5"}:
            return override
        text = self._last_user_text(request.messages)
        words = len(re.findall(r"\S+", text))
        if words > 900 and self.model_preference == "accuracy":
            return "L5"
        if words > 250:
            return "L4"
        if words <= 12:
            return "L3"

        l3_name = self.ollama_l3.default_model
        l4_name = self.ollama_l4.default_model
        l5_name = self.ollama_l5.default_model
        l3_weight = self.model_weights.get(l3_name, {"latency": 0.8, "accuracy": 0.6})
        l4_weight = self.model_weights.get(l4_name, {"latency": 0.5, "accuracy": 0.8})
        l5_weight = self.model_weights.get(l5_name, {"latency": 0.2, "accuracy": 0.95})

        if self.model_preference == "latency":
            scores = {"L3": l3_weight.get("latency", 0.0), "L4": l4_weight.get("latency", 0.0), "L5": l5_weight.get("latency", 0.0)}
            return max(scores, key=scores.get)
        if self.model_preference == "accuracy":
            scores = {"L3": l3_weight.get("accuracy", 0.0), "L4": l4_weight.get("accuracy", 0.0), "L5": l5_weight.get("accuracy", 0.0)}
            return max(scores, key=scores.get)

        # Balanced: blend both dimensions and pick the stronger score.
        l3_score = 0.5 * l3_weight.get("latency", 0.0) + 0.5 * l3_weight.get("accuracy", 0.0)
        l4_score = 0.5 * l4_weight.get("latency", 0.0) + 0.5 * l4_weight.get("accuracy", 0.0)
        l5_score = 0.5 * l5_weight.get("latency", 0.0) + 0.5 * l5_weight.get("accuracy", 0.0)
        scores = {"L3": l3_score, "L4": l4_score, "L5": l5_score}
        return max(scores, key=scores.get)

    @staticmethod
    def _last_user_text(messages: list[Message]) -> str:
        if not messages:
            return ""
        for message in reversed(messages):
            if message.role == "user":
                return message.content or ""
        return messages[-1].content or ""

    async def _maybe_escalate(
        self,
        request: InternalRequest,
        response: InternalResponse,
        started: float,
    ) -> InternalResponse:
        confidence = score_l3_confidence(response.content)
        response.daari_meta.confidence = confidence

        if confidence >= self.confidence_threshold:
            return response

        tier_chain = ["L3", "L4", "L5"]
        current_tier = response.daari_meta.tier
        if current_tier in tier_chain:
            current_idx = tier_chain.index(current_tier)
            for next_tier in tier_chain[current_idx + 1 :]:
                try:
                    next_request = request.model_copy(deep=True)
                    next_request.model = self._executor_for_tier(next_tier).default_model
                    next_response = await self._run_model_tier(next_tier, next_request)
                    next_confidence = score_l3_confidence(next_response.content)
                    next_response.daari_meta.confidence = next_confidence
                    if next_confidence >= self.confidence_threshold:
                        return next_response
                    response = next_response
                    confidence = next_confidence
                except Exception:
                    response.daari_meta.warning = "below_confidence_threshold"
                    return response

        if request.meta.no_frontier or not self.frontier_enabled:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        if self.frontier is None or not self.frontier.api_key:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        try:
            l6_response = await self.frontier.execute(
                request,
                escalated_from=response.daari_meta.tier,
                local_confidence=confidence,
            )
            return l6_response
        except Exception:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

    def _record(self, response: InternalResponse, started: float) -> None:
        self._emit_org_feedback("", response)
        if response.daari_meta.tier in ("L0", "L1"):
            return
        latency_ms = response.daari_meta.latency_ms or int((time.perf_counter() - started) * 1000)
        self.metrics.record(
            response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            latency_ms=latency_ms,
        )

    def _emit_org_feedback(self, last_user: str, response: InternalResponse) -> None:
        if not self.org_learning_enabled or self.org_learning_client is None:
            return
        task_class = response.daari_meta.task_type or self._classify_task(last_user)
        feedback = OrgLearningFeedback(
            tier=response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            latency_ms=max(0, int(response.daari_meta.latency_ms or 0)),
            task_class=task_class,
        )
        try:
            asyncio.create_task(self.org_learning_client.post_feedback(feedback))
        except Exception:
            return

    @staticmethod
    def _classify_task(text: str) -> str:
        normalized = text.lower()
        if any(token in normalized for token in ("pytest", "test", "unit test")):
            return "test"
        if any(token in normalized for token in ("git ", "commit", "branch", "merge", "rebase")):
            return "git"
        if any(token in normalized for token in ("lint", "eslint", "ruff", "flake8")):
            return "lint"
        if any(token in normalized for token in ("http://", "https://", "fetch ", "api ")):
            return "fetch"
        if any(token in normalized for token in ("refactor", "function", "class", "code", "bug")):
            return "code"
        return "general"

    @staticmethod
    def _match_live_fetch_url(text: str) -> str | None:
        if not text:
            return None
        if not re.search(r"(?i)\b(fetch|read|summarize|get)\b", text):
            return None
        match = re.search(r"(https?://[^\s)]+)", text)
        if match is None:
            return None
        return match.group(1).rstrip(".,")

    async def _run_live_fetch(self, request: InternalRequest, url: str, started: float) -> InternalResponse:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return InternalResponse(
                content=f"Unable to fetch {url}: {exc}",
                model=request.model,
                daari_meta=DaariMeta(
                    tier="Lt-fetch",
                    executor="fetch",
                    provider_id="httpx",
                    task_type="tool",
                    tool=f"GET {url}",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    warning="fetch_failed",
                ),
            )

        page = re.sub(r"\s+", " ", response.text)[:4000]
        summary_request = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content=(
                        f"Summarize this fetched page for the user in <=8 bullets.\n"
                        f"URL: {url}\n"
                        f"Original request: {self._last_user_text(request.messages)}\n"
                        f"Page content snippet:\n{page}"
                    ),
                )
            ],
            model=self.ollama_l3.default_model,
            temperature=0.2,
            stream=False,
            meta=request.meta.model_copy(deep=True),
        )
        try:
            summary = await self._run_model_tier("L3", summary_request)
            content = summary.content
            model = summary.model
        except Exception:
            content = f"Fetched {url} ({len(response.text)} bytes). Could not summarize with L3."
            model = request.model

        return InternalResponse(
            content=content,
            model=model,
            daari_meta=DaariMeta(
                tier="Lt-fetch",
                executor="fetch+summarize",
                provider_id="httpx",
                task_type="tool",
                tool=f"GET {url}",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )


@dataclass
class AppContext:
    settings: Settings
    cache: ExactCache
    semantic_cache: SemanticCache
    command_context: CommandContextStore
    ollama_l3: OllamaExecutor
    ollama_l4: OllamaExecutor
    ollama_l5: OllamaExecutor
    frontier: FrontierExecutor
    shell_executor: ShellExecutor
    policy: PolicyEngine
    providers: ProviderRegistry
    metrics: Metrics
    router: Router
    org_cache_client: OrgCacheClient | None = None
    org_learning_client: OrgLearningClient | None = None
    org_learning_sync_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    @property
    def ollama(self) -> OllamaExecutor:
        return self.ollama_l3

    def _resolve_runtime_paths(self) -> tuple[Path, Path, Path]:
        l0_path = self.settings.l0_cache_path
        l1_path = self.settings.l1_cache_path
        context_path = self.settings.context_store_path
        if self.settings.enterprise.enabled and self.settings.enterprise.resolved_org_id:
            l0_path = resolve_org_scoped_path(l0_path, self.settings.enterprise, leaf="l0")
            l1_path = resolve_org_scoped_path(l1_path, self.settings.enterprise, leaf="l1")
            context_path = resolve_org_scoped_path(context_path, self.settings.enterprise, leaf="ccs")
        return l0_path, l1_path, context_path

    @staticmethod
    def _build_command_context_store(settings: Settings, context_path: Path) -> CommandContextStore:
        try:
            return CommandContextStore(
                root=context_path,
                enabled=settings.context.enabled,
            )
        except PermissionError:
            try:
                fallback_root = settings.l0_cache_path.parent / "context" / "commands"
                return CommandContextStore(
                    root=fallback_root,
                    enabled=settings.context.enabled,
                )
            except PermissionError:
                return CommandContextStore(
                    root=Path(os.getcwd()) / ".daari" / "context" / "commands",
                    enabled=settings.context.enabled,
                )

    def reload_cache_handles(self) -> dict[str, str | bool]:
        l0_path, l1_path, context_path = self._resolve_runtime_paths()
        self.cache = ExactCache(path=str(l0_path), enabled=self.settings.cache.l0.enabled)
        self.semantic_cache = SemanticCache(
            path=str(l1_path),
            embedder=OllamaEmbedder(
                base_url=self.settings.ollama.base_url.rstrip("/"),
                model=self.settings.cache.l1.embedding_model,
            ),
            enabled=self.settings.cache.l1.enabled,
            similarity_threshold=self.settings.cache.l1.similarity_threshold,
            max_entries=self.settings.cache.l1.max_entries,
        )
        self.command_context = self._build_command_context_store(self.settings, context_path)

        self.router.cache = self.cache
        self.router.semantic_cache = self.semantic_cache
        self.router.command_context = self.command_context

        return {
            "reloaded": True,
            "l0_path": str(l0_path),
            "l1_path": str(l1_path),
            "ccs_path": str(context_path),
        }

    def _apply_org_learning_profile(self, profile: dict[str, object] | None) -> bool:
        if not isinstance(profile, dict):
            return False
        routing_block = profile.get("routing")
        if not isinstance(routing_block, dict):
            return False
        changed = False
        prefer = routing_block.get("prefer")
        threshold = routing_block.get("confidence_threshold")
        if isinstance(prefer, str) and prefer != self.router.model_preference:
            self.router.model_preference = prefer
            changed = True
        if isinstance(threshold, (int, float)):
            threshold_value = float(threshold)
            if threshold_value != self.router.confidence_threshold:
                self.router.confidence_threshold = threshold_value
                changed = True
        return changed

    def sync_org_learning_profile_startup(self) -> bool:
        if self.org_learning_client is None:
            return False
        profile = self.org_learning_client.get_profile_sync()
        return self._apply_org_learning_profile(profile)

    async def sync_org_learning_profile_once(self) -> bool:
        if self.org_learning_client is None:
            return False
        profile = await self.org_learning_client.get_profile()
        return self._apply_org_learning_profile(profile)

    def start_org_learning_sync(self) -> None:
        if self.org_learning_client is None:
            return
        interval = float(self.settings.enterprise.learning_sync_seconds)
        if interval <= 0:
            return
        if self.org_learning_sync_task is not None and not self.org_learning_sync_task.done():
            return

        async def _sync_loop() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    await self.sync_org_learning_profile_once()
            except asyncio.CancelledError:
                return

        self.org_learning_sync_task = asyncio.create_task(_sync_loop())

    async def stop_org_learning_sync(self) -> None:
        if self.org_learning_sync_task is None:
            return
        self.org_learning_sync_task.cancel()
        try:
            await self.org_learning_sync_task
        except asyncio.CancelledError:
            pass
        self.org_learning_sync_task = None

    @classmethod
    def from_settings(cls, settings: Settings) -> AppContext:
        l0_path = settings.l0_cache_path
        l1_path = settings.l1_cache_path
        context_path = settings.context_store_path
        if settings.enterprise.enabled and settings.enterprise.resolved_org_id:
            l0_path = resolve_org_scoped_path(l0_path, settings.enterprise, leaf="l0")
            l1_path = resolve_org_scoped_path(l1_path, settings.enterprise, leaf="l1")
            context_path = resolve_org_scoped_path(context_path, settings.enterprise, leaf="ccs")
        org_cache_client: OrgCacheClient | None = None
        org_learning_client: OrgLearningClient | None = None
        if settings.enterprise.shared_cache_url:
            org_cache_client = OrgCacheClient(
                base_url=settings.enterprise.shared_cache_url,
                token=settings.enterprise.shared_cache_token,
                timeout_seconds=settings.enterprise.shared_cache_timeout_seconds,
                enabled=True,
            )
        learning_enabled = settings.enterprise.learning_enabled or settings.enterprise.learning.enabled
        if learning_enabled and settings.enterprise.learning_url:
            org_learning_client = OrgLearningClient(
                base_url=settings.enterprise.learning_url,
                token=settings.enterprise.learning_token or settings.enterprise.org_token,
                timeout_seconds=settings.enterprise.learning_timeout_seconds,
                enabled=True,
            )
        cache = ExactCache(
            path=str(l0_path),
            enabled=settings.cache.l0.enabled,
        )
        embedder = OllamaEmbedder(
            base_url=settings.ollama.base_url.rstrip("/"),
            model=settings.cache.l1.embedding_model,
        )
        semantic_cache = SemanticCache(
            path=str(l1_path),
            embedder=embedder,
            enabled=settings.cache.l1.enabled,
            similarity_threshold=settings.cache.l1.similarity_threshold,
            max_entries=settings.cache.l1.max_entries,
        )
        command_context = cls._build_command_context_store(settings, context_path)
        ollama_l3 = OllamaExecutor(
            base_url=settings.ollama.base_url.rstrip("/"),
            default_model=settings.models.l3,
            tier="L3",
        )
        ollama_l4 = OllamaExecutor(
            base_url=settings.ollama.base_url.rstrip("/"),
            default_model=settings.models.l4,
            tier="L4",
        )
        ollama_l5 = OllamaExecutor(
            base_url=settings.ollama.base_url.rstrip("/"),
            default_model=settings.models.l5,
            tier="L5",
        )
        frontier = FrontierExecutor(
            base_url=settings.frontier.base_url.rstrip("/"),
            default_model=settings.frontier.model,
            api_key=settings.resolve_frontier_api_key(),
            provider=settings.frontier.provider,
        )
        shell_executor = ShellExecutor(timeout_seconds=settings.tools.timeout_seconds)
        policy = PolicyEngine(
            allow_patterns=settings.tools.allow,
            block_patterns=settings.tools.block,
            unknown=settings.tools.unknown,
        )
        providers = ProviderRegistry()
        providers.register(
            CallableProvider(
                id="ollama:l3",
                tier="L3",
                execute_fn=lambda request, executor=ollama_l3: executor.execute(request),
            )
        )
        providers.register(
            CallableProvider(
                id="ollama:l4",
                tier="L4",
                execute_fn=lambda request, executor=ollama_l4: executor.execute(request),
            )
        )
        providers.register(
            CallableProvider(
                id="ollama:l5",
                tier="L5",
                execute_fn=lambda request, executor=ollama_l5: executor.execute(request),
            )
        )
        providers.register(SourcegraphProvider(base_url=settings.integrations.sourcegraph.url))
        providers.register(GitHubEnterpriseProvider(base_url=settings.integrations.ghe.url))
        providers.register(GitLabProvider(base_url=settings.integrations.gitlab.url))
        metrics = Metrics()
        router = Router(
            cache=cache,
            semantic_cache=semantic_cache,
            command_context=command_context,
            ollama_l3=ollama_l3,
            ollama_l4=ollama_l4,
            ollama_l5=ollama_l5,
            metrics=metrics,
            frontier=frontier,
            shell_executor=shell_executor,
            policy=policy,
            provider_registry=providers,
            model_preference=settings.routing.prefer,
            model_weights=settings.models.weights,
            integration_triggers={
                "integration:sourcegraph": settings.integrations.sourcegraph.triggers,
                "integration:ghe": settings.integrations.ghe.triggers,
                "integration:gitlab": settings.integrations.gitlab.triggers,
            },
            skills_system_prefix=settings.skills_system_prefix,
            org_cache_client=org_cache_client,
            org_learning_client=org_learning_client,
            org_learning_enabled=learning_enabled,
            frontier_enabled=settings.frontier.enabled,
            confidence_threshold=settings.routing.confidence_threshold,
        )
        context = cls(
            settings=settings,
            cache=cache,
            semantic_cache=semantic_cache,
            command_context=command_context,
            ollama_l3=ollama_l3,
            ollama_l4=ollama_l4,
            ollama_l5=ollama_l5,
            frontier=frontier,
            shell_executor=shell_executor,
            policy=policy,
            providers=providers,
            metrics=metrics,
            router=router,
            org_cache_client=org_cache_client,
            org_learning_client=org_learning_client,
        )
        context.sync_org_learning_profile_startup()
        return context
