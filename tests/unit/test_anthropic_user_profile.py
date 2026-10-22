"""anthropic-user-profile-id passthrough + end-user mapping (#1844)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.anthropic_messages import (
    anthropic_headers,
    anthropic_headers_for_request,
    apply_anthropic_user_profile,
)
from daari.server.app import AppContext, create_app


def test_anthropic_headers_omit_profile_when_absent() -> None:
    headers = anthropic_headers("sk")
    assert "anthropic-user-profile-id" not in headers
    forwarded = anthropic_headers_for_request(
        "sk",
        InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="claude",
            meta=RequestMeta(),
        ),
    )
    assert "anthropic-user-profile-id" not in forwarded


def test_anthropic_headers_forward_profile_from_meta() -> None:
    forwarded = anthropic_headers_for_request(
        "sk",
        InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="claude",
            meta=RequestMeta(anthropic_user_profile_id="prof_client"),
        ),
    )
    assert forwarded["anthropic-user-profile-id"] == "prof_client"


def test_mapping_injects_when_user_matches() -> None:
    meta = RequestMeta(user="erin", key_id="k1")
    apply_anthropic_user_profile(
        meta,
        client_header=None,
        user_profiles={"erin": "prof_erin", "k1": "prof_key"},
    )
    assert meta.anthropic_user_profile_id == "prof_erin"


def test_mapping_falls_back_to_key_then_team() -> None:
    meta = RequestMeta(key_id="k1", team_id="t1")
    apply_anthropic_user_profile(
        meta,
        client_header=None,
        user_profiles={"t1": "prof_team", "k1": "prof_key"},
    )
    assert meta.anthropic_user_profile_id == "prof_key"

    meta2 = RequestMeta(team_id="t1")
    apply_anthropic_user_profile(
        meta2,
        client_header=None,
        user_profiles={"t1": "prof_team"},
    )
    assert meta2.anthropic_user_profile_id == "prof_team"


def test_client_header_wins_over_mapping() -> None:
    meta = RequestMeta(user="erin")
    apply_anthropic_user_profile(
        meta,
        client_header="prof_client",
        user_profiles={"erin": "prof_mapped"},
    )
    assert meta.anthropic_user_profile_id == "prof_client"


def test_no_mapping_match_leaves_unset() -> None:
    meta = RequestMeta(user="other")
    apply_anthropic_user_profile(
        meta,
        client_header=None,
        user_profiles={"erin": "prof_erin"},
    )
    assert meta.anthropic_user_profile_id is None


@pytest.mark.asyncio
async def test_messages_captures_and_forwards_client_profile(settings, monkeypatch):
    """Inbound anthropic-user-profile-id lands on RequestMeta (#1844)."""
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"anthropic-user-profile-id": "prof_from_client"},
        )
        bare = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi2"}],
            },
        )
    assert response.status_code == 200
    assert seen[0].meta.anthropic_user_profile_id == "prof_from_client"
    assert bare.status_code == 200
    assert seen[1].meta.anthropic_user_profile_id is None


@pytest.mark.asyncio
async def test_messages_injects_mapped_profile_and_surfaces_in_meta(settings):
    settings.anthropic.user_profiles = {"alice": "prof_alice"}
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        dm = DaariMeta(tier="L3", executor="ollama", latency_ms=1)
        if request.meta.anthropic_user_profile_id:
            dm.anthropic_user_profile_id = request.meta.anthropic_user_profile_id
        return InternalResponse(content="ok", model="llama3.2:3b", daari_meta=dm)

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"x-daari-client-id": "alice"},
        )
    assert response.status_code == 200
    assert seen[0].meta.anthropic_user_profile_id == "prof_alice"
    assert response.json()["daari_meta"]["anthropic_user_profile_id"] == "prof_alice"


@pytest.mark.asyncio
async def test_openai_chat_captures_profile_header(settings):
    """OpenAI-shape requests capture anthropic-user-profile-id for L6 Anthropic (#1844)."""
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
                "user": "bob",
            },
            headers={"anthropic-user-profile-id": "prof_openai"},
        )
    assert response.status_code == 200
    assert seen[0].meta.anthropic_user_profile_id == "prof_openai"
    assert seen[0].meta.user == "bob"


@pytest.mark.asyncio
async def test_openai_chat_mapping_by_body_user(settings):
    settings.anthropic.user_profiles = {"bob": "prof_bob"}
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
                "user": "bob",
            },
        )
    assert response.status_code == 200
    assert seen[0].meta.anthropic_user_profile_id == "prof_bob"
