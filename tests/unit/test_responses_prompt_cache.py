"""Responses prompt_cache_key / retention forward on L6, drop locally (#1137)."""

from __future__ import annotations

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.responses import ResponsesRequest
from daari.gateway.sampling import SamplingParams
from daari.router.frontier import FrontierExecutor


def test_responses_request_declares_prompt_cache_fields():
    body = ResponsesRequest(
        model="daari",
        input="hi",
        prompt_cache_key="session-1",
        prompt_cache_retention="24h",
        prompt_cache_options={"ttl": "30m"},
    )
    assert body.prompt_cache_key == "session-1"
    assert body.prompt_cache_retention == "24h"
    assert body.prompt_cache_options == {"ttl": "30m"}


def test_from_responses_body_parses_prompt_cache_fields():
    params = SamplingParams.from_responses_body(
        {
            "prompt_cache_key": "agent-v3",
            "prompt_cache_retention": "in_memory",
            "prompt_cache_options": {"ttl": "30m"},
        }
    )
    assert params.prompt_cache_key == "agent-v3"
    assert params.prompt_cache_retention == "in_memory"
    assert params.prompt_cache_options == {"ttl": "30m"}


def test_absent_fields_leave_sampling_unchanged():
    params = SamplingParams.from_responses_body({"max_output_tokens": 16})
    assert params.prompt_cache_key is None
    assert params.prompt_cache_retention is None
    assert params.prompt_cache_options is None
    assert "prompt_cache_key" not in params.openai_payload()
    assert "prompt_cache_retention" not in params.openai_payload()
    assert "prompt_cache_options" not in params.openai_payload()


def test_l6_openai_payload_includes_prompt_cache_fields():
    params = SamplingParams(
        prompt_cache_key="route-a",
        prompt_cache_retention="24h",
        prompt_cache_options={"ttl": "30m"},
    )
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
    assert payload["prompt_cache_key"] == "route-a"
    assert payload["prompt_cache_retention"] == "24h"
    assert payload["prompt_cache_options"] == {"ttl": "30m"}


def test_local_path_records_prompt_cache_as_dropped():
    params = SamplingParams(
        prompt_cache_key="session-1",
        prompt_cache_retention="24h",
        prompt_cache_options={"ttl": "30m"},
    )
    dropped = params.dropped_param_names()
    assert "prompt_cache_key" in dropped
    assert "prompt_cache_retention" in dropped
    assert "prompt_cache_options" in dropped
    notes = "; ".join(params.unsupported_locally())
    assert "prompt_cache_key" in notes
    assert "prompt_cache_retention" in notes
    assert "prompt_cache_options" in notes


def test_responses_meta_receives_prompt_cache_drops():
    params = SamplingParams(prompt_cache_key="k1", prompt_cache_retention="24h")
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
    assert "prompt_cache_key" in dropped
    assert "prompt_cache_retention" in dropped
    response.daari_meta.dropped_params = dropped
    assert response.daari_meta.dropped_params is not None
    assert "prompt_cache_key" in response.daari_meta.dropped_params
