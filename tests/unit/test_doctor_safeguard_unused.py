"""Doctor tip when Ollama lists gpt-oss-safeguard but no decision guardrail uses it (#2032)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import _check_safeguard_unused
from daari.setup.models import SAFEGUARD_MODEL, SAFEGUARD_TAG


def _tags_client(names: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(
                200, json={"models": [{"name": n} for n in names]}
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_safeguard_tip_when_host_has_tag_but_no_decision_rule():
    settings = Settings.model_validate(
        {
            "guardrails": {"enabled": True, "input_rules": []},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_safeguard_unused(
        settings, _tags_client([SAFEGUARD_MODEL, "llama3.1:8b"])
    )
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_safeguard_unused"
    assert SAFEGUARD_TAG in tip.detail
    assert "daari setup models --safeguard" in tip.detail


def test_safeguard_tip_quiet_when_decision_rule_uses_safeguard():
    settings = Settings.model_validate(
        {
            "guardrails": {
                "enabled": True,
                "input_rules": [
                    {
                        "name": "byo_policy",
                        "kind": "decision",
                        "statement": "Does this violate the operator policy?",
                        "model": SAFEGUARD_MODEL,
                        "action": "block",
                    }
                ],
            },
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_safeguard_unused(settings, _tags_client([SAFEGUARD_MODEL])) is None


def test_safeguard_tip_quiet_when_output_rule_uses_safeguard_120b():
    settings = Settings.model_validate(
        {
            "guardrails": {
                "enabled": True,
                "output_rules": [
                    {
                        "name": "egress_policy",
                        "kind": "decision",
                        "statement": "Does this reply violate policy?",
                        "model": "gpt-oss-safeguard:120b",
                        "action": "block",
                    }
                ],
            },
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert (
        _check_safeguard_unused(settings, _tags_client(["gpt-oss-safeguard:120b"]))
        is None
    )


def test_safeguard_tip_quiet_when_tag_absent_on_host():
    settings = Settings.model_validate(
        {
            "guardrails": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_safeguard_unused(settings, _tags_client(["llama3.1:8b"])) is None


def test_safeguard_tip_quiet_when_ollama_unreachable():
    settings = Settings.model_validate(
        {
            "guardrails": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_safeguard_unused(settings, client) is None
