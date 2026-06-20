from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable

import httpx

from daari.cache.command_context import CommandContextStore
from daari.cache.exact import ExactCache
from daari.cache.semantic import OllamaEmbedder, SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.policy.engine import PolicyEngine
from daari.providers.registry import ProviderRegistry
from daari.rules.dev_commands import DevCommandMatch, match_dev_command
from daari.rules.engine import apply_l2_rules
from daari.router.confidence import score_l3_confidence
from daari.router.frontier import FrontierExecutor
from daari.tools.shell import ShellExecutor


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
        ollama: OllamaExecutor | None = None,
        frontier: FrontierExecutor | None = None,
        command_context: CommandContextStore | None = None,
        shell_executor: ShellExecutor | None = None,
        policy: PolicyEngine | None = None,
        provider_registry: ProviderRegistry | None = None,
        model_preference: str = "balanced",
        model_weights: dict[str, dict[str, float]] | None = None,
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
        self.metrics = metrics
        self.frontier = frontier
        self.command_context = command_context
        self.shell_executor = shell_executor or ShellExecutor()
        self.policy = policy or PolicyEngine()
        self.provider_registry = provider_registry or ProviderRegistry()
        self.model_preference = model_preference
        self.model_weights = model_weights or {}
        self.frontier_enabled = frontier_enabled
        self.confidence_threshold = confidence_threshold

    @property
    def ollama(self) -> OllamaExecutor:
        return self.ollama_l3

    async def route(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()
        last_user = self._last_user_text(request.messages)

        if request.has_tool_calls_in_history:
            response = await self._run_model_tier("L3", request)
            self._record(response, started)
            return response

        dev_match = match_dev_command(last_user)

        if not request.meta.no_cache:
            cached = self.cache.get(request)
            if cached is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                cached.daari_meta.tier = "L0"
                cached.daari_meta.cache_hit = True
                cached.daari_meta.executor = "cache"
                cached.daari_meta.provider_id = "cache"
                cached.daari_meta.latency_ms = latency_ms
                self.metrics.record("L0", cache_hit=True, latency_ms=latency_ms)
                return cached

        ccs_hit = self._resolve_ccs_hit(dev_match, request)
        if ccs_hit is not None:
            latency_ms = int((time.perf_counter() - started) * 1000)
            ccs_hit.daari_meta.latency_ms = latency_ms
            self.metrics.record("CCS", cache_hit=True, latency_ms=latency_ms)
            return ccs_hit

        if not request.meta.no_cache:
            semantic_hit, _similarity = await self.semantic_cache.get(request)
            if semantic_hit is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                semantic_hit.daari_meta.tier = "L1"
                semantic_hit.daari_meta.cache_hit = True
                semantic_hit.daari_meta.executor = "cache"
                semantic_hit.daari_meta.provider_id = "cache"
                semantic_hit.daari_meta.latency_ms = latency_ms
                semantic_hit.daari_meta.task_type = "cache_hit"
                self.metrics.record("L1", cache_hit=True, latency_ms=latency_ms)
                return semantic_hit

        if dev_match is not None and dev_match.action == "execute" and dev_match.command:
            policy = self.policy.evaluate(dev_match.command, confirmed=request.meta.confirm_tool)
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
                ask = InternalResponse(
                    content=(
                        "Command requires confirmation. Re-send the same request with "
                        "header X-Daari-Confirm-Tool: true."
                    ),
                    model=request.model,
                    daari_meta=DaariMeta(
                        tier="Lt",
                        executor="policy",
                        provider_id="policy",
                        task_type="tool",
                        rule_id=dev_match.rule_id,
                        policy="ask",
                        pending_command=dev_match.command,
                    ),
                )
                self._record(ask, started)
                return ask

            shell = await self.shell_executor.run(dev_match.command, cwd=os.getcwd())
            if self.command_context and not request.meta.no_cache:
                self.command_context.put(
                    repo_root=os.getcwd(),
                    cwd=os.getcwd(),
                    command=dev_match.command,
                    output=shell.output,
                    exit_code=shell.exit_code,
                    ttl_seconds=dev_match.ttl_seconds,
                )
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

        initial_tier = self._choose_initial_tier(request)
        try:
            response = await self._run_model_tier(initial_tier, request)
        except Exception:
            if initial_tier == "L4":
                response = await self._run_model_tier("L3", request)
                response.daari_meta.warning = "l4_unavailable_fell_back_to_l3"
            else:
                raise
        response = await self._maybe_escalate(request, response, started)
        if not request.meta.no_cache and response.daari_meta.tier in {"L3", "L4"}:
            self.cache.put(request, response)
            await self.semantic_cache.put(request, response)
        self._record(response, started)
        return response

    async def stream_openai_chunks(self, request: InternalRequest) -> AsyncIterator[str]:
        """Basic SSE passthrough for streaming requests via Ollama."""
        created = int(time.time())
        chunk_id = f"chatcmpl-{int(time.time() * 1000)}"
        async for event in self.ollama_l3.stream(request):
            delta = event.get("message", {}).get("content", "")
            if delta:
                payload = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model or self.ollama_l3.default_model,
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload)}\n\n"
            if event.get("done"):
                break
        done_payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model or self.ollama_l3.default_model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        yield "data: [DONE]\n\n"

    def _resolve_ccs_hit(self, dev_match: DevCommandMatch | None, request: InternalRequest) -> InternalResponse | None:
        if self.command_context is None or request.meta.no_cache:
            return None

        if dev_match is None:
            return None

        known_commands = ["git status", "git diff", "pytest", "eslint ."]
        if dev_match.action == "ccs_read":
            for command in known_commands:
                entry = self.command_context.get(repo_root=os.getcwd(), cwd=os.getcwd(), command=command)
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
            entry = self.command_context.get(
                repo_root=os.getcwd(),
                cwd=os.getcwd(),
                command=dev_match.command,
            )
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
            response = await provider.execute(provider_request)
            response.daari_meta.tier = tier
            return response
        if tier == "L4":
            req = request.model_copy(deep=True)
            req.model = self.ollama_l4.default_model
            return await self.ollama_l4.execute(req)
        return await self.ollama_l3.execute(request)

    def _choose_initial_tier(self, request: InternalRequest) -> str:
        override = (request.meta.tier_override or "").upper()
        if override in {"L3", "L4"}:
            return override
        text = self._last_user_text(request.messages)
        words = len(re.findall(r"\S+", text))
        if words > 250:
            return "L4"
        if words <= 12:
            return "L3"

        l3_name = self.ollama_l3.default_model
        l4_name = self.ollama_l4.default_model
        l3_weight = self.model_weights.get(l3_name, {"latency": 0.8, "accuracy": 0.6})
        l4_weight = self.model_weights.get(l4_name, {"latency": 0.5, "accuracy": 0.8})

        if self.model_preference == "latency":
            return "L3" if l3_weight.get("latency", 0.0) >= l4_weight.get("latency", 0.0) else "L4"
        if self.model_preference == "accuracy":
            return "L3" if l3_weight.get("accuracy", 0.0) >= l4_weight.get("accuracy", 0.0) else "L4"

        # Balanced: blend both dimensions and pick the stronger score.
        l3_score = 0.5 * l3_weight.get("latency", 0.0) + 0.5 * l3_weight.get("accuracy", 0.0)
        l4_score = 0.5 * l4_weight.get("latency", 0.0) + 0.5 * l4_weight.get("accuracy", 0.0)
        return "L3" if l3_score >= l4_score else "L4"

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

        if response.daari_meta.tier == "L3":
            try:
                l4_request = request.model_copy(deep=True)
                l4_request.model = self.ollama_l4.default_model
                l4_response = await self._run_model_tier("L4", l4_request)
                l4_confidence = score_l3_confidence(l4_response.content)
                l4_response.daari_meta.confidence = l4_confidence
                if l4_confidence >= self.confidence_threshold:
                    return l4_response
                response = l4_response
                confidence = l4_confidence
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
                escalated_from="L3",
                local_confidence=confidence,
            )
            return l6_response
        except Exception:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

    def _record(self, response: InternalResponse, started: float) -> None:
        if response.daari_meta.tier in ("L0", "L1"):
            return
        latency_ms = response.daari_meta.latency_ms or int((time.perf_counter() - started) * 1000)
        self.metrics.record(
            response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            latency_ms=latency_ms,
        )


@dataclass
class AppContext:
    settings: Settings
    cache: ExactCache
    semantic_cache: SemanticCache
    command_context: CommandContextStore
    ollama_l3: OllamaExecutor
    ollama_l4: OllamaExecutor
    frontier: FrontierExecutor
    shell_executor: ShellExecutor
    policy: PolicyEngine
    providers: ProviderRegistry
    metrics: Metrics
    router: Router

    @property
    def ollama(self) -> OllamaExecutor:
        return self.ollama_l3

    @classmethod
    def from_settings(cls, settings: Settings) -> AppContext:
        cache = ExactCache(
            path=str(settings.l0_cache_path),
            enabled=settings.cache.l0.enabled,
        )
        embedder = OllamaEmbedder(
            base_url=settings.ollama.base_url.rstrip("/"),
            model=settings.cache.l1.embedding_model,
        )
        semantic_cache = SemanticCache(
            path=str(settings.l1_cache_path),
            embedder=embedder,
            enabled=settings.cache.l1.enabled,
            similarity_threshold=settings.cache.l1.similarity_threshold,
            max_entries=settings.cache.l1.max_entries,
        )
        try:
            command_context = CommandContextStore(
                root=settings.context_store_path,
                enabled=settings.context.enabled,
            )
        except PermissionError:
            try:
                fallback_root = settings.l0_cache_path.parent / "context" / "commands"
                command_context = CommandContextStore(
                    root=fallback_root,
                    enabled=settings.context.enabled,
                )
            except PermissionError:
                command_context = CommandContextStore(
                    root=Path(os.getcwd()) / ".daari" / "context" / "commands",
                    enabled=settings.context.enabled,
                )
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
        metrics = Metrics()
        router = Router(
            cache=cache,
            semantic_cache=semantic_cache,
            command_context=command_context,
            ollama_l3=ollama_l3,
            ollama_l4=ollama_l4,
            metrics=metrics,
            frontier=frontier,
            shell_executor=shell_executor,
            policy=policy,
            provider_registry=providers,
            model_preference=settings.routing.prefer,
            model_weights=settings.models.weights,
            frontier_enabled=settings.frontier.enabled,
            confidence_threshold=settings.routing.confidence_threshold,
        )
        return cls(
            settings=settings,
            cache=cache,
            semantic_cache=semantic_cache,
            command_context=command_context,
            ollama_l3=ollama_l3,
            ollama_l4=ollama_l4,
            frontier=frontier,
            shell_executor=shell_executor,
            policy=policy,
            providers=providers,
            metrics=metrics,
            router=router,
        )
