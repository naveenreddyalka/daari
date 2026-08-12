"""Streaming must reach the same tiers as route() (#155).

`_stream_tier_chain` only ever listed local model tiers, so the deterministic
pre-model tiers (Lt shell tools, L2 rules, CCS, live fetch, integrations) were
unreachable while streaming, and frontier escalation buffered instead of
relaying upstream SSE.
"""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.policy.engine import PolicyEngine
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str, **meta) -> InternalRequest:
    request = InternalRequest(messages=[Message(role="user", content=text)], model="daari")
    for key, value in meta.items():
        setattr(request.meta, key, value)
    return request


class _Executor(OllamaExecutor):
    def __init__(self, text: str = "a local model answer, reasonably long and confident") -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")
        self.text = text
        self.stream_calls = 0

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content=self.text,
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.stream_calls += 1
        yield {"message": {"content": self.text}}
        yield {"done": True}


class _Shell:
    """Stand-in for ShellExecutor.run."""

    def __init__(self, output: str = "M daari/router/router.py") -> None:
        self.output = output
        self.calls: list[str] = []

    async def run(self, command: str, cwd: str | None = None):
        self.calls.append(command)

        class _Result:
            output = self.output
            exit_code = 0

        return _Result()


def _router(tmp_path, executor, **kwargs) -> Router:
    # A bare PolicyEngine denies every unknown command, which would make the
    # Lt tests pass on a denial rather than on real tool output.
    kwargs.setdefault("policy", PolicyEngine(allow_patterns=["git status", "pytest"]))
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
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
    out = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        for choice in payload.get("choices", []):
            out.append(choice.get("delta", {}).get("content") or "")
    return "".join(out)


def _anthropic_text(body: str) -> str:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("type") == "content_block_delta":
            out.append(payload.get("delta", {}).get("text") or "")
    return "".join(out)


# --- deterministic tiers ----------------------------------------------------


@pytest.mark.asyncio
async def test_openai_stream_serves_shell_tool_tier(tmp_path):
    executor = _Executor()
    shell = _Shell()
    router = _router(tmp_path, executor, shell_executor=shell)
    body = await _collect(router.stream_openai_chunks(_request("git status")))
    assert shell.calls == ["git status"], "Lt tier must run on the streaming path"
    assert "M daari/router/router.py" in _openai_text(body)
    assert executor.stream_calls == 0, "a tool answer must not also hit a model"
    assert body.rstrip().endswith("data: [DONE]")


@pytest.mark.asyncio
async def test_anthropic_stream_serves_shell_tool_tier(tmp_path):
    executor = _Executor()
    shell = _Shell()
    router = _router(tmp_path, executor, shell_executor=shell)
    body = await _collect(router.stream_anthropic_events(_request("git status")))
    assert shell.calls == ["git status"]
    assert "M daari/router/router.py" in _anthropic_text(body)
    assert executor.stream_calls == 0
    assert "message_stop" in body


@pytest.mark.asyncio
async def test_stream_tool_tier_matches_non_stream(tmp_path):
    """The same prompt must produce the same tier and text either way."""
    executor = _Executor()
    shell = _Shell()
    router = _router(tmp_path, executor, shell_executor=shell)
    non_stream = await router.route(_request("git status"))
    stream_text = _openai_text(await _collect(router.stream_openai_chunks(_request("git status"))))
    assert non_stream.daari_meta.tier == "Lt"
    assert non_stream.content == shell.output, "guard: route() must serve real tool output"
    assert stream_text == non_stream.content


@pytest.mark.asyncio
async def test_stream_skips_tool_tier_for_agent_flow(tmp_path):
    """Agent turns own their own tool protocol; daari must not shell out."""
    executor = _Executor()
    shell = _Shell()
    router = _router(tmp_path, executor, shell_executor=shell)
    request = _request("git status")
    request.tools = [{"type": "function", "function": {"name": "run", "parameters": {}}}]
    await _collect(router.stream_openai_chunks(request))
    assert shell.calls == [], "tool-carrying requests must reach the model, not the shell"
    assert executor.stream_calls == 1


# --- frontier SSE relay -----------------------------------------------------


class _StreamingFrontier:
    """Frontier stand-in exposing both execute() and stream()."""

    def __init__(self) -> None:
        self.api_key = "sk-test"
        self.execute_calls = 0
        self.stream_calls = 0

    async def execute(self, request, escalated_from=None, local_confidence=None):
        self.execute_calls += 1
        return InternalResponse(
            content="FRONTIER BUFFERED",
            model="gpt-4o",
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="openai"),
        )

    async def stream(self, request, escalated_from=None, local_confidence=None):
        self.stream_calls += 1
        for part in ("FRONTIER ", "RELAYED ", "IN CHUNKS"):
            yield part


@pytest.mark.asyncio
async def test_stream_relays_frontier_chunks(tmp_path):
    executor = _Executor(text="idk")
    frontier = _StreamingFrontier()
    router = _router(
        tmp_path, executor, frontier=frontier, frontier_enabled=True, confidence_threshold=0.99
    )
    body = await _collect(router.stream_openai_chunks(_request("explain quantum decoherence")))
    assert frontier.stream_calls == 1, "escalated stream must relay, not buffer"
    assert frontier.execute_calls == 0
    assert "FRONTIER RELAYED IN CHUNKS" in _openai_text(body)
    # Relay means the text arrives across several chunks, not one blob.
    content_chunks = [
        line
        for line in body.splitlines()
        if line.startswith("data: ") and '"content"' in line and "FRONTIER" in line or
        (line.startswith("data: ") and '"content"' in line and "RELAYED" in line)
    ]
    assert len(content_chunks) >= 2, "relayed frontier text should stream incrementally"


@pytest.mark.asyncio
async def test_frontier_executor_parses_upstream_sse():
    """FrontierExecutor.stream must decode real OpenAI SSE, not just yield blobs."""
    import httpx

    from daari.router.frontier import FrontierExecutor

    body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        "data: \n\n"
        "data: not-json\n\n"
        'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    deltas = [d async for d in executor.stream(_request("hi"))]
    assert deltas == ["Hello", " world"], "blank, malformed, and [DONE] lines must be skipped"


@pytest.mark.asyncio
async def test_stream_buffers_frontier_when_output_guardrails_active(tmp_path):
    """Redaction needs the whole answer, so guardrails force the buffered path."""
    from daari.gateway.guardrails import GuardrailEngine, GuardrailRule

    executor = _Executor(text="idk")
    frontier = _StreamingFrontier()
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
        guardrails=GuardrailEngine(
            enabled=True,
            output_rules=[GuardrailRule(name="secrets", kind="secret", action="redact")],
        ),
    )
    body = await _collect(router.stream_openai_chunks(_request("explain quantum decoherence")))
    assert "FRONTIER" in _openai_text(body)
    assert frontier.stream_calls + frontier.execute_calls == 1
