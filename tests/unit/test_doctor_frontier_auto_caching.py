"""Doctor tip when frontier.auto_caching is on without an Anthropic L6 slot (#2321)."""

from __future__ import annotations

from pathlib import Path

from daari.config.settings import FrontierProviderConfig
from daari.setup.doctor import _check_frontier_auto_caching, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def _down_client():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tips_when_auto_caching_on_with_openai_only(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.provider = "openai"
    settings.frontier.base_url = "https://api.openai.com/v1"
    settings.frontier.providers = []
    row = _check_frontier_auto_caching(settings)
    assert row.name == "frontier_auto_caching"
    assert row.ok is False
    assert row.optional is True
    detail = row.detail
    assert "frontier.auto_caching" in detail
    assert "Anthropic" in detail
    assert "no-op" in detail.lower()
    assert "off" in detail.lower()


def test_tips_when_pool_has_only_openai_slots(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.providers = [
        FrontierProviderConfig(id="openai", base_url="https://api.openai.com/v1"),
        FrontierProviderConfig(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="anthropic/claude-sonnet-5-5",
        ),
    ]
    row = _check_frontier_auto_caching(settings)
    assert row.ok is False
    assert row.optional is True


def test_quiet_when_auto_caching_off(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = False
    settings.frontier.provider = "openai"
    row = _check_frontier_auto_caching(settings)
    assert row.ok is True
    assert row.optional is True
    assert "auto_caching=false" in row.detail


def test_quiet_when_scalar_provider_is_anthropic(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.provider = "anthropic"
    settings.frontier.base_url = "https://api.anthropic.com"
    settings.frontier.providers = []
    row = _check_frontier_auto_caching(settings)
    assert row.ok is True
    assert row.optional is True


def test_quiet_when_pool_has_anthropic_slot_by_id(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.provider = "openai"
    settings.frontier.providers = [
        FrontierProviderConfig(id="openai", base_url="https://api.openai.com/v1"),
        FrontierProviderConfig(
            id="claude", base_url="https://proxy.example.internal/v1", model="claude-sonnet-5-5"
        ),
    ]
    assert _check_frontier_auto_caching(settings).ok is True


def test_quiet_when_pool_has_anthropic_slot_by_base_url(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.provider = "openai"
    settings.frontier.providers = [
        FrontierProviderConfig(id="primary", base_url="https://api.anthropic.com"),
    ]
    assert _check_frontier_auto_caching(settings).ok is True


def test_run_doctor_includes_check(settings):
    settings.frontier.enabled = True
    settings.frontier.auto_caching = True
    settings.frontier.provider = "openai"
    settings.frontier.providers = []
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "frontier_auto_caching" in by_name
    assert by_name["frontier_auto_caching"].ok is False
    assert by_name["frontier_auto_caching"].optional is True


def test_doctor_health_documents_row():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "doctor `frontier_auto_caching`" in text
    assert "frontier.auto_caching" in text
