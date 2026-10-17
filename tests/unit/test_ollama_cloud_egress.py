"""Ollama :cloud ids are remote egress for local-only fences (#1736)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.pricing import is_ollama_cloud_model
from daari.router.local_pool import CloudEgressBlocked
from daari.router.router import AppContext
from tests.conftest import MOCK_MODEL_CONTENT, mock_all_ollama_executors


def _request(**meta_kwargs) -> InternalRequest:
    return InternalRequest(
        model="daari",
        messages=[Message(role="user", content="hi")],
        meta=RequestMeta(no_cache=True, **meta_kwargs),
    )


def _ctx(settings):
    return AppContext.from_settings(settings)


@pytest.mark.asyncio
async def test_no_frontier_does_not_serve_cloud_when_local_host_exists(settings, monkeypatch):
    settings.models.l3 = "clef:cloud"
    settings.models.l4 = "llama3.2:3b"
    settings.routing.local_pool.backends = [
        {
            "id": "cloud",
            "base_url": "http://cloud.invalid",
            "model": "clef:cloud",
            "tiers": ["L3"],
        },
        {
            "id": "local",
            "base_url": "http://local.invalid",
            "model": "llama3.2:3b",
            "tiers": ["L3", "L4", "L5"],
        },
    ]
    ctx = _ctx(settings)
    served: list[str] = []
    events: list[tuple[str, dict]] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        served.append(request.model or "")
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model=request.model or "",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                model=request.model or "",
            ),
        )

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda name, detail=None: events.append((name, detail or {})),
    )

    response = await ctx.router.route(_request(no_frontier=True))

    assert served
    assert all(not is_ollama_cloud_model(model) for model in served)
    assert not is_ollama_cloud_model(response.model)
    assert any(name == "cloud_egress_skipped" and detail.get("reason") == "no_frontier" for name, detail in events)


@pytest.mark.asyncio
async def test_no_frontier_cloud_only_stack_is_blocked(settings, monkeypatch):
    settings.models.l3 = "clef:cloud"
    settings.models.l4 = "clef-flash:cloud"
    settings.models.l5 = "clef:cloud"
    ctx = _ctx(settings)
    called = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        called["n"] += 1
        raise AssertionError("cloud executor must not run")

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)

    with pytest.raises(CloudEgressBlocked) as exc:
        await ctx.router.route(_request(no_frontier=True))

    assert exc.value.reason == "no_frontier"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_tier_cap_blocks_cloud_model(settings, monkeypatch):
    settings.models.l3 = "clef:cloud"
    ctx = _ctx(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        raise AssertionError("cloud executor must not run")

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)

    with pytest.raises(CloudEgressBlocked) as exc:
        await ctx.router.route(_request(tier_cap="L3"))

    assert exc.value.reason == "tier_cap:L3"


@pytest.mark.asyncio
async def test_cloud_egress_scrubs_pii_when_enabled(settings, monkeypatch):
    settings.models.l3 = "clef:cloud"
    settings.frontier.scrub_pii = True
    ctx = _ctx(settings)
    seen: list[str] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen.append(request.messages[-1].content or "")
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model=request.model or "",
            daari_meta=DaariMeta(tier="L3", executor="ollama", model=request.model or ""),
        )

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)

    def scrub(messages):
        return [message.model_copy(update={"content": "scrubbed"}) for message in messages], {"email": 1}

    monkeypatch.setattr("daari.gateway.pii.scrub_messages", scrub)
    response = await ctx.router.route(_request())

    assert seen == ["scrubbed"]
    assert is_ollama_cloud_model(response.model)


@pytest.mark.asyncio
async def test_plain_local_model_is_not_scrubbed_or_blocked(settings, monkeypatch):
    settings.models.l3 = "llama3.2:3b"
    settings.frontier.scrub_pii = True
    ctx = _ctx(settings)
    seen: list[str] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen.append(request.messages[-1].content or "")
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model=request.model or "",
            daari_meta=DaariMeta(tier="L3", executor="ollama", model=request.model or ""),
        )

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)
    monkeypatch.setattr(
        "daari.gateway.pii.scrub_messages",
        lambda messages: (_ for _ in ()).throw(AssertionError("local hop must not scrub")),
    )

    response = await ctx.router.route(_request())

    assert seen == ["hi"]
    assert response.model == "llama3.2:3b"
