"""Doctor tip for enterprise policy-status (#1163)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.enterprise.policy_sync import (
    clear_policy_status_for_tests,
    policy_content_hash,
    record_policy_apply,
)
from daari.setup.doctor import _check_policy_status, run_doctor

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


@pytest.fixture(autouse=True)
def _reset_policy_status():
    clear_policy_status_for_tests()
    yield
    clear_policy_status_for_tests()


def test_policy_status_skipped_when_unset(settings, tmp_path):
    settings.enterprise.policy_sync_url = None
    result = _check_policy_status(settings, state_path=tmp_path / "missing.json")
    assert result.name == "policy_status"
    assert result.ok
    assert result.optional
    assert "skipped" in result.detail.lower() or "not configured" in result.detail.lower()


def test_policy_status_warns_when_configured_never_applied(tmp_path):
    settings = Settings.model_validate(
        {"enterprise": {"policy_sync_url": "https://org.example/policy"}}
    )
    result = _check_policy_status(settings, state_path=tmp_path / "missing.json")
    assert not result.ok
    assert result.optional
    assert "policy-status" in result.detail
    assert "never" in result.detail.lower()


def test_policy_status_ok_after_apply(tmp_path):
    state = tmp_path / "state.json"
    payload = {"routing": {"prefer": "local"}}
    recorded = record_policy_apply(
        payload,
        url="https://org.example/p",
        state_path=state,
        applied_at=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc),
    )
    settings = Settings.model_validate(
        {"enterprise": {"policy_sync_url": "https://org.example/policy"}}
    )
    clear_policy_status_for_tests()
    result = _check_policy_status(settings, state_path=state)
    assert result.ok
    assert result.optional
    assert "policy-status" in result.detail
    assert recorded.policy_hash in result.detail
    assert policy_content_hash(payload) in result.detail


def test_run_doctor_includes_policy_status(settings):
    settings.enterprise.policy_sync_url = None
    row = next(
        item for item in run_doctor(settings, httpx_client=None) if item.name == "policy_status"
    )
    assert row.ok
    assert row.optional


def test_doctor_health_docs_mention_policy_status() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "policy_status" in text or "policy-status" in text
