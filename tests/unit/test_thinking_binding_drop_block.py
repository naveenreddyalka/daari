"""Default drop_block thinking binding on preserved-thinking Claude (#2196)."""

from __future__ import annotations

from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    THINKING_BINDING_BETA,
    anthropic_headers_for_request,
    apply_thinking_binding_drop_block,
    is_preserved_thinking_model,
    request_has_thinking_blocks,
    to_anthropic_payload,
)


_THINKING_BLOCK = {
    "type": "thinking",
    "thinking": "scratch",
    "signature": "sig_test",
}


def _request_with_thinking(*, beta: str | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="ok",
                thinking_blocks=[dict(_THINKING_BLOCK)],
            ),
            Message(role="user", content="again"),
        ],
        model="daari",
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(anthropic_beta=beta) if beta else RequestMeta(),
    )


def _request_plain() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(max_tokens=50),
        meta=RequestMeta(),
    )


class TestPreservedThinkingGate:
    def test_fable_mythos_any_version(self):
        assert is_preserved_thinking_model("claude-fable-5-1")
        assert is_preserved_thinking_model("claude-mythos-5-2")
        assert is_preserved_thinking_model("anthropic.claude-fable-5-1-20260901")

    def test_sonnet_haiku_opus_from_5_5(self):
        assert is_preserved_thinking_model("claude-sonnet-5-5")
        assert is_preserved_thinking_model("claude-opus-5-5-20251101")
        assert is_preserved_thinking_model("claude-haiku-5.5")
        assert is_preserved_thinking_model("claude-sonnet-5-6")
        assert is_preserved_thinking_model("claude-opus-6")

    def test_older_models_excluded(self):
        assert not is_preserved_thinking_model("claude-sonnet-4-0")
        assert not is_preserved_thinking_model("claude-opus-4-8")
        assert not is_preserved_thinking_model("claude-haiku-4-5")
        assert not is_preserved_thinking_model("claude-sonnet-5")
        assert not is_preserved_thinking_model("gpt-6-luna")


class TestDropBlockDefault:
    def test_preserved_model_with_blocks_merges_beta_and_binding(self):
        req = _request_with_thinking()
        assert request_has_thinking_blocks(req)
        headers = anthropic_headers_for_request(
            "sk-test", req, model="claude-sonnet-5-5"
        )
        assert THINKING_BINDING_BETA in headers.get("anthropic-beta", "")

        payload = to_anthropic_payload(req, model="claude-sonnet-5-5")
        apply_thinking_binding_drop_block(
            payload,
            "claude-sonnet-5-5",
            enabled=True,
            has_thinking_blocks=True,
        )
        thinking = payload.get("thinking") or {}
        assert thinking.get("type") == "adaptive"
        assert thinking.get("block_binding") == {
            "prefix_mismatch_behavior": "drop_block"
        }

    def test_old_model_untouched(self):
        req = _request_with_thinking()
        headers = anthropic_headers_for_request(
            "sk-test", req, model="claude-sonnet-4-0"
        )
        assert THINKING_BINDING_BETA not in headers.get("anthropic-beta", "")

        payload = to_anthropic_payload(req, model="claude-sonnet-4-0")
        apply_thinking_binding_drop_block(
            payload,
            "claude-sonnet-4-0",
            enabled=True,
            has_thinking_blocks=True,
        )
        assert "block_binding" not in (payload.get("thinking") or {})

    def test_kill_switch_off_untouched(self):
        req = _request_with_thinking()
        headers = anthropic_headers_for_request(
            "sk-test",
            req,
            model="claude-fable-5-1",
            thinking_binding_drop_block=False,
        )
        assert THINKING_BINDING_BETA not in headers.get("anthropic-beta", "")

        payload = to_anthropic_payload(req, model="claude-fable-5-1")
        apply_thinking_binding_drop_block(
            payload,
            "claude-fable-5-1",
            enabled=False,
            has_thinking_blocks=True,
        )
        assert "block_binding" not in (payload.get("thinking") or {})

    def test_client_beta_merged_not_clobbered(self):
        req = _request_with_thinking(beta="context-1m-2025-08-07")
        headers = anthropic_headers_for_request(
            "sk-test", req, model="claude-opus-5-5"
        )
        betas = [b.strip() for b in headers["anthropic-beta"].split(",")]
        assert "context-1m-2025-08-07" in betas
        assert THINKING_BINDING_BETA in betas
        assert betas.count(THINKING_BINDING_BETA) == 1

    def test_no_thinking_blocks_unchanged(self):
        req = _request_plain()
        assert not request_has_thinking_blocks(req)
        headers = anthropic_headers_for_request(
            "sk-test", req, model="claude-sonnet-5-5"
        )
        assert THINKING_BINDING_BETA not in headers.get("anthropic-beta", "")

        payload = to_anthropic_payload(req, model="claude-sonnet-5-5")
        before = dict(payload)
        apply_thinking_binding_drop_block(
            payload,
            "claude-sonnet-5-5",
            enabled=True,
            has_thinking_blocks=False,
        )
        assert payload == before

    def test_existing_thinking_keeps_type_and_gains_binding(self):
        req = _request_with_thinking()
        req.sampling.thinking = {"type": "enabled", "budget_tokens": 1024}
        payload = to_anthropic_payload(req, model="claude-sonnet-5-5")
        apply_thinking_binding_drop_block(
            payload,
            "claude-sonnet-5-5",
            enabled=True,
            has_thinking_blocks=True,
        )
        assert payload["thinking"]["type"] == "enabled"
        assert payload["thinking"]["budget_tokens"] == 1024
        assert payload["thinking"]["block_binding"] == {
            "prefix_mismatch_behavior": "drop_block"
        }


class TestConfigKillSwitch:
    def test_default_true_and_documented(self):
        settings = Settings()
        assert settings.frontier.thinking_binding_drop_block is True
        config = (
            __import__("pathlib").Path("docs/developer/reference/config.md")
            .read_text(encoding="utf-8")
        )
        assert "frontier.thinking_binding_drop_block" in config
