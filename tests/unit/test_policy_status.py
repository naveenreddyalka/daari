"""Policy-sync drift hash and policy-status (#1138)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.enterprise.policy_sync import (
    clear_policy_status_for_tests,
    load_policy_status,
    policy_content_hash,
    record_policy_apply,
    redact_policy_url,
)


@pytest.fixture(autouse=True)
def _reset_policy_status():
    clear_policy_status_for_tests()
    yield
    clear_policy_status_for_tests()


def test_policy_hash_stable_across_runs():
    payload = {"routing": {"prefer": "local"}, "schema": 1}
    assert policy_content_hash(payload) == policy_content_hash(
        {"schema": 1, "routing": {"prefer": "local"}}
    )


def test_policy_hash_changes_when_payload_mutates():
    base = {"routing": {"prefer": "local"}}
    mutated = {"routing": {"prefer": "frontier"}}
    assert policy_content_hash(base) != policy_content_hash(mutated)


def test_redact_policy_url_strips_path_and_query():
    assert (
        redact_policy_url("https://org.example/v1/policy?token=secret")
        == "https://org.example"
    )


def test_record_and_load_status(tmp_path):
    state = tmp_path / "policy-sync-state.json"
    payload = {"routing": {"confidence_threshold": 0.7}}
    when = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    recorded = record_policy_apply(
        payload,
        url="https://org.example/policy?token=x",
        applied_at=when,
        state_path=state,
    )
    assert recorded.applied is True
    assert recorded.policy_hash == policy_content_hash(payload)
    assert recorded.source_url == "https://org.example"
    clear_policy_status_for_tests()
    loaded = load_policy_status(state_path=state)
    assert loaded.policy_hash == recorded.policy_hash
    assert loaded.applied_at == recorded.applied_at
    assert loaded.source_url == "https://org.example"


def test_never_applied_status_when_configured(tmp_path):
    settings = Settings.model_validate(
        {"enterprise": {"policy_sync_url": "https://org.example/policy"}}
    )
    status = load_policy_status(settings=settings, state_path=tmp_path / "missing.json")
    assert status.configured is True
    assert status.applied is False


def test_cli_policy_status_exits_nonzero_when_configured_never_applied(tmp_path, monkeypatch):
    settings = Settings.model_validate(
        {"enterprise": {"policy_sync_url": "https://org.example/policy"}}
    )
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.DEFAULT_POLICY_STATE_PATH",
        tmp_path / "missing.json",
    )
    clear_policy_status_for_tests()
    result = CliRunner().invoke(cli_app, ["enterprise", "policy-status"])
    assert result.exit_code == 1, result.output
    assert "never successfully applied" in result.output


def test_cli_policy_status_prints_hash_after_apply(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    payload = {"routing": {"prefer": "local"}}
    record_policy_apply(
        payload,
        url="https://org.example/p",
        state_path=state,
        applied_at=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc),
    )
    settings = Settings()
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.load_policy_status",
        lambda settings=None, state_path=None: load_policy_status(
            settings=settings, state_path=state
        ),
    )
    result = CliRunner().invoke(cli_app, ["enterprise", "policy-status"])
    assert result.exit_code == 0, result.output
    assert policy_content_hash(payload) in result.output
    assert "https://org.example" in result.output
