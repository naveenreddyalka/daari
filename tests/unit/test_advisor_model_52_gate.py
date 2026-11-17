"""Reject non-5.2 advisor models when the executor is Fable/Mythos 5.2 (#2223)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    ADVISOR_TOOL_TYPE,
    AdvisorModelRejected,
    enforce_advisor_model_for_52,
    is_fable_mythos_52_model,
)
from daari.router.frontier import FrontierExecutor


def _req(*, tools: list[dict], model: str = "daari") -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="plan")],
        model=model,
        sampling=SamplingParams(max_tokens=50),
        tools=tools,
        meta=RequestMeta(),
    )


def _advisor(model: str, *, anthropic_shaped: bool = True) -> dict:
    if anthropic_shaped:
        return {"type": ADVISOR_TOOL_TYPE, "name": "advisor", "model": model}
    return {
        "type": "function",
        "anthropic_type": ADVISOR_TOOL_TYPE,
        "model": model,
        "function": {"name": "advisor", "parameters": {}},
    }


class TestEnforceAdvisorGate:
    def test_52_rejects_weaker_advisor(self):
        with pytest.raises(AdvisorModelRejected, match="claude-fable-5-2") as exc:
            enforce_advisor_model_for_52(
                [_advisor("claude-fable-5-1")],
                model="claude-fable-5-2",
            )
        assert "claude-mythos-5-2" in str(exc.value)
        assert "claude-fable-5-1" in str(exc.value)

    def test_mythos_52_rejects_opus_advisor(self):
        with pytest.raises(AdvisorModelRejected, match="claude-mythos-5-2"):
            enforce_advisor_model_for_52(
                [_advisor("claude-opus-5-5")],
                model="anthropic.claude-mythos-5-2-20261109",
            )

    @pytest.mark.parametrize(
        "advisor_model",
        ["claude-fable-5-2", "claude-mythos-5-2", "claude-fable-5-2-20261109"],
    )
    def test_52_allows_52_advisor(self, advisor_model):
        enforce_advisor_model_for_52(
            [_advisor(advisor_model)],
            model="claude-fable-5-2",
        )

    def test_52_without_advisor_ok(self):
        enforce_advisor_model_for_52(
            [{"type": "computer_toolset_20260801"}],
            model="claude-fable-5-2",
        )

    def test_non_52_executor_unaffected(self):
        enforce_advisor_model_for_52(
            [_advisor("claude-opus-5-5")],
            model="claude-opus-5-5",
        )
        enforce_advisor_model_for_52(
            [_advisor("claude-fable-5-1")],
            model="claude-fable-5-1",
        )

    def test_openai_shaped_advisor_payload(self):
        with pytest.raises(AdvisorModelRejected, match="claude-fable-5-2"):
            enforce_advisor_model_for_52(
                [_advisor("claude-sonnet-5-5", anthropic_shaped=False)],
                model="claude-mythos-5-2",
            )


class TestFrontierPayloadGate:
    def test_anthropic_payload_raises_before_egress(self):
        exe = FrontierExecutor(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            default_model="claude-fable-5-2",
            provider="anthropic",
        )
        req = _req(tools=[_advisor("claude-fable-5-1")])
        with pytest.raises(AdvisorModelRejected, match="claude-fable-5-2"):
            exe._anthropic_payload(req, stream=False)

    @pytest.mark.asyncio
    async def test_execute_rejects_without_http(self, monkeypatch):
        exe = FrontierExecutor(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            default_model="claude-fable-5-2",
            provider="anthropic",
        )
        posted = AsyncMock()
        monkeypatch.setattr(exe, "_client", lambda: type("C", (), {"post": posted})())
        req = _req(tools=[_advisor("claude-opus-5-5")])
        with pytest.raises(AdvisorModelRejected):
            await exe.execute(req, escalated_from=None, local_confidence=None)
        posted.assert_not_called()


def test_allowed_ids_are_fable_mythos_52():
    assert is_fable_mythos_52_model("claude-fable-5-2")
    assert is_fable_mythos_52_model("claude-mythos-5-2")
