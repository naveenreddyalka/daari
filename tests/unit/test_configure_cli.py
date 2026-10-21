"""`daari configure <client>` one-command onboarding (#445)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.cli.configure import CONFIGURE_CLIENTS, configure_client, supported_clients
from daari.clients.registry import default_registry
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
    assert "cursor" in result.output
    assert "chatgpt-desktop" in result.output


def test_configure_help_lists_first_wave_clients():
    result = runner.invoke(app, ["configure", "--help"])
    assert result.exit_code == 0
    for cid in ("cursor", "claude-code", "vscode", "claude-desktop", "chatgpt-desktop"):
        assert cid in result.output


def test_supported_clients_includes_first_wave():
    ids = supported_clients()
    assert "claude-code" in ids
    assert "vscode" in ids
    assert "claude-desktop" in ids


def test_configure_first_wave_subset_of_registry_and_leads_supported():
    """First-wave ⊆ registry; supported_clients starts with that wave (#1827)."""
    registry_ids = set(default_registry().list_ids())
    assert set(CONFIGURE_CLIENTS) <= registry_ids
    for required in (
        "cursor",
        "claude-code",
        "vscode",
        "claude-desktop",
        "chatgpt-desktop",
    ):
        assert required in CONFIGURE_CLIENTS
    ids = supported_clients()
    assert ids[: len(CONFIGURE_CLIENTS)] == list(CONFIGURE_CLIENTS)


def test_verification_hint_cursor_bearer_and_chatgpt_client_header():
    from daari.cli.configure import _verification_hint

    cursor = _verification_hint(
        "cursor", base_url="http://127.0.0.1:11435/v1", api_key="secret"
    )
    assert "Authorization: Bearer secret" in cursor
    assert "/v1/models" in cursor

    chatgpt = _verification_hint(
        "chatgpt-desktop", base_url="http://127.0.0.1:11435/v1", api_key="secret"
    )
    assert "X-Daari-Client-Id: chatgpt-desktop" in chatgpt
    assert "/api/tags" in chatgpt or "/v1/models" in chatgpt


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


def test_supported_clients_includes_chatgpt_desktop():
    assert "chatgpt-desktop" in supported_clients()


def test_configure_chatgpt_desktop_dry_run_prints_ollama_host(home):
    result = runner.invoke(app, ["configure", "chatgpt-desktop", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435 (no /v1)" in result.output
    assert "11434" in result.output
    assert "X-Daari-Client-Id: chatgpt-desktop" in result.output
    assert "Dry-run complete" in result.output


def test_setup_chatgpt_desktop_dry_run(home):
    result = runner.invoke(app, ["setup", "chatgpt-desktop", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435" in result.output
    assert "11435/v1" not in result.output
    assert "Dry-run complete" in result.output


def test_configure_chatgpt_desktop_does_not_write_prefs(home):
    before = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["configure", "chatgpt-desktop"])
    assert result.exit_code == 0
    assert "were not modified" in result.output
    after = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    assert after == before


def test_supported_clients_includes_codex():
    assert "codex" in supported_clients()


def test_configure_codex_dry_run_prints_openai_and_ollama_hosts(home):
    result = runner.invoke(app, ["configure", "codex", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435/v1" in result.output
    assert "ollama launch codex" in result.output
    assert "http://127.0.0.1:11435 (no /v1)" in result.output
    assert "X-Daari-Client-Id: codex" in result.output
    assert "curl" in result.output
    assert "/v1/models" in result.output
    assert "Dry-run complete" in result.output


def test_setup_codex_dry_run(home):
    result = runner.invoke(app, ["setup", "codex", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435/v1" in result.output
    assert "ollama launch codex" in result.output
    assert "http://127.0.0.1:11435 (no /v1)" in result.output
    assert "X-Daari-Client-Id: codex" in result.output
    assert "curl" in result.output
    assert "/v1/models" in result.output
    assert "Dry-run complete" in result.output


def test_configure_codex_does_not_write_config(home):
    before = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["configure", "codex"])
    assert result.exit_code == 0
    assert "were not modified" in result.output
    after = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    assert after == before


def test_codex_guide_linked_from_clients_nav():
    guide = Path("docs/developer/guides/clients/codex.md").read_text(encoding="utf-8")
    assert "http://127.0.0.1:11435/v1" in guide
    assert "ollama launch codex" in guide
    assert "X-Daari-Client-Id: codex" in guide
    nav = Path("mkdocs.yml").read_text(encoding="utf-8")
    assert "developer/guides/clients/codex.md" in nav


def test_supported_clients_includes_opencode():
    assert "opencode" in supported_clients()


def test_configure_opencode_dry_run_prints_v2_snippet(home):
    result = runner.invoke(app, ["configure", "opencode", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435/v1" in result.output
    assert "providers" in result.output
    assert "@opencode/ai/providers/openai-compatible" in result.output
    assert "settings.baseURL" in result.output
    assert "provider.daari.options.baseURL" in result.output
    assert "X-Daari-Client-Id: opencode" in result.output
    assert "{env:DAARI_API_KEY}" in result.output
    assert "curl" in result.output
    assert "Dry-run complete" in result.output


def test_setup_opencode_dry_run(home):
    result = runner.invoke(app, ["setup", "opencode", "--dry-run"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:11435/v1" in result.output
    assert "@opencode/ai/providers/openai-compatible" in result.output
    assert "X-Daari-Client-Id: opencode" in result.output
    assert "Dry-run complete" in result.output


def test_configure_opencode_does_not_write_config(home):
    before = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["configure", "opencode"])
    assert result.exit_code == 0
    assert "were not modified" in result.output
    assert "{env:DAARI_API_KEY}" in result.output
    after = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    assert after == before


def test_configure_and_setup_gemini_cli_do_not_point_native_api_at_daari(home):
    before = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    for args in (
        ["configure", "gemini-cli"],
        ["setup", "gemini-cli"],
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert "native Gemini API is not a daari surface" in result.output
        assert "codex" in result.output
        assert "GOOGLE_GEMINI_BASE_URL" not in result.output
        assert "settings.json" not in result.output
    after = {p.relative_to(home) for p in home.rglob("*") if p.is_file()}
    assert after == before


def test_opencode_guide_linked_from_clients_nav():
    guide = Path("docs/developer/guides/clients/opencode.md").read_text(encoding="utf-8")
    assert "http://127.0.0.1:11435/v1" in guide
    assert "@opencode/ai/providers/openai-compatible" in guide
    assert "provider.daari.options.baseURL" in guide
    assert "X-Daari-Client-Id: opencode" in guide
    assert "{env:DAARI_API_KEY}" in guide
    nav = Path("mkdocs.yml").read_text(encoding="utf-8")
    assert "developer/guides/clients/opencode.md" in nav
