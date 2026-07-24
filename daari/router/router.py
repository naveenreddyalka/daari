from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx

from daari.cache.command_context import CommandContextStore
from daari.cache.exact import ExactCache
from daari.cache.semantic import OllamaEmbedder, SemanticCache, cosine_similarity
from daari.config.settings import Settings
from daari.enterprise.cache import resolve_org_scoped_path
from daari.enterprise.client import OrgCacheClient, OrgLearningClient, OrgLearningFeedback
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore, add_step, end_trace, start_trace
from daari.observability.usage import UsageLedger
from daari.policy.engine import PolicyEngine
from daari.providers.integrations import GitHubEnterpriseProvider, GitLabProvider, SourcegraphProvider
from daari.providers.registry import ProviderRegistry
from daari.rules.dev_commands import DevCommandMatch, match_dev_command
from daari.rules.engine import apply_l2_rules
from daari.router.confidence import score_l3_confidence
from daari.router.frontier import FrontierExecutor
from daari.router.mlx_executor import MLXExecutor
from daari.router.context_optimizer import optimize_messages
from daari.router.profile import PromptProfile, build_prompt_profile, categorize
from daari.tools.shell import ShellExecutor


def _guardrails_from_settings(settings: Settings) -> Any | None:
    from daari.gateway.guardrails import engine_from_settings

    return engine_from_settings(settings)


def _build_l0_cache(settings: Settings, l0_path: Path) -> ExactCache:
    if getattr(settings.cache, "backend", "disk") == "redis":
        from daari.cache.redis_exact import RedisExactCache

        return RedisExactCache(
            settings.cache.redis_url,
            prefix=settings.cache.redis_prefix,
            enabled=settings.cache.l0.enabled,
            ttl_seconds=settings.cache.l0.ttl_seconds,
        )
    return ExactCache(
        path=str(l0_path),
        enabled=settings.cache.l0.enabled,
        ttl_seconds=settings.cache.l0.ttl_seconds,
    )


def _catalog_from_settings(settings: Settings) -> Any:
    from daari.router.capabilities import catalog_from_settings

    return catalog_from_settings(settings)


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


def _draft_hint(draft: str, similarity: float) -> str:
    return (
        f"A previous answer to a similar question (similarity {similarity:.2f}) is provided "
        "below. Reuse whatever is still correct; reformat or correct it as needed rather "
        f"than writing from scratch.\n\n---\n{draft}"
    )


def estimate_num_ctx(prompt_chars: int, *, floor: int = 4096, ceiling: int = 32768) -> int:
    """Pick an Ollama num_ctx large enough for the prompt plus completion headroom.

    Ollama's default context silently truncates big prompts (issue #88 —
    Claude Code system prompts alone are >10k tokens), which manifests as
    empty streams. chars/4 approximates tokens; 2048 headroom for output.
    """
    estimated_tokens = max(0, prompt_chars) // 4 + 2048
    num_ctx = floor
    while num_ctx < estimated_tokens and num_ctx < ceiling:
        num_ctx *= 2
    return min(num_ctx, ceiling)


class OllamaRequestError(RuntimeError):
    """Ollama HTTP error with the response body preserved for diagnosis."""

    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.body = body[:500]
        super().__init__(f"Ollama {status_code} at {url}: {self.body}")


@dataclass
class OllamaExecutor:
    base_url: str
    default_model: str
    tier: str = "L3"
    timeout: float = 120.0

    def _payload(self, request: InternalRequest, model: str, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for m in request.messages:
            data = m.model_dump(exclude_none=True)
            tool_calls = data.get("tool_calls")
            if tool_calls:
                # Ollama requires function.arguments as an object; OpenAI/Anthropic
                # conversions carry JSON strings (issue #88).
                for call in tool_calls:
                    function = call.get("function") if isinstance(call, dict) else None
                    if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                        try:
                            function["arguments"] = json.loads(function["arguments"] or "{}")
                        except json.JSONDecodeError:
                            function["arguments"] = {}
            elif not data.get("content"):
                # Content-less non-tool-call messages make Ollama reject the batch.
                continue
            messages.append(data)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        prompt_chars = sum(len(m.content or "") for m in request.messages)
        if request.tools:
            payload["tools"] = request.tools
            prompt_chars += len(json.dumps(request.tools))
        payload["options"] = {"num_ctx": estimate_num_ctx(prompt_chars)}
        return payload

    async def execute(self, request: InternalRequest) -> InternalResponse:
        model = request.model or self.default_model
        started = time.perf_counter()
        payload = self._payload(request, model, stream=False)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/chat", json=payload)
            if response.status_code >= 400:
                raise OllamaRequestError(
                    response.status_code, str(response.request.url), response.text
                )
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
        payload = self._payload(request, model, stream=True)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise OllamaRequestError(
                        response.status_code, str(response.request.url), body
                    )
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
        ollama_l3: OllamaExecutor | MLXExecutor | None = None,
        ollama_l4: OllamaExecutor | MLXExecutor | None = None,
        ollama_l5: OllamaExecutor | MLXExecutor | None = None,
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
        usage_ledger: UsageLedger | None = None,
        category_policies: dict[str, Any] | None = None,
        trace_store: TraceStore | None = None,
        feedback_store: Any | None = None,
        tuner: Any | None = None,
        example_store: Any | None = None,
        shadow_rng: Any | None = None,
        model_profile_store: Any | None = None,
        warm_tracker: Any | None = None,
        learned_router: Any | None = None,
        *,
        l1_shadow_sample_rate: float = 0.0,
        latency_budget_ms: int = 0,
        frontier_enabled: bool = False,
        confidence_threshold: float = 0.7,
        l1_draft_threshold: float = 0.75,
        context_optimizer_enabled: bool = True,
        context_max_history: int = 20,
        context_squeeze_whitespace: bool = True,
        context_compact: bool = False,
        frontier_compress: bool = False,
        frontier_compress_ratio: float = 0.6,
        max_tier_for_chat: str | None = None,
        frontier_daily_budget_usd: float = 0.0,
        frontier_monthly_budget_usd: float = 0.0,
        frontier_soft_budget_ratio: float = 0.8,
        frontier_price_per_1k_tokens: float = 0.002,
        frontier_scrub_pii: bool = False,
        frontier_slim_prompts: bool = True,
        frontier_max_history: int = 8,
        guardrails: Any | None = None,
        capability_catalog: Any | None = None,
        otel_enabled: bool = False,
        org_pool: OllamaExecutor | MLXExecutor | None = None,
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
        self.usage_ledger = usage_ledger
        self.category_policies = category_policies or {}
        self.trace_store = trace_store
        self.feedback_store = feedback_store
        self.tuner = tuner
        self.example_store = example_store
        self.model_profile_store = model_profile_store
        self.warm_tracker = warm_tracker
        self.learned_router = learned_router
        self.latency_budget_ms = latency_budget_ms
        self._warm_models: set[str] = set()
        self.l1_shadow_sample_rate = max(0.0, min(1.0, l1_shadow_sample_rate))
        self._shadow_rng = shadow_rng or random.random
        self._shadow_tasks: set[Any] = set()
        self._shadow_stats_cache: tuple[float, dict[str, Any]] | None = None
        self.l1_draft_threshold = l1_draft_threshold
        self.context_optimizer_enabled = context_optimizer_enabled
        self.context_max_history = context_max_history
        self.context_squeeze_whitespace = context_squeeze_whitespace
        self.context_compact = context_compact
        self.frontier_compress = frontier_compress
        self.frontier_compress_ratio = frontier_compress_ratio
        # Compaction summaries keyed by prefix hash (Trust PRD T2b).
        self._compaction_cache: dict[str, str] = {}
        self.max_tier_for_chat = max_tier_for_chat
        self.frontier_daily_budget_usd = frontier_daily_budget_usd
        self.frontier_monthly_budget_usd = frontier_monthly_budget_usd
        self.frontier_soft_budget_ratio = frontier_soft_budget_ratio
        self.frontier_price_per_1k_tokens = frontier_price_per_1k_tokens
        self.frontier_scrub_pii = frontier_scrub_pii
        self.frontier_slim_prompts = frontier_slim_prompts
        self.frontier_max_history = frontier_max_history
        self.guardrails = guardrails
        self.capability_catalog = capability_catalog
        self.otel_enabled = otel_enabled
        self.org_pool = org_pool

    @property
    def ollama(self) -> OllamaExecutor:
        return self.ollama_l3

    def _tier_models(self) -> dict[str, str]:
        return {
            "L3": self.ollama_l3.default_model,
            "L4": self.ollama_l4.default_model,
            "L5": self.ollama_l5.default_model,
        }

    def _filter_capable_tiers(self, tiers: list[str], request: InternalRequest) -> list[str]:
        if self.capability_catalog is None:
            return tiers
        from daari.router.capabilities import filter_tiers_by_capability, required_capabilities

        required = required_capabilities(request)
        if not required:
            return tiers
        kept = filter_tiers_by_capability(
            tiers,
            tier_models=self._tier_models(),
            catalog=self.capability_catalog,
            required=required,
        )
        if kept != tiers:
            add_step(
                "capability_filter",
                required=sorted(required),
                before=tiers,
                after=kept or tiers,
            )
        # Never empty the chain — fall back to the original if everything filtered out.
        return kept or tiers

    def _apply_guardrail_hits(self, hits: list[Any], *, warning: str | None) -> None:
        for hit in hits:
            add_step(
                "guardrail",
                stage=hit.stage,
                rule=hit.rule,
                action=hit.action,
                detail=hit.detail,
            )
            if hasattr(self.metrics, "record_guardrail"):
                self.metrics.record_guardrail(hit.action)
        if warning:
            add_step("guardrail_warning", warning=warning)

    async def route(self, request: InternalRequest) -> InternalResponse:
        from daari.gateway.guardrails import blocked_response

        profile = build_prompt_profile(request)
        trace = start_trace() if self.trace_store is not None else None
        add_step(
            "profile",
            category=profile.category,
            complexity=profile.complexity,
            prompt_tokens_est=profile.prompt_tokens_est,
        )
        profile = await self._apply_learned_route(request, profile)
        input_warning: str | None = None
        if self.guardrails is not None and getattr(self.guardrails, "enabled", False):
            inbound = self.guardrails.check_input(request)
            if inbound.hits:
                self._apply_guardrail_hits(inbound.hits, warning=inbound.warning)
            if inbound.blocked:
                response = blocked_response(request, self.guardrails.block_message)
                if response.daari_meta.task_type is None:
                    response.daari_meta.task_type = profile.category
                add_step("served", tier="guardrail", cache_hit=False, latency_ms=0)
                if trace is not None:
                    response.daari_meta.trace_id = trace.trace_id
                    self.trace_store.save(
                        trace, tier="guardrail", category=profile.category
                    )
                end_trace()
                return response
            input_warning = inbound.warning
        try:
            response = await self._route_impl(request, profile)
        except Exception:
            end_trace()
            raise
        if self.guardrails is not None and getattr(self.guardrails, "enabled", False):
            outbound = self.guardrails.check_output(response)
            if outbound.hits:
                self._apply_guardrail_hits(outbound.hits, warning=outbound.warning)
            if outbound.response is not None:
                response = outbound.response
            if outbound.warning and not response.daari_meta.warning:
                response.daari_meta.warning = outbound.warning
        if input_warning and not response.daari_meta.warning:
            response.daari_meta.warning = input_warning
        if response.daari_meta.task_type is None:
            response.daari_meta.task_type = profile.category
        if response.daari_meta.complexity is None:
            response.daari_meta.complexity = profile.complexity
        add_step(
            "served",
            tier=response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            latency_ms=response.daari_meta.latency_ms,
        )
        if trace is not None:
            response.daari_meta.trace_id = trace.trace_id
            self.trace_store.save(trace, tier=response.daari_meta.tier, category=profile.category)
            if getattr(self, "otel_enabled", False):
                from daari.observability.otel import export_trace

                export_trace(trace)
        end_trace()
        self._ledger_record(request, response)
        self._feedback_record(profile, response)
        self._example_record(request, profile, response)
        return response

    _MODEL_TIERS = {"L3", "L4", "L5", "L6"}

    def _feedback_record(self, profile: PromptProfile | None, response: InternalResponse) -> None:
        """Implicit D1 outcome capture — metadata only, best-effort."""
        if self.feedback_store is None:
            return
        meta = response.daari_meta
        if meta.tier not in self._MODEL_TIERS or meta.cache_hit:
            return
        try:
            self.feedback_store.record_outcome(
                trace_id=meta.trace_id,
                category=profile.category if profile is not None else meta.task_type,
                complexity=profile.complexity if profile is not None else meta.complexity,
                tier=meta.tier,
                confidence=meta.confidence,
                escalated=meta.tier == "L6" or meta.escalated_from is not None,
                latency_ms=meta.latency_ms,
            )
        except Exception:
            pass

    def _policy_for(self, profile: PromptProfile | None) -> Any | None:
        if profile is None:
            return None
        return self.category_policies.get(profile.category)

    def _category_cache_skip(self, profile: PromptProfile | None) -> bool:
        policy = self._policy_for(profile)
        return policy is not None and getattr(policy, "cache", "default") == "skip"

    def _category_cache_max_age(self, profile: PromptProfile | None) -> float | None:
        policy = self._policy_for(profile)
        if policy is None:
            return None
        ttl = getattr(policy, "ttl_seconds", None)
        return float(ttl) if isinstance(ttl, (int, float)) else None

    def _ledger_record(self, request: InternalRequest, response: InternalResponse) -> None:
        if self.usage_ledger is None:
            return
        if response.daari_meta.prompt_chars is not None:
            prompt_chars = response.daari_meta.prompt_chars
        else:
            prompt_chars = sum(len(message.content or "") for message in request.messages)
        self.usage_ledger.record(
            tier=response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            prompt_chars=prompt_chars,
            completion_chars=len(response.content or ""),
            client_id=request.meta.client_id,
        )

    def _example_record(
        self,
        request: InternalRequest,
        profile: PromptProfile | None,
        response: InternalResponse,
    ) -> None:
        """Opt-in D2a training-example capture — full text, never tool flows."""
        if self.example_store is None:
            return
        meta = response.daari_meta
        if (
            meta.tier not in self._MODEL_TIERS
            or meta.cache_hit
            or request.tools
            or request.has_tool_calls_in_history
            or not response.content.strip()
        ):
            return
        try:
            self.example_store.record(
                trace_id=meta.trace_id,
                category=profile.category if profile is not None else meta.task_type,
                complexity=profile.complexity if profile is not None else meta.complexity,
                tier=meta.tier,
                model=meta.model or response.model,
                messages=[
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                    if message.content
                ],
                completion=response.content,
            )
        except Exception:
            pass

    # Trust PRD T1c: shadow-check tuning knobs.
    _SHADOW_AGREE_SIMILARITY = 0.80
    _SHADOW_MIN_SAMPLES = 20
    _SHADOW_FALSE_HIT_LIMIT = 0.10
    _L1_THRESHOLD_STEP = 0.02
    _SHADOW_STATS_TTL = 60.0

    async def _apply_learned_route(
        self, request: InternalRequest, profile: PromptProfile
    ) -> PromptProfile:
        """Trust PRD Train 4: confident learned category beats the heuristic."""
        if self.learned_router is None:
            return profile
        try:
            if not self.learned_router.available:
                return profile
            text = self._last_user_text(request.messages)
            if not text.strip():
                return profile
            embedding = await self.semantic_cache.embedder.embed(text)
            if embedding is None:
                return profile
            prediction = self.learned_router.predict(embedding)
        except Exception:
            return profile
        if prediction is None or prediction[0] == profile.category:
            return profile
        category, confidence = prediction
        add_step(
            "learned_route",
            category=category,
            confidence=confidence,
            heuristic=profile.category,
        )
        return profile.model_copy(update={"category": category})

    async def _refresh_warm_models(self) -> None:
        """Trust PRD T3c: keep the /api/ps warm set fresh (TTL-cached)."""
        if self.warm_tracker is None:
            return
        try:
            await self.warm_tracker.refresh()
        except Exception:
            pass

    def _shadow_stats(self) -> dict[str, Any]:
        if self.feedback_store is None:
            return {}
        now = time.monotonic()
        if (
            self._shadow_stats_cache is not None
            and now - self._shadow_stats_cache[0] < self._SHADOW_STATS_TTL
        ):
            return self._shadow_stats_cache[1]
        try:
            stats = self.feedback_store.shadow_stats(days=7)
        except Exception:
            stats = {}
        self._shadow_stats_cache = (now, stats)
        return stats

    def _l1_threshold_for_category(self, category: str | None) -> float:
        """Raise the L1 similarity bar for categories with measured false hits."""
        base = self.semantic_cache.similarity_threshold
        if category is None:
            return base
        stats = self._shadow_stats().get(category)
        if not stats or stats.get("samples", 0) < self._SHADOW_MIN_SAMPLES:
            return base
        if stats.get("false_hit_rate", 0.0) > self._SHADOW_FALSE_HIT_LIMIT:
            tuned = min(0.99, base + self._L1_THRESHOLD_STEP)
            add_step("l1_threshold", category=category, base=base, tuned=tuned)
            return tuned
        return base

    def _maybe_shadow_check(
        self,
        request: InternalRequest,
        cached_content: str,
        profile: PromptProfile | None,
    ) -> None:
        """Sample L1 hits for background verification — never blocks serving."""
        if (
            self.feedback_store is None
            or self.l1_shadow_sample_rate <= 0.0
            or not cached_content.strip()
            or self._shadow_rng() >= self.l1_shadow_sample_rate
        ):
            return
        category = (
            profile.category
            if profile is not None
            else build_prompt_profile(request).category
        )
        try:
            task = asyncio.create_task(
                self._shadow_check(request, cached_content, category)
            )
        except RuntimeError:
            return
        self._shadow_tasks.add(task)
        task.add_done_callback(self._shadow_tasks.discard)

    async def _shadow_check(
        self, request: InternalRequest, cached_content: str, category: str
    ) -> None:
        try:
            fresh = await self.ollama_l3.execute(request.model_copy(deep=True))
            if not fresh.content.strip():
                return
            embedder = self.semantic_cache.embedder
            cached_vec = await embedder.embed(cached_content)
            fresh_vec = await embedder.embed(fresh.content)
            if cached_vec is None or fresh_vec is None:
                return
            similarity = cosine_similarity(cached_vec, fresh_vec)
            self.feedback_store.record_shadow(
                category=category,
                similarity=similarity,
                agreed=similarity >= self._SHADOW_AGREE_SIMILARITY,
            )
            self._shadow_stats_cache = None
        except Exception:
            pass

    async def _route_impl(
        self, request: InternalRequest, profile: PromptProfile | None = None
    ) -> InternalResponse:
        started = time.perf_counter()
        request = self._with_skills_prefix(request)
        last_user = self._last_user_text(request.messages)
        cache_skip = self._category_cache_skip(profile)
        cache_max_age = self._category_cache_max_age(profile)

        if request.has_tool_calls_in_history:
            response = await self._run_model_tier("L3", request)
            self._record(response, started)
            return response

        dev_match = match_dev_command(last_user)

        if not request.meta.no_cache and not cache_skip:
            try:
                cached = self.cache.get(request, max_age=cache_max_age)
            except Exception:
                cached = None
            add_step("l0_lookup", hit=cached is not None)
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

        draft_response: InternalResponse | None = None
        draft_similarity = 0.0
        if not request.meta.no_cache and not cache_skip:
            try:
                nearest_response, nearest_similarity = await self.semantic_cache.nearest(
                    request, max_age=cache_max_age
                )
            except Exception:
                nearest_response, nearest_similarity = None, 0.0
            l1_threshold = self._l1_threshold_for_category(
                profile.category if profile is not None else None
            )
            semantic_hit = (
                nearest_response
                if nearest_response is not None and nearest_similarity >= l1_threshold
                else None
            )
            add_step("l1_lookup", hit=semantic_hit is not None, similarity=round(nearest_similarity, 4))
            if (
                semantic_hit is None
                and nearest_response is not None
                and nearest_similarity >= self.l1_draft_threshold
                and nearest_response.content.strip()
            ):
                draft_response = nearest_response
                draft_similarity = nearest_similarity
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
                self._maybe_shadow_check(request, semantic_hit.content, profile)
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

        # The draft only affects generation (local and frontier); cache reads
        # and writes keep using the original request so keys are unaffected.
        gen_request = request
        if draft_response is not None:
            gen_request = request.model_copy(deep=True)
            gen_request.messages = [
                *gen_request.messages,
                Message(role="system", content=_draft_hint(draft_response.content, draft_similarity)),
            ]
            add_step("draft_injected", similarity=round(draft_similarity, 4))

        await self._refresh_warm_models()
        initial_tier = self._choose_initial_tier(request, profile)
        try:
            response = await self._run_model_tier(initial_tier, gen_request)
        except Exception:
            if initial_tier == "L4":
                response = await self._run_model_tier("L3", gen_request)
                response.daari_meta.warning = "l4_unavailable_fell_back_to_l3"
            elif initial_tier == "L5":
                try:
                    response = await self._run_model_tier("L4", gen_request)
                    response.daari_meta.warning = "l5_unavailable_fell_back_to_l4"
                except Exception:
                    response = await self._run_model_tier("L3", gen_request)
                    response.daari_meta.warning = "l5_unavailable_fell_back_to_l3"
            else:
                raise
        response = await self._maybe_escalate(gen_request, response, started, profile=profile)
        if (
            not request.meta.no_cache
            and not cache_skip
            and response.daari_meta.tier in {"L3", "L4", "L5"}
            and response.content.strip()
        ):
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
        # Longest trigger wins so "@mcp:demo" beats "@mcp".
        candidates: list[tuple[int, str]] = []
        for provider_id, triggers in self.integration_triggers.items():
            for trigger in triggers or []:
                normalized = trigger.strip().lower()
                if normalized and text_lower.startswith(normalized):
                    candidates.append((len(normalized), provider_id))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    async def stream_openai_chunks(self, request: InternalRequest) -> AsyncIterator[str]:
        """Emit OpenAI-compatible SSE chunks (strict shape for Cursor and other clients)."""
        from daari.gateway.content import sanitize_messages_for_ollama
        from daari.gateway.request_log import log_gateway_event

        started = time.perf_counter()
        created = int(time.time())
        chunk_id = f"chatcmpl-{int(time.time() * 1000)}"
        client_model = request.model or self.ollama_l3.default_model
        profile = build_prompt_profile(request)
        trace = start_trace() if self.trace_store is not None else None
        add_step(
            "profile",
            category=profile.category,
            complexity=profile.complexity,
            prompt_tokens_est=profile.prompt_tokens_est,
            stream=True,
        )
        profile = await self._apply_learned_route(request, profile)

        def finish_trace(tier: str | None) -> None:
            if trace is not None:
                self.trace_store.save(trace, tier=tier, category=profile.category)
            end_trace()

        await self._refresh_warm_models()
        tier_chain = self._stream_tier_chain(request, profile)
        # Agent flows (tools passed through by the gateway, or tool history)
        # keep the full tool protocol; Ask flows get plain-text sanitization.
        agent_flow = bool(request.tools) or request.has_tool_calls_in_history
        # ADR-0004: agent turns skip L0 entirely; explicit no-cache and
        # category cache-skip policies also bypass.
        cacheable = (
            not agent_flow
            and not request.meta.no_cache
            and not self._category_cache_skip(profile)
        )
        stream_request = request.model_copy(deep=True)
        if not agent_flow:
            stream_request.tools = None
            stream_request.messages = sanitize_messages_for_ollama(stream_request.messages)
            stream_request = self._optimize_context(stream_request)
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
                cached = self.cache.get(request, max_age=self._category_cache_max_age(profile))
            except Exception:
                cached = None
            add_step("l0_lookup", hit=cached is not None)
            if cached is not None and cached.content.strip():
                latency_ms = int((time.perf_counter() - started) * 1000)
                self.metrics.record("L0", cache_hit=True, latency_ms=latency_ms)
                if self.usage_ledger is not None:
                    self.usage_ledger.record(
                        tier="L0",
                        cache_hit=True,
                        prompt_chars=prompt_chars,
                        completion_chars=len(cached.content),
                        client_id=request.meta.client_id,
                    )
                log_gateway_event("stream_cache_hit", {"tier": "L0", "model": client_model})
                yield f"data: {json.dumps(chunk_payload(delta={'role': 'assistant'}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={'content': cached.content}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={}, finish_reason='stop'))}\n\n"
                yield usage_chunk(len(cached.content))
                yield "data: [DONE]\n\n"
                add_step("served", tier="L0", cache_hit=True, latency_ms=latency_ms)
                finish_trace("L0")
                return

            # L1 semantic lookup (issue #43): parity with the non-stream path.
            # One nearest() call serves both the hit path and the draft band.
            try:
                nearest_response, nearest_similarity = await self.semantic_cache.nearest(
                    request, max_age=self._category_cache_max_age(profile)
                )
            except Exception:
                nearest_response, nearest_similarity = None, 0.0
            l1_hit = (
                nearest_response is not None
                and nearest_similarity
                >= self._l1_threshold_for_category(
                    profile.category if profile is not None else None
                )
                and bool(nearest_response.content.strip())
            )
            add_step("l1_lookup", hit=l1_hit, similarity=round(nearest_similarity, 4))
            if l1_hit:
                latency_ms = int((time.perf_counter() - started) * 1000)
                self.metrics.record("L1", cache_hit=True, latency_ms=latency_ms)
                if self.usage_ledger is not None:
                    self.usage_ledger.record(
                        tier="L1",
                        cache_hit=True,
                        prompt_chars=prompt_chars,
                        completion_chars=len(nearest_response.content),
                        client_id=request.meta.client_id,
                    )
                log_gateway_event("stream_cache_hit", {"tier": "L1", "model": client_model})
                yield f"data: {json.dumps(chunk_payload(delta={'role': 'assistant'}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={'content': nearest_response.content}))}\n\n"
                yield f"data: {json.dumps(chunk_payload(delta={}, finish_reason='stop'))}\n\n"
                yield usage_chunk(len(nearest_response.content))
                yield "data: [DONE]\n\n"
                add_step("served", tier="L1", cache_hit=True, latency_ms=latency_ms)
                finish_trace("L1")
                self._maybe_shadow_check(request, nearest_response.content, profile)
                return
            if (
                nearest_response is not None
                and nearest_similarity >= self.l1_draft_threshold
                and nearest_response.content.strip()
            ):
                # Draft only affects generation; cache keys use the original request.
                stream_request.messages = [
                    *stream_request.messages,
                    Message(
                        role="system",
                        content=_draft_hint(nearest_response.content, nearest_similarity),
                    ),
                ]
                add_step("draft_injected", similarity=round(nearest_similarity, 4))

        last_error: Exception | None = None
        for tier_index, tier in enumerate(tier_chain):
            stream_executor = self._executor_for_tier(tier)
            ollama_model = stream_executor.default_model
            stream_request.model = ollama_model
            add_step("tier_attempt", tier=tier, stream=True)
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
                    add_step("fallback", from_tier=tier, error=str(exc)[:120])
                    continue
                yield f"data: {json.dumps({'error': f'stream failed: {exc}'})}\n\n"
                yield "data: [DONE]\n\n"
                add_step("served", tier=None, error=str(exc)[:120])
                finish_trace(None)
                return

            if not content_sent and tier_index < len(tier_chain) - 1:
                add_step("fallback", from_tier=tier, error="empty_response")
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
            if self.usage_ledger is not None:
                self.usage_ledger.record(
                    tier=tier,
                    cache_hit=False,
                    prompt_chars=prompt_chars,
                    completion_chars=completion_chars,
                    client_id=request.meta.client_id,
                )
            if self.feedback_store is not None:
                try:
                    self.feedback_store.record_outcome(
                        trace_id=trace.trace_id if trace is not None else None,
                        category=profile.category,
                        complexity=profile.complexity,
                        tier=tier,
                        confidence=None,
                        escalated=False,
                        latency_ms=latency_ms,
                    )
                except Exception:
                    pass
            if (
                self.example_store is not None
                and not tool_calls_sent
                and not request.tools
                and not request.has_tool_calls_in_history
                and streamed_text.strip()
            ):
                try:
                    self.example_store.record(
                        trace_id=trace.trace_id if trace is not None else None,
                        category=profile.category,
                        complexity=profile.complexity,
                        tier=tier,
                        model=ollama_model,
                        messages=[
                            {"role": message.role, "content": message.content}
                            for message in request.messages
                            if message.content
                        ],
                        completion=streamed_text,
                    )
                except Exception:
                    pass
            if cacheable and not tool_calls_sent and streamed_text.strip() and tier in {"L3", "L4", "L5"}:
                streamed_response = InternalResponse(
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
                )
                try:
                    self.cache.put(request, streamed_response)
                except Exception:
                    pass
                # L1 write-back happens after [DONE] was yielded, so it never
                # delays chunk delivery to the client.
                try:
                    await self.semantic_cache.put(request, streamed_response)
                except Exception:
                    pass
            add_step("served", tier=tier, cache_hit=False, latency_ms=latency_ms)
            finish_trace(tier)
            return

        end_trace()
        if last_error is not None:
            raise last_error

    def _stream_tier_chain(
        self, request: InternalRequest, profile: PromptProfile | None = None
    ) -> list[str]:
        initial = self._choose_initial_tier(request, profile)
        chain = [initial]
        if initial == "L5":
            chain.extend(["L4", "L3"])
        elif initial == "L4":
            chain.append("L3")
        deduped: list[str] = []
        for tier in chain:
            if tier not in deduped:
                deduped.append(tier)
        return self._filter_capable_tiers(deduped, request)

    async def stream_anthropic_events(self, request: InternalRequest) -> AsyncIterator[str]:
        """Emit Anthropic-compatible SSE events with daari metadata.

        Parity with the OpenAI stream path (issue #5): tier fallback via
        _stream_tier_chain, message sanitization before Ollama, and chars/4
        usage estimates instead of hardcoded zeros.
        """
        from daari.gateway.content import sanitize_messages_for_ollama
        from daari.gateway.request_log import log_gateway_event

        message_id = f"msg_{int(time.time() * 1000)}"
        await self._refresh_warm_models()
        # Parity with the OpenAI stream path (issue #101): category policies,
        # learned routing, and latency step-down all key off the profile.
        profile = build_prompt_profile(request)
        profile = await self._apply_learned_route(request, profile)
        tier_chain = self._stream_tier_chain(request, profile)
        # Agent flows (issue #84: Claude Code tool turns) keep the full tool
        # protocol; plain chat gets sanitization + context optimization.
        agent_flow = bool(request.tools) or request.has_tool_calls_in_history
        stream_request = request.model_copy(deep=True)
        if not agent_flow:
            stream_request.tools = None
            stream_request.messages = sanitize_messages_for_ollama(stream_request.messages)
            stream_request = self._optimize_context(stream_request)
        prompt_chars = sum(len(message.content or "") for message in stream_request.messages)
        input_tokens = max(1, prompt_chars // 4)

        def sse(event_type: str, payload: dict[str, Any]) -> str:
            return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        stream_started = time.perf_counter()
        last_error: Exception | None = None
        for tier_index, tier in enumerate(tier_chain):
            stream_executor = self._executor_for_tier(tier)
            model_name = stream_executor.default_model
            stream_request.model = model_name
            meta = {
                "tier": tier,
                "executor": "ollama",
                "provider_id": f"ollama:{tier.lower()}",
                "model": model_name,
                "stream": True,
            }
            message_start = sse(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": message_id,
                        "type": "message",
                        "role": "assistant",
                        "model": model_name,
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": input_tokens, "output_tokens": 0},
                    },
                    "daari_meta": meta,
                },
            )

            def text_block_start(index: int) -> str:
                return sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "text", "text": ""},
                        "daari_meta": meta,
                    },
                )

            def block_stop(index: int) -> str:
                return sse(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": index, "daari_meta": meta},
                )

            pending: list[str] = []
            any_output = False
            text_block_open = False
            block_index = 0
            tool_use_sent = False
            completion_chars = 0
            try:
                async for event in stream_executor.stream(stream_request):
                    message = event.get("message", {})
                    delta = message.get("content", "")
                    raw_tool_calls = message.get("tool_calls")
                    if raw_tool_calls and agent_flow:
                        if not any_output:
                            pending.append(message_start)
                            any_output = True
                        if text_block_open:
                            pending.append(block_stop(block_index))
                            text_block_open = False
                            block_index += 1
                        for call in _openai_tool_call_deltas(raw_tool_calls):
                            pending.append(
                                sse(
                                    "content_block_start",
                                    {
                                        "type": "content_block_start",
                                        "index": block_index,
                                        "content_block": {
                                            "type": "tool_use",
                                            "id": call["id"],
                                            "name": call["function"]["name"],
                                            "input": {},
                                        },
                                        "daari_meta": meta,
                                    },
                                )
                            )
                            pending.append(
                                sse(
                                    "content_block_delta",
                                    {
                                        "type": "content_block_delta",
                                        "index": block_index,
                                        "delta": {
                                            "type": "input_json_delta",
                                            "partial_json": call["function"]["arguments"],
                                        },
                                        "daari_meta": meta,
                                    },
                                )
                            )
                            pending.append(block_stop(block_index))
                            block_index += 1
                        tool_use_sent = True
                    elif not delta and raw_tool_calls:
                        # Plain chat: model ignored the no-tools hint; degrade to text.
                        delta = json.dumps(raw_tool_calls)
                    if delta:
                        if not any_output:
                            pending.append(message_start)
                            any_output = True
                        if not text_block_open:
                            pending.append(text_block_start(block_index))
                            text_block_open = True
                        completion_chars += len(delta)
                        pending.append(
                            sse(
                                "content_block_delta",
                                {
                                    "type": "content_block_delta",
                                    "index": block_index,
                                    "delta": {"type": "text_delta", "text": delta},
                                    "daari_meta": meta,
                                },
                            )
                        )
                    if event.get("done"):
                        break
            except Exception as exc:
                last_error = exc
                log_gateway_event(
                    "anthropic_stream_attempt_failed",
                    {
                        "tier": tier,
                        "ollama_model": model_name,
                        # Timeouts stringify to "" (issue #101); the type name
                        # keeps the cause diagnosable.
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                )
                if tier_index < len(tier_chain) - 1:
                    continue
                raise

            if not any_output and tier_index < len(tier_chain) - 1:
                log_gateway_event(
                    "anthropic_stream_empty_retry",
                    {
                        "tier": tier,
                        "ollama_model": model_name,
                        "prompt_chars": prompt_chars,
                        "num_ctx": estimate_num_ctx(prompt_chars),
                        "agent_flow": agent_flow,
                    },
                )
                continue

            if not any_output:
                pending.append(message_start)
                pending.append(text_block_start(block_index))
                text_block_open = True
            for chunk in pending:
                yield chunk
            if text_block_open:
                yield block_stop(block_index)
            yield sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": "tool_use" if tool_use_sent else "end_turn",
                        "stop_sequence": None,
                    },
                    "usage": {"output_tokens": max(0, completion_chars // 4)},
                    "daari_meta": meta,
                },
            )
            yield sse("message_stop", {"type": "message_stop", "daari_meta": meta})
            # Mirror chat_completions_stream_done (issue #101) so the final
            # outcome of a fallback chain is visible in cursor-requests.log.
            log_gateway_event(
                "anthropic_stream_done",
                {
                    "tier": tier,
                    "ollama_model": model_name,
                    "latency_ms": int((time.perf_counter() - stream_started) * 1000),
                    "completion_chars": completion_chars,
                    "tool_use": tool_use_sent,
                    "agent_flow": agent_flow,
                    "empty": not any_output,
                },
            )
            return

        if last_error is not None:
            raise last_error

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

    def _optimize_context(self, request: InternalRequest) -> InternalRequest:
        if not self.context_optimizer_enabled:
            return request
        if request.tools or request.has_tool_calls_in_history:
            return request
        optimized, chars_before, chars_after = optimize_messages(
            request.messages,
            max_history_messages=self.context_max_history,
            squeeze_whitespace=self.context_squeeze_whitespace,
        )
        if chars_after >= chars_before and len(optimized) == len(request.messages):
            return request
        trimmed = request.model_copy(deep=True)
        trimmed.messages = optimized
        add_step("context_optimized", chars_before=chars_before, chars_after=chars_after)
        return trimmed

    _COMPACTION_PROMPT = (
        "Summarize the following conversation history in at most 150 words. "
        "Preserve decisions, facts, names, and code identifiers. Output only "
        "the summary.\n\n{history}"
    )
    _COMPACTION_CACHE_MAX = 64

    async def _compact_context(self, request: InternalRequest) -> InternalRequest:
        """Trust PRD T2b: summarize over-limit history instead of dropping it."""
        if (
            not self.context_compact
            or request.tools
            or request.has_tool_calls_in_history
        ):
            return request
        non_system = [(i, m) for i, m in enumerate(request.messages) if m.role != "system"]
        if len(non_system) <= self.context_max_history:
            return request

        old = non_system[: -self.context_max_history]
        old_indices = {index for index, _ in old}
        history_text = "\n".join(
            f"{message.role}: {message.content}" for _, message in old if message.content
        )
        if not history_text.strip():
            return request

        import hashlib as _hashlib

        prefix_key = _hashlib.sha256(history_text.encode("utf-8")).hexdigest()
        summary = self._compaction_cache.get(prefix_key)
        if summary is None:
            try:
                summary_request = InternalRequest(
                    messages=[
                        Message(
                            role="user",
                            content=self._COMPACTION_PROMPT.format(history=history_text),
                        )
                    ],
                    model=self.ollama_l3.default_model,
                    temperature=0.0,
                )
                summary_response = await self.ollama_l3.execute(summary_request)
                summary = summary_response.content.strip()
            except Exception:
                return request
            if not summary:
                return request
            self._compaction_cache[prefix_key] = summary
            while len(self._compaction_cache) > self._COMPACTION_CACHE_MAX:
                self._compaction_cache.pop(next(iter(self._compaction_cache)))

        chars_before = sum(len(m.content or "") for m in request.messages)
        compacted = request.model_copy(deep=True)
        kept: list[Message] = []
        summary_inserted = False
        for index, message in enumerate(compacted.messages):
            if index in old_indices:
                if not summary_inserted:
                    kept.append(
                        Message(
                            role="system",
                            content=f"[Earlier conversation summary] {summary}",
                        )
                    )
                    summary_inserted = True
                continue
            kept.append(message)
        compacted.messages = kept
        chars_after = sum(len(m.content or "") for m in kept)
        add_step(
            "context_compacted",
            turns_summarized=len(old),
            chars_before=chars_before,
            chars_after=chars_after,
        )
        return compacted

    async def _run_model_tier(self, tier: str, request: InternalRequest) -> InternalResponse:
        add_step("tier_attempt", tier=tier)
        request = await self._compact_context(request)
        request = self._optimize_context(request)
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

    _TIER_ORDER = ("L3", "L4", "L5")

    def _effective_tier_cap(self, request: InternalRequest) -> str | None:
        header_cap = (request.meta.tier_cap or "").upper()
        if header_cap in self._TIER_ORDER:
            return header_cap
        config_cap = (self.max_tier_for_chat or "").upper()
        if config_cap in self._TIER_ORDER:
            return config_cap
        return None

    def _cap_tier(self, tier: str, cap: str | None) -> str:
        if cap is None or tier not in self._TIER_ORDER:
            return tier
        if self._TIER_ORDER.index(tier) > self._TIER_ORDER.index(cap):
            return cap
        return tier

    def _choose_initial_tier(
        self, request: InternalRequest, profile: PromptProfile | None = None
    ) -> str:
        override = (request.meta.tier_override or "").upper()
        if override in {"L3", "L4", "L5"}:
            # Still respect capability filter for explicit overrides when possible.
            capable = self._filter_capable_tiers([override, "L5", "L4", "L3"], request)
            return capable[0] if capable else override
        tier = self._choose_uncapped_tier(request, profile)
        tier = self._cap_tier(tier, self._effective_tier_cap(request))
        tier = self._apply_latency_budget(tier, request, profile)
        capable = self._filter_capable_tiers([tier, "L5", "L4", "L3"], request)
        return capable[0] if capable else tier

    @staticmethod
    def _policy_attr(policy: Any, name: str) -> Any:
        if policy is None:
            return None
        if isinstance(policy, dict):
            return policy.get(name)
        return getattr(policy, name, None)

    def _effective_latency_budget(
        self, request: InternalRequest, profile: PromptProfile | None = None
    ) -> int:
        """Header > category policy > global setting. 0 disables."""
        header_budget = request.meta.latency_budget_ms
        if isinstance(header_budget, int) and header_budget > 0:
            return header_budget
        policy = self._policy_for(profile or build_prompt_profile(request))
        policy_budget = self._policy_attr(policy, "latency_budget_ms")
        if isinstance(policy_budget, (int, float)) and policy_budget > 0:
            return int(policy_budget)
        return self.latency_budget_ms

    _TIER_SPEED_ORDER = ["L3", "L4", "L5"]  # fastest first

    def _apply_latency_budget(
        self, tier: str, request: InternalRequest, profile: PromptProfile | None = None
    ) -> str:
        """Trust PRD T3b: step down to a faster tier when the profiled model
        would blow the latency budget."""
        if self.model_profile_store is None:
            return tier
        budget = self._effective_latency_budget(request, profile)
        if budget <= 0:
            return tier
        try:
            expected = self.model_profile_store.latency_ms_for(
                self._executor_for_tier(tier).default_model
            )
        except Exception:
            return tier
        if expected is None or expected <= budget:
            return tier
        # Walk faster tiers below the current one; pick the first that fits.
        candidates = self._TIER_SPEED_ORDER[: self._TIER_SPEED_ORDER.index(tier)]
        for faster in reversed(candidates):
            faster_expected = self.model_profile_store.latency_ms_for(
                self._executor_for_tier(faster).default_model
            )
            if faster_expected is None or faster_expected <= budget:
                add_step(
                    "latency_budget",
                    budget_ms=budget,
                    expected_ms=expected,
                    downgraded_from=tier,
                    tier=faster,
                )
                return faster
        return tier

    def _choose_uncapped_tier(
        self, request: InternalRequest, profile: PromptProfile | None = None
    ) -> str:
        policy = self._policy_for(profile or build_prompt_profile(request))
        policy_tier = getattr(policy, "tier", None) if policy is not None else None
        if policy_tier in {"L3", "L4", "L5"}:
            return policy_tier
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
        elif self.model_preference == "accuracy":
            scores = {"L3": l3_weight.get("accuracy", 0.0), "L4": l4_weight.get("accuracy", 0.0), "L5": l5_weight.get("accuracy", 0.0)}
        else:
            # Balanced: blend both dimensions and pick the stronger score.
            scores = {
                "L3": 0.5 * l3_weight.get("latency", 0.0) + 0.5 * l3_weight.get("accuracy", 0.0),
                "L4": 0.5 * l4_weight.get("latency", 0.0) + 0.5 * l4_weight.get("accuracy", 0.0),
                "L5": 0.5 * l5_weight.get("latency", 0.0) + 0.5 * l5_weight.get("accuracy", 0.0),
            }
        return self._pick_with_warm_preference(scores)

    # Small enough to only decide otherwise-tied choices (Trust PRD T3c).
    _WARM_BONUS = 0.001

    def _pick_with_warm_preference(self, scores: dict[str, float]) -> str:
        warm = self._warm_models
        if self.warm_tracker is not None:
            warm = warm | self.warm_tracker.get()
        if warm:
            names = {
                "L3": self.ollama_l3.default_model,
                "L4": self.ollama_l4.default_model,
                "L5": self.ollama_l5.default_model,
            }
            boosted = {
                tier: score + (self._WARM_BONUS if names[tier] in warm else 0.0)
                for tier, score in scores.items()
            }
            choice = max(boosted, key=boosted.get)
            if names[choice] in warm and choice != max(scores, key=scores.get):
                add_step("warm_preference", tier=choice, model=names[choice])
            return choice
        return max(scores, key=scores.get)

    @staticmethod
    def _last_user_text(messages: list[Message]) -> str:
        if not messages:
            return ""
        for message in reversed(messages):
            if message.role == "user":
                return message.content or ""
        return messages[-1].content or ""

    def _confidence_threshold_for(
        self, request: InternalRequest, profile: PromptProfile | None
    ) -> float:
        """Tuned per-category threshold (D1c); base for overrides or no tuner."""
        base = self.confidence_threshold
        if self.tuner is None or profile is None or request.meta.tier_override:
            return base
        try:
            tuned = self.tuner.threshold_for(profile.category)
        except Exception:
            return base
        if tuned != base:
            add_step("tuner", category=profile.category, base=base, tuned=tuned)
        return tuned

    async def _maybe_escalate(
        self,
        request: InternalRequest,
        response: InternalResponse,
        started: float,
        profile: PromptProfile | None = None,
    ) -> InternalResponse:
        threshold = self._confidence_threshold_for(request, profile)
        confidence = score_l3_confidence(response.content)
        response.daari_meta.confidence = confidence

        if confidence >= threshold:
            return response

        tier_chain = ["L3", "L4", "L5"]
        cap = self._effective_tier_cap(request)
        if cap in tier_chain:
            tier_chain = tier_chain[: tier_chain.index(cap) + 1]
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
                    if next_confidence >= threshold:
                        return next_response
                    response = next_response
                    confidence = next_confidence
                except Exception:
                    response.daari_meta.warning = "below_confidence_threshold"
                    return response

        # L5.5 — org inference pool before paying frontier (issue #118).
        if self.org_pool is not None:
            try:
                add_step("escalate", to="L5-org", local_confidence=confidence)
                pool_request = request.model_copy(deep=True)
                pool_request.model = self.org_pool.default_model
                pool_response = await self.org_pool.execute(pool_request)
                pool_confidence = score_l3_confidence(pool_response.content)
                pool_response.daari_meta.confidence = pool_confidence
                pool_response.daari_meta.tier = getattr(self.org_pool, "tier", None) or "L5-org"
                pool_response.daari_meta.escalated_from = response.daari_meta.tier
                if pool_confidence >= threshold:
                    return pool_response
                response = pool_response
                confidence = pool_confidence
            except Exception:
                add_step("org_pool_failed")

        if request.meta.no_frontier or not self.frontier_enabled:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        if self.frontier is None or not self.frontier.api_key:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        budget_state = self._frontier_budget_state()
        if budget_state == "exceeded":
            add_step("budget_check", exceeded=True)
            response.daari_meta.warning = "frontier_budget_exceeded"
            return response
        if budget_state == "soft":
            add_step("budget_check", exceeded=False, soft=True)

        add_step("escalate", to="L6", local_confidence=confidence)
        try:
            l6_request = self._slim_for_frontier(request)
            l6_request = await self._compress_for_frontier(l6_request)
            l6_request = self._scrub_for_frontier(l6_request)
            l6_response = await self.frontier.execute(
                l6_request,
                escalated_from=response.daari_meta.tier,
                local_confidence=confidence,
            )
            l6_response.daari_meta.prompt_chars = sum(
                len(message.content or "") for message in l6_request.messages
            )
            if budget_state == "soft":
                l6_response.daari_meta.warning = "frontier_budget_warning"
            self.metrics.record_escalation()
            return l6_response
        except Exception:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

    def _slim_for_frontier(self, request: InternalRequest) -> InternalRequest:
        """Cut frontier token spend: drop daari-internal hints, collapse
        duplicate system prompts, and trim history (issue #34)."""
        if not self.frontier_slim_prompts or request.tools or request.has_tool_calls_in_history:
            return request
        # Lazy import: gateway.openai imports this module at load time.
        from daari.gateway.openai import NO_TOOLS_HINT

        chars_before = sum(len(message.content or "") for message in request.messages)
        slimmed = request.model_copy(deep=True)
        kept = []
        seen_system: set[str] = set()
        for message in slimmed.messages:
            if message.role == "system":
                content = (message.content or "").strip()
                if content == NO_TOOLS_HINT.strip():
                    continue
                if content in seen_system:
                    continue
                seen_system.add(content)
            kept.append(message)
        slimmed.messages, _, chars_after = optimize_messages(
            kept,
            max_history_messages=self.frontier_max_history,
            squeeze_whitespace=True,
        )
        add_step("frontier_slimmed", chars_before=chars_before, chars_after=chars_after)
        return slimmed

    async def _compress_for_frontier(self, request: InternalRequest) -> InternalRequest:
        """Trust PRD T2c: relevance-prune long context before paying L6 rates."""
        if not self.frontier_compress or request.tools or request.has_tool_calls_in_history:
            return request
        try:
            from daari.router.compress import compress_messages

            compressed, chars_before, chars_after = await compress_messages(
                request.messages,
                embedder=self.semantic_cache.embedder,
                target_ratio=self.frontier_compress_ratio,
            )
        except Exception:
            return request
        if chars_after >= chars_before:
            return request
        result = request.model_copy(deep=True)
        result.messages = compressed
        add_step("frontier_compressed", chars_before=chars_before, chars_after=chars_after)
        return result

    def _scrub_for_frontier(self, request: InternalRequest) -> InternalRequest:
        """Trust PRD T5c: PII never leaves the device unless opted out."""
        if not self.frontier_scrub_pii:
            return request
        try:
            from daari.gateway.pii import scrub_messages

            scrubbed, counts = scrub_messages(request.messages)
        except Exception:
            return request
        if not counts:
            return request
        result = request.model_copy(deep=True)
        result.messages = scrubbed
        add_step("pii_scrub", **counts)
        return result

    def _frontier_budget_state(self) -> str:
        """'ok' | 'soft' | 'exceeded' across daily and monthly caps (T5a)."""
        if self.usage_ledger is None:
            return "ok"
        state = "ok"
        windows: list[tuple[float, Any]] = []
        if self.frontier_daily_budget_usd > 0:
            windows.append(
                (self.frontier_daily_budget_usd, self.usage_ledger.frontier_spend_usd)
            )
        if self.frontier_monthly_budget_usd > 0:
            windows.append(
                (
                    self.frontier_monthly_budget_usd,
                    getattr(self.usage_ledger, "frontier_spend_usd_month", None),
                )
            )
        for budget, spend_fn in windows:
            if spend_fn is None:
                continue
            try:
                spend = spend_fn(price_per_1k_tokens=self.frontier_price_per_1k_tokens)
            except Exception:
                continue
            if spend >= budget:
                return "exceeded"
            if spend >= budget * self.frontier_soft_budget_ratio:
                state = "soft"
        return state

    def _frontier_budget_exceeded(self) -> bool:
        return self._frontier_budget_state() == "exceeded"

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
        return categorize(text)

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
    virtual_key_store: Any | None = None
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
        self.cache = ExactCache(
            path=str(l0_path),
            enabled=self.settings.cache.l0.enabled,
            ttl_seconds=self.settings.cache.l0.ttl_seconds,
        )
        self.semantic_cache = SemanticCache(
            path=str(l1_path),
            embedder=OllamaEmbedder(
                base_url=self.settings.ollama.base_url.rstrip("/"),
                model=self.settings.cache.l1.embedding_model,
                cache_size=self.settings.cache.l1.embed_cache_size,
            ),
            enabled=self.settings.cache.l1.enabled,
            similarity_threshold=self.settings.cache.l1.similarity_threshold,
            max_entries=self.settings.cache.l1.max_entries,
            ttl_seconds=self.settings.cache.l1.ttl_seconds,
            normalize_inputs=self.settings.cache.l1.normalize_inputs,
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
                embedder=OllamaEmbedder(
                    settings.ollama.base_url,
                    settings.cache.l1.embedding_model,
                    cache_size=settings.cache.l1.embed_cache_size,
                ),
                similarity_threshold=settings.cache.l1.similarity_threshold,
            )
        learning_enabled = settings.enterprise.learning_enabled or settings.enterprise.learning.enabled
        if learning_enabled and settings.enterprise.learning_url:
            org_learning_client = OrgLearningClient(
                base_url=settings.enterprise.learning_url,
                token=settings.enterprise.learning_token or settings.enterprise.org_token,
                timeout_seconds=settings.enterprise.learning_timeout_seconds,
                enabled=True,
            )
        cache = _build_l0_cache(settings, l0_path)
        embedder = OllamaEmbedder(
            base_url=settings.ollama.base_url.rstrip("/"),
            model=settings.cache.l1.embedding_model,
            cache_size=settings.cache.l1.embed_cache_size,
        )
        semantic_cache = SemanticCache(
            path=str(l1_path),
            embedder=embedder,
            enabled=settings.cache.l1.enabled,
            similarity_threshold=settings.cache.l1.similarity_threshold,
            max_entries=settings.cache.l1.max_entries,
            ttl_seconds=settings.cache.l1.ttl_seconds,
            normalize_inputs=settings.cache.l1.normalize_inputs,
        )
        command_context = cls._build_command_context_store(settings, context_path)
        def tier_executor(tier: str, ollama_model: str) -> OllamaExecutor | MLXExecutor:
            # MLX backend (issue #97): tiers mapped in mlx.models are served by
            # mlx_lm.server; the rest stay on Ollama.
            mlx_model = settings.mlx.models.get(tier) if settings.mlx.enabled else None
            if mlx_model:
                return MLXExecutor(
                    base_url=settings.mlx.base_url.rstrip("/"),
                    default_model=mlx_model,
                    tier=tier,
                )
            return OllamaExecutor(
                base_url=settings.ollama.base_url.rstrip("/"),
                default_model=ollama_model,
                tier=tier,
            )

        ollama_l3 = tier_executor("L3", settings.models.l3)
        ollama_l4 = tier_executor("L4", settings.models.l4)
        ollama_l5 = tier_executor("L5", settings.models.l5)
        org_pool_executor: OllamaExecutor | MLXExecutor | None = None
        org_pool_cfg = settings.routing.org_pool
        if org_pool_cfg.enabled and org_pool_cfg.base_url.strip():
            org_pool_executor = OllamaExecutor(
                base_url=org_pool_cfg.base_url.rstrip("/"),
                default_model=org_pool_cfg.model or settings.models.l5,
                tier=org_pool_cfg.tier or "L5-org",
            )
        frontier = FrontierExecutor(
            base_url=settings.frontier.base_url.rstrip("/"),
            default_model=settings.frontier.model,
            api_key=settings.resolve_frontier_api_key(),
            provider=settings.frontier.provider,
            prompt_cache=settings.frontier.prompt_cache,
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
        from daari.providers.mcp_egress import build_mcp_providers

        mcp_providers = build_mcp_providers(settings.integrations.mcp_servers)
        mcp_triggers: dict[str, list[str]] = {}
        for mcp_provider in mcp_providers:
            providers.register(mcp_provider)
            mcp_triggers[mcp_provider.id] = list(mcp_provider.server.triggers)
        metrics = Metrics()
        if (
            settings.observability.backend == "postgres"
            and settings.observability.postgres_url.strip()
        ):
            from daari.observability.postgres_trace import PostgresTraceStore
            from daari.observability.postgres_usage import PostgresUsageLedger

            usage_ledger = PostgresUsageLedger(
                settings.observability.postgres_url,
                enabled=settings.usage.enabled,
            )
            trace_store = PostgresTraceStore(
                settings.observability.postgres_url,
                enabled=settings.trace.enabled,
                max_entries=settings.trace.max_entries,
            )
        else:
            usage_ledger = UsageLedger(
                path=settings.usage_ledger_path,
                enabled=settings.usage.enabled,
            )
            trace_store = TraceStore(
                path=settings.trace_store_path,
                enabled=settings.trace.enabled,
                max_entries=settings.trace.max_entries,
            )
        from daari.learning.feedback import FeedbackStore

        feedback_store = FeedbackStore(
            settings.feedback_store_path,
            enabled=settings.learning.enabled,
            max_rows=settings.learning.max_rows,
        )
        example_store = None
        if settings.learning.capture_examples:
            from daari.learning.examples import ExampleStore

            example_store = ExampleStore(
                settings.example_store_path,
                max_rows=settings.learning.examples_max_rows,
            )
        from daari.router.model_profile import ModelProfileStore, WarmModelTracker

        model_profile_store = ModelProfileStore()
        warm_tracker = (
            WarmModelTracker(settings.ollama.base_url.rstrip("/"))
            if settings.routing.warm_model_preference
            else None
        )
        learned_router = None
        if settings.routing.learned_router:
            from daari.learning.router_model import LearnedRouter

            learned_router = LearnedRouter(
                settings.learning.router_model_path,
                min_samples=settings.learning.router_min_samples,
            )
        tuner = None
        if settings.learning.auto_tune and settings.learning.enabled:
            from daari.learning.tuner import RoutingTuner

            tuner = RoutingTuner(
                feedback_store,
                base_threshold=settings.routing.confidence_threshold,
                min_samples=settings.learning.tuner_min_samples,
            )
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
                **mcp_triggers,
            },
            skills_system_prefix=settings.skills_system_prefix,
            org_cache_client=org_cache_client,
            org_learning_client=org_learning_client,
            org_learning_enabled=learning_enabled,
            usage_ledger=usage_ledger,
            category_policies=dict(settings.routing.category_policies),
            trace_store=trace_store,
            feedback_store=feedback_store,
            tuner=tuner,
            example_store=example_store,
            l1_shadow_sample_rate=settings.cache.l1.shadow_sample_rate,
            model_profile_store=model_profile_store,
            warm_tracker=warm_tracker,
            learned_router=learned_router,
            latency_budget_ms=settings.routing.latency_budget_ms,
            frontier_daily_budget_usd=settings.frontier.daily_budget_usd,
            frontier_monthly_budget_usd=settings.frontier.monthly_budget_usd,
            frontier_soft_budget_ratio=settings.frontier.soft_budget_ratio,
            frontier_price_per_1k_tokens=settings.frontier.price_per_1k_tokens,
            frontier_scrub_pii=settings.frontier.scrub_pii,
            frontier_slim_prompts=settings.frontier.slim_prompts,
            frontier_max_history=settings.frontier.max_history_messages,
            frontier_enabled=settings.frontier.enabled,
            confidence_threshold=settings.routing.confidence_threshold,
            l1_draft_threshold=settings.cache.l1.draft_threshold,
            context_optimizer_enabled=settings.context_optimizer.enabled,
            context_max_history=settings.context_optimizer.max_history_messages,
            context_squeeze_whitespace=settings.context_optimizer.squeeze_whitespace,
            context_compact=settings.context_optimizer.compact,
            frontier_compress=settings.frontier.compress_context,
            frontier_compress_ratio=settings.frontier.compress_target_ratio,
            max_tier_for_chat=settings.routing.max_tier_for_chat,
            guardrails=_guardrails_from_settings(settings),
            capability_catalog=_catalog_from_settings(settings),
            otel_enabled=bool(settings.observability.otel),
            org_pool=org_pool_executor,
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
