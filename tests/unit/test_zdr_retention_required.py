"""ZDR honesty for retention-required Claude Fable/Mythos models (#2284)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.provider_prefs import (
    ProviderPreferences,
    ZdrRetentionConflict,
    require_zdr_retention_ok,
)
from daari.router.capabilities import (
    anthropic_capabilities,
    is_retention_required_model,
)
from daari.setup.doctor import _check_zdr_retention_required


@pytest.mark.parametrize(
    "model",
    (
        "claude-fable-5-1",
        "claude-fable-5-2",
        "claude-mythos-5-1",
        "claude-mythos-5-2",
        "anthropic.claude-fable-5-2",
        "claude-fable-5-2-20261109",
        "claude-mythos-5-2-20261109",
    ),
)
def test_retention_required_models_detected(model):
    assert is_retention_required_model(model) is True


@pytest.mark.parametrize(
    "model",
    ("claude-opus-5-5", "claude-sonnet-5-5", "gpt-6-astra", "llama3.2:3b"),
)
def test_non_retention_models_ok(model):
    assert is_retention_required_model(model) is False


def test_capabilities_mark_retention_required():
    caps = anthropic_capabilities("claude-fable-5-2")
    assert caps.get("retention", {}).get("required") is True
    assert caps.get("retention", {}).get("zero_data_retention") is False
    opus = anthropic_capabilities("claude-opus-5-5")
    assert opus.get("retention", {}).get("required") is not True


def test_zdr_plus_fable_raises():
    with pytest.raises(ZdrRetentionConflict, match="claude-fable-5-2") as exc:
        require_zdr_retention_ok(
            ProviderPreferences(zdr=True),
            "claude-fable-5-2",
            authorized=(),
        )
    assert "30-day" in str(exc.value).lower() or "retention" in str(exc.value).lower()
    assert "zero" in str(exc.value).lower() or "zdr" in str(exc.value).lower()


def test_override_allows_retention_model():
    require_zdr_retention_ok(
        ProviderPreferences(zdr=True),
        "claude-fable-5-2",
        authorized=("claude-fable-5-2",),
    )


def test_zdr_plus_non_retention_unaffected():
    require_zdr_retention_ok(
        ProviderPreferences(zdr=True),
        "claude-opus-5-5",
        authorized=(),
    )


def test_no_zdr_skips_check():
    require_zdr_retention_ok(
        ProviderPreferences(zdr=False),
        "claude-fable-5-2",
        authorized=(),
    )
    require_zdr_retention_ok(None, "claude-fable-5-2", authorized=())


def test_settings_retention_authorized_knob():
    settings = Settings.model_validate(
        {"models": {"retention_authorized": ["claude-fable-5-2"]}}
    )
    assert "claude-fable-5-2" in settings.models.retention_authorized


def test_doctor_tips_zdr_slot_with_retention_model():
    settings = Settings()
    settings.frontier.enabled = True
    settings.frontier.providers = []
    settings.frontier.model = "claude-fable-5-2"
    # Slot-level zdr on the single frontier config.
    from daari.config.settings import FrontierProviderConfig

    settings.frontier.providers = [
        FrontierProviderConfig(
            id="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-fable-5-2",
            zdr=True,
        )
    ]
    result = _check_zdr_retention_required(settings)
    assert result is not None
    assert result.ok is False
    assert result.optional is True
    assert "claude-fable-5-2" in result.detail
    assert "retention" in result.detail.lower() or "zdr" in result.detail.lower()


def test_doctor_quiet_when_authorized_or_no_zdr():
    settings = Settings()
    settings.frontier.enabled = True
    from daari.config.settings import FrontierProviderConfig

    settings.frontier.providers = [
        FrontierProviderConfig(
            id="anthropic",
            base_url="https://api.anthropic.com",
            model="claude-fable-5-2",
            zdr=True,
        )
    ]
    settings.models.retention_authorized = ["claude-fable-5-2"]
    assert _check_zdr_retention_required(settings) is None

    settings.models.retention_authorized = []
    settings.frontier.providers[0].zdr = False
    assert _check_zdr_retention_required(settings) is None
