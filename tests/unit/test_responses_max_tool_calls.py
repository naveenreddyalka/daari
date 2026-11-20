"""Responses max_tool_calls: declare honestly, never silent, never bridge (#2256)."""

from __future__ import annotations

from pathlib import Path

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.responses import ResponsesRequest
from daari.gateway.sampling import SamplingParams
from daari.router.frontier import FrontierExecutor

DOC = Path(__file__).resolve().parents[2] / "docs/developer/concepts/clients-and-gateways.md"


def test_docs_mention_max_tool_calls_honesty():
    text = DOC.read_text(encoding="utf-8")
    assert "max_tool_calls" in text
    assert "dropped_params" in text


def test_responses_request_declares_max_tool_calls():
    body = ResponsesRequest(model="daari", input="hi", max_tool_calls=3)
    assert body.max_tool_calls == 3


def test_from_responses_body_parses_max_tool_calls():
    params = SamplingParams.from_responses_body({"max_tool_calls": 5, "max_output_tokens": 16})
    assert params.max_tool_calls == 5


def test_invalid_max_tool_calls_ignored():
    assert SamplingParams.from_responses_body({"max_tool_calls": 0}).max_tool_calls is None
    assert SamplingParams.from_responses_body({"max_tool_calls": -1}).max_tool_calls is None
    assert SamplingParams.from_responses_body({"max_tool_calls": "x"}).max_tool_calls is None


def test_openai_payload_never_forwards_max_tool_calls():
    params = SamplingParams(max_tool_calls=4, max_tokens=32)
    payload = params.openai_payload()
    assert "max_tool_calls" not in payload
    assert payload["max_tokens"] == 32


def test_frontier_chat_bridge_rejects_unknown_keys_without_max_tool_calls():
    """Hermetic: bridged OpenAI chat payload must not smuggle max_tool_calls."""
    params = SamplingParams(max_tool_calls=2, max_tokens=8)
    request = InternalRequest(
        messages=[Message(role="user", content="hello")],
        model="gpt-4o",
        sampling=params,
    )
    executor = FrontierExecutor(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        provider="openai",
    )
    payload = executor._openai_payload(request, stream=False)
    assert "max_tool_calls" not in payload


def test_max_tool_calls_always_listed_in_dropped_params():
    params = SamplingParams(max_tool_calls=3)
    dropped = params.dropped_param_names()
    assert "max_tool_calls" in dropped
    notes = "; ".join(params.unsupported_locally())
    assert "max_tool_calls" in notes


def test_meta_receives_max_tool_calls_drop():
    params = SamplingParams(max_tool_calls=2)
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="llama3.2:3b",
        sampling=params,
    )
    response = InternalResponse(
        content="ok",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
    )
    dropped = list(request.sampling.dropped_param_names())
    response.daari_meta.dropped_params = dropped
    assert "max_tool_calls" in (response.daari_meta.dropped_params or [])
