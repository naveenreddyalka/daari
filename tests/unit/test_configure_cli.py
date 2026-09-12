"""`daari configure <client>` one-command onboarding (#445)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.cli.configure import configure_client, supported_clients
from daari.config.settings import Settings


runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # Linux Claude Desktop / VS Code paths under XDG.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    return tmp_path


def test_unknown_client_lists_supported_and_exits_1(home):
    result = runner.invoke(app, ["configure", "not-a-client"])
    assert result.exit_code == 1
    assert "Unknown client" in result.output
    assert "claude-code" in result.output
    assert "vscode" in result.output


def test_supported_clients_includes_first_wave():
    ids = supported_clients()
    assert "claude-code" in ids
    assert "vscode" in ids
    assert "claude-desktop" in ids


def test_configure_claude_code_writes_settings(home, monkeypatch):
    settings = Settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = 11435
    monkeypatch.setattr("daari.cli.configure.get_settings", lambda: settings)

    configure_client("claude-code", settings=settings)
    path = home / ".claude" / "settings.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:11435"
    assert data["env"]["ANTHROPIC_AUTH_TOKEN"] == "daari-local"
    assert data["env"]["ANTHROPIC_MODEL"] == "daari"


def test_configure_claude_code_dry_run_no_write(home, monkeypatch):
    settings = Settings()
    monkeypatch.setattr("daari.cli.configure.get_settings", lambda: settings)
    configure_client("claude-code", dry_run=True, settings=settings)
    assert not (home / ".claude" / "settings.json").exists()


def test_configure_claude_code_idempotent(home, monkeypatch):
    settings = Settings()
    monkeypatch.setattr("daari.cli.configure.get_settings", lambda: settings)
    configure_client("claude-code", settings=settings)
    path = home / ".claude" / "settings.json"
    first = path.read_text(encoding="utf-8")
    # Capture stdout via CliRunner for message.
    result = runner.invoke(app, ["configure", "claude-code"])
    assert result.exit_code == 0
    assert "already configured" in result.output.lower()
    assert path.read_text(encoding="utf-8") == first
    assert "Verify:" in result.output


def test_configure_vscode_writes_settings(home, monkeypatch):
    # Pretend VS Code is installed.
    code_dir = home / ".config" / "Code" / "User"
    code_dir.mkdir(parents=True)
    (code_dir / "settings.json").write_text("{}\n", encoding="utf-8")
    # detect() checks for Code binary or dir — recipe looks at candidate paths.
    settings = Settings()
    monkeypatch.setattr("daari.cli.configure.get_settings", lambda: settings)
    monkeypatch.setattr(
        "daari.clients.vscode.recipe.VSCodeSetupRecipe.detect",
        lambda self: True,
    )
    configure_client("vscode", settings=settings)
    data = json.loads((code_dir / "settings.json").read_text(encoding="utf-8"))
    assert data["openai.baseUrl"] == "http://127.0.0.1:11435/v1"
    assert data["openai.apiKey"] == "daari-local"


def test_configure_claude_desktop_writes_config(home, monkeypatch):
    settings = Settings()
    monkeypatch.setattr("daari.cli.configure.get_settings", lambda: settings)
    monkeypatch.setattr(
        "daari.clients.claude_desktop.recipe.ClaudeDesktopSetupRecipe.detect",
        lambda self: True,
    )
    configure_client("claude-desktop", settings=settings)
    path = home / ".config" / "Claude-3p" / "configLibrary" / "daari.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["inferenceProvider"] == "gateway"
    assert data["inferenceGatewayBaseUrl"] == "http://127.0.0.1:11435"
    assert data["inferenceGatewayApiKey"] == "daari-local"
