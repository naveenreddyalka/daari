"""Pre-first-token host failover for streamed local requests (#974)."""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.local_pool import LocalBackendPool, LocalBackendSlot
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str = "say hello") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _slot(slot_id: str, *, url: str = "http://x", **kwargs) -> LocalBackendSlot:
    return LocalBackendSlot(
        id=slot_id,
        base_url=url,
        model="llama3.2:3b",
        **kwargs,
    )


class _HostExecutor(OllamaExecutor):
    """Per-host stream stub; bind_executor copies stream from the instance dict."""

    def __init__(self, host_id: str, *, fail: bool = False) -> None:
        super().__init__(base_url=f"http://{host_id}", default_model="llama3.2:3b")
        self.host_id = host_id
        self.fail = fail
        self.stream_calls = 0

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content=f"from-{self.host_id}",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.stream_calls += 1
        if self.fail:
            raise ConnectionError(f"{self.host_id} connect failed")
        yield {"message": {"content": f"ok-from-{self.host_id}"}}
        yield {"done": True}


def _router(tmp_path, template: OllamaExecutor, pool: LocalBackendPool) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=template,
        ollama_l3=template,
        ollama_l4=template,
        ollama_l5=template,
        metrics=Metrics(),
        local_pool=pool,
    )


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _openai_text(body: str) -> str:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if "error" in payload:
            continue
        for choice in payload.get("choices", []):
            out.append(choice.get("delta", {}).get("content") or "")
    return "".join(out)


def _has_openai_error(body: str) -> bool:
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if "error" in payload:
            return True
    return False


@pytest.mark.asyncio
async def test_stream_fails_over_to_second_host_before_first_token(tmp_path):
    primary = _HostExecutor("gpu-a", fail=True)
    secondary = _HostExecutor("gpu-b", fail=False)
    # Template stream is unused; bind_executor copies per-slot stream methods.
    template = _HostExecutor("template", fail=False)
    pool = LocalBackendPool(
        slots=[_slot("gpu-a", url="http://a"), _slot("gpu-b", url="http://b")],
        strategy="round_robin",
    )
    # Force first pick to be gpu-a by resetting rr and ensuring order.
    pool._rr["L3"] = 0
    router = _router(tmp_path, template, pool)
    # Patch bind_executor to return the matching host stub.
    original_bind = pool.bind_executor

    def bind(slot, tmpl):
        return primary if slot.id == "gpu-a" else secondary

    pool.bind_executor = bind  # type: ignore[method-assign]
    body = await _collect(router.stream_openai_chunks(_request()))
    assert primary.stream_calls == 1
    assert secondary.stream_calls == 1
    assert "ok-from-gpu-b" in _openai_text(body)
    assert not _has_openai_error(body)
    assert body.rstrip().endswith("data: [DONE]")
    assert pool.slots[0].breaker.failures >= 1
    assert pool.slots[1].breaker.failures == 0
    assert pool.slots[1].breaker.state == "closed"
    pool.bind_executor = original_bind  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_stream_all_hosts_down_emits_error(tmp_path):
    primary = _HostExecutor("gpu-a", fail=True)
    secondary = _HostExecutor("gpu-b", fail=True)
    template = _HostExecutor("template", fail=True)
    pool = LocalBackendPool(
        slots=[_slot("gpu-a", url="http://a"), _slot("gpu-b", url="http://b")],
        strategy="round_robin",
    )
    pool._rr["L3"] = 0
    router = _router(tmp_path, template, pool)

    def bind(slot, tmpl):
        return primary if slot.id == "gpu-a" else secondary

    pool.bind_executor = bind  # type: ignore[method-assign]
    body = await _collect(router.stream_openai_chunks(_request()))
    assert primary.stream_calls >= 1
    assert secondary.stream_calls >= 1
    assert _has_openai_error(body) or "stream failed" in body
    assert pool.slots[0].breaker.failures >= 1
    assert pool.slots[1].breaker.failures >= 1


@pytest.mark.asyncio
async def test_pick_exclude_skips_tried_hosts():
    pool = LocalBackendPool(
        slots=[_slot("a", url="http://a"), _slot("b", url="http://b")],
        strategy="round_robin",
    )
    first = pool.pick("L3")
    second = pool.pick("L3", exclude={first.id})
    assert second.id != first.id
    with pytest.raises(Exception):
        pool.pick("L3", exclude={first.id, second.id})


@pytest.mark.asyncio
async def test_post_first_token_failure_does_not_failover_hosts(tmp_path):
    """After the client has seen a delta, host failover must not swap mid-stream."""

    class _PartialThenDie(_HostExecutor):
        async def stream(self, request, **kwargs):  # type: ignore[override]
            self.stream_calls += 1
            yield {"message": {"content": "partial "}}
            raise RuntimeError("died after token")

    dying = _PartialThenDie("gpu-a")
    healthy = _HostExecutor("gpu-b", fail=False)
    template = _HostExecutor("template")
    pool = LocalBackendPool(
        slots=[
            _slot("gpu-a", url="http://a", breaker=CircuitBreaker(failure_threshold=5)),
            _slot("gpu-b", url="http://b"),
        ],
        strategy="round_robin",
    )
    pool._rr["L3"] = 0
    router = _router(tmp_path, template, pool)

    def bind(slot, tmpl):
        return dying if slot.id == "gpu-a" else healthy

    pool.bind_executor = bind  # type: ignore[method-assign]
    body = await _collect(router.stream_openai_chunks(_request()))
    assert dying.stream_calls == 1
    assert healthy.stream_calls == 0, "must not hop hosts after first token"
    assert "partial" in body
    assert "stream_incomplete" in body or "error" in body
