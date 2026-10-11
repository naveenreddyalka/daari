"""Preserve Anthropic thinking blocks for L6 replay (issue #431)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import AnthropicMessageIn, anthropic_message_to_internal, wants_anthropic_models
from daari.gateway.content import content_to_text, extract_thinking_blocks, sanitize_messages_for_ollama
from daari.gateway.internal import InternalRequest, Message
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.capabilities import anthropic_model_cards, anthropic_models_payload
from daari.router.router import AppContext
from daari.server.app import create_app


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_wants_anthropic_models_header_and_x_api_key() -> None:
    assert wants_anthropic_models(_FakeRequest({"anthropic-version": "2023-06-01"})) is True
    assert wants_anthropic_models(_FakeRequest({"x-api-key": "sekret"})) is True
    assert wants_anthropic_models(_FakeRequest({"authorization": "Bearer sekret"})) is False
    assert wants_anthropic_models(_FakeRequest({})) is False
    # Bearer wins over x-api-key for OpenAI-shaped clients that send both.
    assert (
        wants_anthropic_models(
            _FakeRequest({"x-api-key": "sekret", "authorization": "Bearer sekret"})
        )
        is False
    )


def test_anthropic_model_cards_match_openai_ids(settings) -> None:
    from daari.router.capabilities import openai_model_cards

    openai_ids = [card["id"] for card in openai_model_cards(settings)]
    anthropic = anthropic_model_cards(settings)
    assert [card["id"] for card in anthropic] == openai_ids
    assert all(card["type"] == "model" for card in anthropic)
    assert all(card["display_name"] for card in anthropic)
    assert all(card["created_at"].endswith("Z") for card in anthropic)
    assert all("line" in card for card in anthropic)
    payload = anthropic_models_payload(settings)
    assert payload["has_more"] is False
    assert payload["first_id"] == anthropic[0]["id"]
    assert payload["last_id"] == anthropic[-1]["id"]


def test_anthropic_model_line_explicit_map() -> None:
    from daari.router.capabilities import anthropic_model_line

    assert anthropic_model_line("claude-sonnet-5") == "sonnet"
    assert anthropic_model_line("claude-sonnet-5-5") == "sonnet"
    assert anthropic_model_line("anthropic.claude-sonnet-5-5") == "sonnet"
    assert anthropic_model_line("claude-opus-5") == "opus"
    assert anthropic_model_line("claude-haiku-4-5") == "haiku"
    assert anthropic_model_line("claude-fable-5-1") == "fable"
    assert anthropic_model_line("claude-fable-5-1-20260901") == "fable"
    # Local / unknown: null — never invent from free-form id tokens.
    assert anthropic_model_line("daari") is None
    assert anthropic_model_line("llama3.2:3b") is None
    assert anthropic_model_line("gpt-6.1-sol") is None
    assert anthropic_model_line("totally-unknown-model") is None


def test_anthropic_model_cards_line_null_for_local(settings) -> None:
    by_id = {card["id"]: card["line"] for card in anthropic_model_cards(settings)}
    assert by_id.get("daari") is None
    if "llama3.2:3b" in by_id:
        assert by_id["llama3.2:3b"] is None


def test_anthropic_model_cards_lifecycle_and_server_tools(settings) -> None:
    """Anthropic Models API lifecycle + capabilities.server_tools (#1507)."""
    from daari.router.capabilities import anthropic_capabilities, anthropic_models_payload

    cards = anthropic_model_cards(settings)
    assert cards
    for card in cards:
        assert card["lifecycle"] in ("active", "deprecated", "retired")
        assert "deprecated_at" in card
        assert "retires_at" in card
        server = card["capabilities"]["server_tools"]
        assert "supported" in server
        assert "web_search" in server and "supported" in server["web_search"]
        assert "code_execution" in server and "supported" in server["code_execution"]

    claude_caps = anthropic_capabilities("claude-sonnet-5-5")
    assert claude_caps["server_tools"]["supported"] is True
    assert claude_caps["server_tools"]["web_search"]["supported"] is True
    assert claude_caps["server_tools"]["code_execution"]["supported"] is True

    local_caps = anthropic_capabilities("daari")
    assert local_caps["server_tools"]["supported"] is False
    assert local_caps["server_tools"]["web_search"]["supported"] is False
    assert local_caps["server_tools"]["code_execution"]["supported"] is False

    # Default list omits retired.
    default_ids = {c["id"] for c in anthropic_models_payload(settings)["data"]}
    assert default_ids == {
        c["id"] for c in cards if c["lifecycle"] in ("active", "deprecated")
    }


@pytest.mark.asyncio
async def test_anthropic_models_lifecycle_query_filter(settings) -> None:
    from daari.router.capabilities import anthropic_model_cards
    from daari.router.router import AppContext
    from daari.server.app import create_app

    # Inject one retired card via monkeypatch on anthropic_model_cards.
    real_cards = anthropic_model_cards(settings)
    retired = dict(real_cards[0])
    retired["id"] = "claude-retired-test"
    retired["lifecycle"] = "retired"
    retired["deprecated_at"] = "2026-01-01T00:00:00Z"
    retired["retires_at"] = "2026-06-01T00:00:00Z"
    mixed = list(real_cards) + [retired]

    import daari.router.capabilities as caps_mod

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    original = caps_mod.anthropic_model_cards
    caps_mod.anthropic_model_cards = lambda _s: mixed
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            default = await client.get(
                "/v1/models", headers={"anthropic-version": "2023-06-01"}
            )
            assert default.status_code == 200
            default_ids = {c["id"] for c in default.json()["data"]}
            assert "claude-retired-test" not in default_ids

            with_retired = await client.get(
                "/v1/models",
                params={"lifecycle": "retired"},
                headers={"anthropic-version": "2023-06-01"},
            )
            assert with_retired.status_code == 200
            retired_ids = {c["id"] for c in with_retired.json()["data"]}
            assert retired_ids == {"claude-retired-test"}

            multi = await client.get(
                "/v1/models",
                params=[("lifecycle", "active"), ("lifecycle", "retired")],
                headers={"anthropic-version": "2023-06-01"},
            )
            multi_ids = {c["id"] for c in multi.json()["data"]}
            assert "claude-retired-test" in multi_ids
            assert any(c["lifecycle"] == "active" for c in multi.json()["data"])
    finally:
        caps_mod.anthropic_model_cards = original


def test_anthropic_model_cards_thinking_disabled_capability(settings) -> None:
    """Models API reports capabilities.thinking.types.disabled (#1481)."""
    from daari.router.capabilities import (
        anthropic_capabilities,
        anthropic_thinking_disabled_supported,
    )

    cards = {card["id"]: card for card in anthropic_model_cards(settings)}
    assert "daari" in cards
    local_caps = cards["daari"]["capabilities"]
    assert local_caps["thinking"]["types"]["disabled"]["supported"] is True

    # Claude family id — field present with Anthropic semantics (accept disabled).
    from daari.router.capabilities import anthropic_model_line as _line

    claude_id = next(
        (cid for cid in cards if "claude" in cid.lower() or _line(cid)),
        "claude-sonnet-5-5",
    )
    if claude_id not in cards:
        # Catalog may omit frontier ids; still pin the helper shape.
        assert anthropic_thinking_disabled_supported("claude-sonnet-5-5") is True
        assert (
            anthropic_capabilities("claude-sonnet-5-5")["thinking"]["types"]["disabled"][
                "supported"
            ]
            is True
        )
    else:
        assert cards[claude_id]["capabilities"]["thinking"]["types"]["disabled"][
            "supported"
        ] is True

    for card in cards.values():
        assert "capabilities" in card
        assert card["capabilities"]["thinking"]["types"]["disabled"]["supported"] in (
            True,
            False,
        )


@pytest.mark.asyncio
async def test_messages_captures_anthropic_beta_and_version(settings):
    """Inbound anthropic-beta / anthropic-version land on RequestMeta (#455)."""
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
            headers={
                "anthropic-version": "2024-01-01",
                "anthropic-beta": "context-1m-2025-08-07,interleaved-thinking-2025-05-14",
            },
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
    assert seen[0].meta.anthropic_version == "2024-01-01"
    assert (
        seen[0].meta.anthropic_beta
        == "context-1m-2025-08-07,interleaved-thinking-2025-05-14"
    )
    assert bare.status_code == 200
    assert seen[1].meta.anthropic_beta is None
    assert seen[1].meta.anthropic_version is None


def test_anthropic_headers_forward_beta_and_override_version() -> None:
    from daari.gateway.internal import RequestMeta
    from daari.router.anthropic_messages import (
        ANTHROPIC_VERSION,
        anthropic_headers,
        anthropic_headers_for_request,
    )

    default = anthropic_headers("sk")
    assert default["anthropic-version"] == ANTHROPIC_VERSION
    assert "anthropic-beta" not in default

    forwarded = anthropic_headers_for_request(
        "sk",
        InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="claude",
            meta=RequestMeta(
                anthropic_beta="context-1m-2025-08-07",
                anthropic_version="2024-10-22",
            ),
        ),
    )
    assert forwarded["anthropic-beta"] == "context-1m-2025-08-07"
    assert forwarded["anthropic-version"] == "2024-10-22"


@pytest.mark.asyncio
async def test_models_list_anthropic_shape_via_header(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/models", headers={"anthropic-version": "2023-06-01"}
        )
        via_key = await client.get("/v1/models", headers={"x-api-key": "unused-when-open"})
        openai_shape = await client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert "object" not in body
    assert body["has_more"] is False
    assert body["data"]
    assert body["data"][0]["type"] == "model"
    assert "display_name" in body["data"][0]
    assert "created_at" in body["data"][0]
    assert "line" in body["data"][0]
    assert via_key.json()["data"][0]["type"] == "model"
    assert openai_shape.json()["object"] == "list"
    assert "capabilities" in openai_shape.json()["data"][0]


@pytest.mark.asyncio
async def test_models_retrieve_anthropic_shape_includes_line(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        daari = await client.get(
            "/v1/models/daari", headers={"anthropic-version": "2023-06-01"}
        )
        sonnet = await client.get(
            "/v1/models/claude-sonnet-5-5",
            headers={"anthropic-version": "2023-06-01"},
        )
    assert daari.status_code == 200
    assert daari.json()["type"] == "model"
    assert daari.json()["line"] is None
    assert sonnet.status_code == 200
    assert sonnet.json()["line"] == "sonnet"


def test_extract_keeps_thinking_with_text() -> None:
    blocks = [
        {"type": "thinking", "thinking": "step by step", "signature": "sig_abc"},
        {"type": "text", "text": "answer"},
    ]
    kept = extract_thinking_blocks(blocks)
    assert kept == [
        {"type": "thinking", "thinking": "step by step", "signature": "sig_abc"},
    ]


def test_extract_keeps_signature_only_thinking() -> None:
    """Omitted-display blocks have empty thinking but a required signature."""
    blocks = [{"type": "thinking", "thinking": "", "signature": "sig_only"}]
    assert extract_thinking_blocks(blocks) == [
        {"type": "thinking", "thinking": "", "signature": "sig_only"},
    ]


def test_extract_omits_empty_thinking() -> None:
    blocks = [
        {"type": "thinking", "thinking": "", "signature": ""},
        {"type": "thinking", "thinking": "   "},
        {"type": "text", "text": "hi"},
    ]
    assert extract_thinking_blocks(blocks) == []


def test_extract_keeps_redacted_thinking_with_data() -> None:
    blocks = [{"type": "redacted_thinking", "data": "enc_blob"}]
    assert extract_thinking_blocks(blocks) == [
        {"type": "redacted_thinking", "data": "enc_blob"},
    ]


def test_extract_omits_empty_redacted_thinking() -> None:
    assert extract_thinking_blocks([{"type": "redacted_thinking", "data": ""}]) == []
    assert extract_thinking_blocks([{"type": "redacted_thinking"}]) == []


def test_content_to_text_ignores_thinking() -> None:
    blocks = [
        {"type": "thinking", "thinking": "secret chain", "signature": "sig"},
        {"type": "text", "text": "visible"},
    ]
    assert content_to_text(blocks) == "visible"


def test_anthropic_inbound_keeps_thinking_on_message() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "plan", "signature": "sig_1"},
            {"type": "text", "text": "done"},
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert len(expanded) == 1
    assert expanded[0].content == "done"
    assert expanded[0].thinking_blocks == [
        {"type": "thinking", "thinking": "plan", "signature": "sig_1"},
    ]


def test_anthropic_inbound_omits_empty_thinking() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "", "signature": ""},
            {"type": "text", "text": "hi"},
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert expanded[0].thinking_blocks == []
    assert expanded[0].content == "hi"


def test_anthropic_inbound_thinking_with_tool_use() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "", "signature": "sig_tool"},
            {"type": "text", "text": "calling"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search",
                "input": {"q": "x"},
            },
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert expanded[0].thinking_blocks[0]["signature"] == "sig_tool"
    assert expanded[0].tool_calls is not None
    assert expanded[0].content == "calling"


def test_l6_replay_emits_thinking_before_text() -> None:
    request = InternalRequest(
        messages=[
            Message(role="user", content="q"),
            Message(
                role="assistant",
                content="a",
                thinking_blocks=[
                    {"type": "thinking", "thinking": "reason", "signature": "sig"},
                ],
            ),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-4-0")
    assistant = payload["messages"][1]
    assert assistant["content"][0] == {
        "type": "thinking",
        "thinking": "reason",
        "signature": "sig",
    }
    assert assistant["content"][1] == {"type": "text", "text": "a"}


def test_l6_replay_emits_thinking_before_tool_use() -> None:
    request = InternalRequest(
        messages=[
            Message(role="user", content="search"),
            Message(
                role="assistant",
                content="ok",
                thinking_blocks=[
                    {"type": "thinking", "thinking": "", "signature": "sig_t"},
                    {"type": "redacted_thinking", "data": "blob"},
                ],
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "x"}'},
                    }
                ],
            ),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-4-0")
    content = payload["messages"][1]["content"]
    assert content[0]["type"] == "thinking"
    assert content[1]["type"] == "redacted_thinking"
    assert content[2]["type"] == "text"
    assert content[3]["type"] == "tool_use"


def test_sanitize_strips_thinking_for_ollama() -> None:
    messages = [
        Message(
            role="assistant",
            content="answer",
            thinking_blocks=[
                {"type": "thinking", "thinking": "hidden", "signature": "sig"},
            ],
        )
    ]
    sanitized = sanitize_messages_for_ollama(messages)
    assert sanitized[0].thinking_blocks == []
    assert sanitized[0].content == "answer"
