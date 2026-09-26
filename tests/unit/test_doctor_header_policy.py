"""Doctor warns when header_policy is enabled but empty/malformed (#1112)."""

from __future__ import annotations

from daari.config.settings import HeaderDenyRule, HeaderPolicySettings
from daari.setup.doctor import _check_header_policy, run_doctor


def test_disabled_header_policy_ok(settings):
    settings.server.header_policy = HeaderPolicySettings(enabled=False)
    result = _check_header_policy(settings)
    assert result.name == "header_policy"
    assert result.ok
    assert result.optional


def test_enabled_with_rules_ok(settings):
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        required=["X-Client-Id"],
    )
    result = _check_header_policy(settings)
    assert result.ok


def test_enabled_empty_warns(settings):
    settings.server.header_policy = HeaderPolicySettings(enabled=True)
    result = _check_header_policy(settings)
    assert not result.ok
    assert result.optional
    assert "empty" in result.detail.lower()


def test_enabled_bad_regex_warns(settings):
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        deny=[HeaderDenyRule(header="user-agent", regex="[unterminated")],
    )
    result = _check_header_policy(settings)
    assert not result.ok
    assert result.optional
    assert "regex" in result.detail.lower() or "malformed" in result.detail.lower()


def test_run_doctor_includes_header_policy(settings):
    names = [item.name for item in run_doctor(settings, httpx_client=None)]
    assert "header_policy" in names
