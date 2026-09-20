"""daari config validate and strict nested-key checking (#710)."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.setup.doctor import run_doctor

CLEAN = "server:\n  port: 11435\n"
NESTED = (
    "server:\n  port: 11436\n"
    "cache:\n  l0:\n    future_knob: 3\n"
    "routing:\n  category_policies:\n    chat:\n      tier: L3\n      not_a_policy: true\n"
)


def _write(tmp_path, text: str):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_config_validates(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(tmp_path, CLEAN)
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 0, result.output
    assert "config ok" in result.stdout


def test_unknown_nested_keys_at_two_depths(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DAARI_STRICT_CONFIG", raising=False)
    path = _write(tmp_path, NESTED)
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 1
    assert "unknown key: cache.l0.future_knob" in result.stderr
    assert "unknown key: routing.category_policies.chat.not_a_policy" in result.stderr

    caplog.set_level(logging.WARNING, logger="daari.config")
    settings = Settings.load(config_path=path)
    assert settings.server.port == 11436
    assert any("cache.l0.future_knob" in rec.message for rec in caplog.records)
    assert any(
        "routing.category_policies.chat.not_a_policy" in rec.message for rec in caplog.records
    )


def test_type_error_and_out_of_range(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _write(
        tmp_path,
        "server:\n  port: eleven\nfrontier:\n  confidence_threshold: 5\n",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 1
    assert "server.port" in result.stderr
    assert "frontier.confidence_threshold" in result.stderr


def test_strict_mode_and_env_reject_unknown_nested_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DAARI_STRICT_CONFIG", raising=False)
    path = _write(tmp_path, "cache:\n  l0:\n    future_knob: 1\n")
    with pytest.raises(ValidationError, match="future_knob"):
        Settings.load(config_path=path, strict=True)
    monkeypatch.setenv("DAARI_STRICT_CONFIG", "1")
    with pytest.raises(ValidationError, match="cache.l0.future_knob"):
        Settings.load(config_path=path)


def test_doctor_mentions_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DAARI_STRICT_CONFIG", raising=False)
    config_dir = tmp_path / ".daari"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "cache:\n  l0:\n    future_knob: 2\n", encoding="utf-8"
    )
    results = run_doctor(Settings.load(config_path=config_dir / "config.yaml"))
    row = next(item for item in results if item.name == "config_keys")
    assert row.ok is False
    assert "cache.l0.future_knob" in row.detail
    assert row.optional is True


def test_asr_frontier_fallback_disabled_frontier(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = _write(
        tmp_path,
        "asr:\n  frontier_fallback: true\nfrontier:\n  enabled: false\n",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 1
    assert "asr.frontier_fallback is true but frontier.enabled is false" in result.stderr


def test_asr_frontier_fallback_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = _write(
        tmp_path,
        "asr:\n  frontier_fallback: true\nfrontier:\n  enabled: true\n",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 1
    assert "asr.frontier_fallback is true but no frontier API key resolves" in result.stderr


def test_asr_with_base_url_passes_even_if_fallback_on(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = _write(
        tmp_path,
        "asr:\n  base_url: http://asr.local/v1\n  frontier_fallback: true\n"
        "frontier:\n  enabled: true\n",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(path)])
    assert result.exit_code == 0, result.output
    assert "config ok" in result.stdout
