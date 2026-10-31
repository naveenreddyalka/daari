"""Doctor tip when body cap sits below Anthropic Messages limits (#2031)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_body_cap_below_provider, run_doctor

_32_MIB = 32 * 1024 * 1024
_10_MIB = 10 * 1024 * 1024


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _anthropic_frontier(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.provider = "anthropic"
    settings.frontier.base_url = "https://api.anthropic.com"
    settings.frontier.model = "claude-sonnet-4-5"


def test_warns_when_anthropic_and_default_cap(settings):
    _anthropic_frontier(settings)
    settings.server.max_body_bytes = _10_MIB
    result = _check_body_cap_below_provider(settings)
    assert result is not None
    assert result.name == "body_cap_below_provider"
    assert result.ok is False
    assert result.optional is True
    assert "128" in result.detail
    assert "DAARI_SERVER__MAX_BODY_BYTES" in result.detail
    assert str(_10_MIB) in result.detail or "10" in result.detail


def test_warns_when_anthropic_via_providers_list(settings):
    settings.frontier.enabled = True
    settings.frontier.provider = "openai"
    settings.frontier.providers = [
        {
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com",
            "model": "claude-sonnet-4-5",
            "api_key": "sk-ant-test",
        }
    ]
    settings.server.max_body_bytes = _10_MIB
    result = _check_body_cap_below_provider(settings)
    assert result is not None
    assert result.ok is False


def test_quiet_when_cap_disabled(settings):
    _anthropic_frontier(settings)
    settings.server.max_body_bytes = 0
    result = _check_body_cap_below_provider(settings)
    assert result is None or result.ok is True


def test_quiet_when_cap_at_or_above_32_mib(settings):
    _anthropic_frontier(settings)
    settings.server.max_body_bytes = _32_MIB
    result = _check_body_cap_below_provider(settings)
    assert result is None or result.ok is True
    settings.server.max_body_bytes = _32_MIB + 1
    result = _check_body_cap_below_provider(settings)
    assert result is None or result.ok is True


def test_quiet_when_no_anthropic_path(settings):
    settings.frontier.enabled = True
    settings.frontier.provider = "openai"
    settings.frontier.base_url = "https://api.openai.com/v1"
    settings.frontier.providers = []
    settings.server.max_body_bytes = _10_MIB
    result = _check_body_cap_below_provider(settings)
    assert result is None or result.ok is True


def test_quiet_when_frontier_disabled(settings):
    settings.frontier.enabled = False
    settings.frontier.provider = "anthropic"
    settings.server.max_body_bytes = _10_MIB
    result = _check_body_cap_below_provider(settings)
    assert result is None or result.ok is True


def test_run_doctor_includes_tip(settings):
    _anthropic_frontier(settings)
    settings.server.max_body_bytes = _10_MIB
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "body_cap_below_provider" in by_name
    assert by_name["body_cap_below_provider"].ok is False
