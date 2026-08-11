"""Streaming must enforce the same policy and tier ladder as route() (#154, #155).

Boundaries, guardrails, and frontier escalation all lived in `route()` only,
so every IDE client — which streams by default — bypassed them.
"""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import BoundariesSettings
from daari.gateway.boundaries import BoundaryEngine
from daari.gateway.guardrails import GuardrailEngine, GuardrailRule
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

LOCAL_TEXT = "a local answer that is long enough to look confident to the scorer"


def _request(text: str, **meta) -> InternalRequest:
    request = InternalRequest(messages=[Message(role="user", content=text)], model="daari")
    for key, value in meta.items():
        setattr(request.meta, key, value)
    return request


def _boundaries(mode: str = "block") -> BoundariesSettings:
    return BoundariesSettings(
        enabled=True,
        mode=mode,
        product_name="CK Assist",
        product_description="Credit scores, cards, loans, and account help only.",
        allow_topics=["credit score", "credit card", "loan"],
        deny_topics=["python", "wedding", "weather"],
        examples_in=["Why did my score drop?"],
        examples_out=["Write a Python scraper"],
        refuse_message="I only help with credit and account questions.",
        clear_out_threshold=0.7,
        clear_in_threshold=0.7,
    )


class _Executor(OllamaExecutor):
    """Ollama stand-in counting calls and returning canned text."""

    def __init__(self, text: str = LOCAL_TEXT) -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")
        self.text = text
        self.calls = 0
        self.stream_calls = 0

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        self.calls += 1
        return InternalResponse(
            content=self.text,
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.stream_calls += 1
        for part in (self.text[: len(self.text) // 2], self.text[len(self.text) // 2 :]):
            yield {"message": {"content": part}}
        yield {"message": {"content": ""}, "done": True}


def _router(tmp_path, executor, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=kwargs.pop("l0_enabled", False)),
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"), NoopEmbedder(), enabled=kwargs.pop("l1_enabled", False)
        ),
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        **kwargs,
    )


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _openai_text(body: str) -> str:
    text = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        for choice in payload.get("choices", []):
            text.append(choice.get("delta", {}).get("content") or "")
    return "".join(text)


def _anthropic_text(body: str) -> str:
    text = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("type") == "content_block_delta":
            text.append(payload.get("delta", {}).get("text") or "")
    return "".join(text)


# --- boundaries -------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_stream_blocks_out_of_scope_prompt(tmp_path):
    executor = _Executor()
    router = _router(
        tmp_path, executor, boundaries=BoundaryEngine.from_settings(_boundaries("block"))
    )
    body = await _collect(
        router.stream_openai_chunks(_request("Write a Python scraper for weather data"))
    )
    assert executor.stream_calls == 0, "model must not run for a blocked prompt"
    assert "I only help with credit and account questions." in _openai_text(body)
    assert body.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_anthropic_stream_blocks_out_of_scope_prompt(tmp_path):
    executor = _Executor()
    router = _router(
        tmp_path, executor, boundaries=BoundaryEngine.from_settings(_boundaries("block"))
    )
    body = await _collect(
        router.stream_anthropic_events(_request("Write a Python scraper for weather data"))
    )
    assert executor.stream_calls == 0
    assert "I only help with credit and account questions." in _anthropic_text(body)
    assert "message_stop" in body


@pytest.mark.asyncio
async def test_stream_warn_mode_continues_to_model(tmp_path):
    executor = _Executor()
    router = _router(
        tmp_path, executor, boundaries=BoundaryEngine.from_settings(_boundaries("warn"))
    )
    body = await _collect(
        router.stream_openai_chunks(_request("Write a Python scraper for weather data"))
    )
    assert executor.stream_calls == 1, "warn mode annotates but does not refuse"
    assert LOCAL_TEXT in _openai_text(body)


@pytest.mark.asyncio
async def test_stream_allows_in_scope_prompt(tmp_path):
    executor = _Executor()
    router = _router(
        tmp_path, executor, boundaries=BoundaryEngine.from_settings(_boundaries("block"))
    )
    body = await _collect(router.stream_openai_chunks(_request("Why did my credit score drop?")))
    assert executor.stream_calls == 1
    assert LOCAL_TEXT in _openai_text(body)


# --- guardrails -------------------------------------------------------------


def _guardrails() -> GuardrailEngine:
    return GuardrailEngine(
        enabled=True,
        input_rules=[
            GuardrailRule(
                name="deny-topic", kind="deny", pattern=r"forbidden-topic", action="block"
            )
        ],
        output_rules=[GuardrailRule(name="secrets", kind="secret", action="redact")],
        block_message="Blocked by policy.",
    )


@pytest.mark.asyncio
async def test_stream_input_guardrail_blocks_before_model(tmp_path):
    executor = _Executor()
    router = _router(tmp_path, executor, guardrails=_guardrails())
    body = await _collect(router.stream_openai_chunks(_request("tell me about forbidden-topic")))
    assert executor.stream_calls == 0
    assert "Blocked by policy." in _openai_text(body)


LEAKED_SECRET = "AKIAIOSFODNN7EXAMPLE"


@pytest.mark.asyncio
async def test_stream_output_guardrail_redacts_and_skips_cache(tmp_path):
    executor = _Executor(text=f"the access key is {LEAKED_SECRET} keep it safe")
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    router = Router(
        cache=cache,
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        guardrails=_guardrails(),
    )
    request = _request("give me the key")
    text = _openai_text(await _collect(router.stream_openai_chunks(request)))
    assert LEAKED_SECRET not in text, "secret must not reach the client"
    cached = cache.get(request)
    if cached is not None:
        assert LEAKED_SECRET not in cached.content, "secret must not be cached"


# --- frontier escalation ----------------------------------------------------


class _Frontier:
    def __init__(self) -> None:
        self.api_key = "sk-test"
        self.calls = 0

    async def execute(self, request, escalated_from=None, local_confidence=None):
        self.calls += 1
        return InternalResponse(
            content="FRONTIER ANSWER",
            model="gpt-4o",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                escalated_from=escalated_from,
            ),
        )


@pytest.mark.asyncio
async def test_stream_escalates_to_frontier_on_low_confidence(tmp_path):
    executor = _Executor(text="idk")  # short answer scores below threshold
    frontier = _Frontier()
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
    )
    body = await _collect(router.stream_openai_chunks(_request("explain quantum decoherence")))
    assert frontier.calls == 1, "streaming must be able to reach L6"
    assert "FRONTIER ANSWER" in _openai_text(body)


@pytest.mark.asyncio
async def test_stream_respects_no_frontier_flag(tmp_path):
    executor = _Executor(text="idk")
    frontier = _Frontier()
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
    )
    body = await _collect(
        router.stream_openai_chunks(_request("explain quantum decoherence", no_frontier=True))
    )
    assert frontier.calls == 0
    assert "idk" in _openai_text(body)


@pytest.mark.asyncio
async def test_anthropic_stream_escalates_to_frontier(tmp_path):
    executor = _Executor(text="idk")
    frontier = _Frontier()
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
    )
    body = await _collect(router.stream_anthropic_events(_request("explain quantum decoherence")))
    assert frontier.calls == 1
    assert "FRONTIER ANSWER" in _anthropic_text(body)
    assert _last_event(body) == "message_stop", "escalated stream must terminate cleanly"


def _last_event(body: str) -> str:
    events = [line[len("event: ") :] for line in body.splitlines() if line.startswith("event: ")]
    return events[-1] if events else ""


@pytest.mark.asyncio
async def test_anthropic_stream_output_guardrail_redacts(tmp_path):
    executor = _Executor(text=f"the access key is {LEAKED_SECRET} keep it safe")
    router = _router(tmp_path, executor, guardrails=_guardrails())
    body = await _collect(router.stream_anthropic_events(_request("give me the key")))
    assert LEAKED_SECRET not in _anthropic_text(body)
    assert "message_stop" in body


@pytest.mark.asyncio
async def test_stream_does_not_escalate_when_confident(tmp_path):
    executor = _Executor()
    frontier = _Frontier()
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.1,
    )
    body = await _collect(router.stream_openai_chunks(_request("explain quantum decoherence")))
    assert frontier.calls == 0
    assert LOCAL_TEXT in _openai_text(body)
