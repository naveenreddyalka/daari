from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from daari.cli.app import app
from daari.clients.cursor.recipe import (
    CURSOR_STORAGE_KEY,
    DAARI_MARKER_KEY,
    CursorSetupRecipe,
)
from daari.clients.claude_code.recipe import ClaudeCodeSetupRecipe
from daari.clients.intellij.recipe import IntelliJSetupRecipe
from daari.clients.vscode.recipe import DAARI_MARKER_KEY as VSCODE_MARKER_KEY
from daari.clients.vscode.recipe import VSCodeSetupRecipe
from daari.config.settings import Settings
from daari.setup.backup import create_backup, latest_backup, restore_latest_backup
from daari.setup.models import fetch_ollama_models, write_models_config


@pytest.fixture
def cursor_home(tmp_path):
    user_dir = tmp_path / "Cursor" / "User"
    user_dir.mkdir(parents=True)
    settings = user_dir / "settings.json"
    settings.write_text('{"window.commandCenter": true,}\n', encoding="utf-8")

    storage_dir = user_dir / "globalStorage"
    storage_dir.mkdir()
    db_path = storage_dir / "state.vscdb"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
        (CURSOR_STORAGE_KEY, json.dumps({"openAIBaseUrl": None, "useOpenAIKey": False})),
    )
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture
def recipe(cursor_home, monkeypatch):
    recipe = CursorSetupRecipe()

    def fake_candidate_paths(self):
        base = cursor_home / "Cursor" / "User"
        return [base / "settings.json"]

    def fake_storage_db_path(self):
        path = cursor_home / "Cursor" / "User" / "globalStorage" / "state.vscdb"
        return path if path.is_file() else None

    monkeypatch.setattr(CursorSetupRecipe, "_candidate_paths", fake_candidate_paths)
    monkeypatch.setattr(CursorSetupRecipe, "_storage_db_path", fake_storage_db_path)
    monkeypatch.setattr(CursorSetupRecipe, "detect", lambda self: True)
    return recipe


@pytest.fixture
def backup_root(tmp_path):
    return tmp_path / "backups"


@pytest.fixture
def intellij_home(tmp_path):
    options = tmp_path / "JetBrains" / "IntelliJIdea2025.1" / "options"
    options.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def intellij_recipe(intellij_home, monkeypatch):
    recipe = IntelliJSetupRecipe()

    def fake_roots(self):
        return [intellij_home / "JetBrains"]

    monkeypatch.setattr(IntelliJSetupRecipe, "_jetbrains_roots", fake_roots)
    return recipe


@pytest.fixture
def vscode_home(tmp_path):
    user_dir = tmp_path / "Code" / "User"
    user_dir.mkdir(parents=True)
    settings = user_dir / "settings.json"
    settings.write_text('{"editor.formatOnSave": true}\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def vscode_recipe(vscode_home, monkeypatch):
    recipe = VSCodeSetupRecipe()

    def fake_candidate_paths(self):
        return [vscode_home / "Code" / "User" / "settings.json"]

    monkeypatch.setattr(VSCodeSetupRecipe, "_candidate_paths", fake_candidate_paths)
    monkeypatch.setattr(VSCodeSetupRecipe, "detect", lambda self: True)
    return recipe


@pytest.fixture
def claude_home(tmp_path):
    home = tmp_path / ".claude"
    home.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def claude_recipe(claude_home, monkeypatch):
    recipe = ClaudeCodeSetupRecipe()
    monkeypatch.setattr("daari.clients.claude_code.recipe.Path.home", lambda: claude_home)
    monkeypatch.setattr("daari.clients.claude_code.recipe.shutil.which", lambda _: "/usr/local/bin/claude")
    return recipe


class TestBackup:
    def test_create_and_restore_roundtrip(self, tmp_path):
        source = tmp_path / "settings.json"
        source.write_text('{"a": 1}\n', encoding="utf-8")
        root = tmp_path / "backups"

        backup = create_backup("cursor", [source], root=root)
        source.write_text('{"a": 999}\n', encoding="utf-8")

        restore = restore_latest_backup("cursor", root=root)
        assert restore.backup_dir == backup.backup_dir
        assert json.loads(source.read_text()) == {"a": 1}


class TestCursorSetupApply:
    def test_apply_patches_settings_and_vscdb(self, recipe, backup_root):
        result = recipe.apply(
            base_url="http://127.0.0.1:11435/v1",
            api_key="daari-local",
            model_name="daari",
            backup_root=backup_root,
        )
        assert result.changed is True
        assert result.backup_dir is not None
        assert len(result.files_changed) == 2

        settings_path = Path(result.files_changed[0])
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert settings["openai.baseUrl"] == "http://127.0.0.1:11435/v1"
        assert settings[DAARI_MARKER_KEY]["model"] == "daari"

        db_path = Path(result.files_changed[1])
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            (CURSOR_STORAGE_KEY,),
        ).fetchone()
        conn.close()
        data = json.loads(row[0])
        assert data["openAIBaseUrl"] == "http://127.0.0.1:11435/v1"
        assert data["useOpenAIKey"] is True
        assert any(item.get("name") == "daari" for item in data["availableAPIKeyModels"])

    def test_apply_is_idempotent_without_force(self, recipe, backup_root):
        recipe.apply(backup_root=backup_root)
        second = recipe.apply(backup_root=backup_root)
        assert second.changed is False
        assert "already configured" in second.message

    def test_apply_force_reapplies(self, recipe, backup_root):
        first = recipe.apply(backup_root=backup_root)
        second = recipe.apply(force=True, backup_root=backup_root)
        assert second.changed is True
        assert second.backup_dir != first.backup_dir

    def test_undo_restores_previous_content(self, recipe, backup_root):
        settings_path = Path(recipe.settings_paths()[0])
        original = settings_path.read_text(encoding="utf-8")

        recipe.apply(backup_root=backup_root)
        assert settings_path.read_text(encoding="utf-8") != original

        undo = recipe.undo(backup_root=backup_root)
        assert settings_path.read_text(encoding="utf-8") == original
        assert latest_backup("cursor", root=backup_root) is not None
        assert undo.files_restored


class TestCursorSetupDryRun:
    def test_dry_run_does_not_write(self, recipe, backup_root):
        settings_path = Path(recipe.settings_paths()[0])
        before = settings_path.read_text(encoding="utf-8")
        plan = recipe.dry_run()
        after = settings_path.read_text(encoding="utf-8")
        assert before == after
        assert plan.client_id == "cursor"
        assert plan.changes


class TestSetupModels:
    def test_write_models_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        result = write_models_config("llama3.2:3b", config_path=config_path)
        assert result.changed is True
        assert "llama3.2:3b" in config_path.read_text(encoding="utf-8")

    def test_fetch_ollama_models(self):
        mock = MagicMock(spec=httpx.Client)
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        mock.get.return_value = response

        models = fetch_ollama_models("http://127.0.0.1:11434", client=mock)
        assert models == ["llama3.2:3b"]


class TestSetupCLI:
    def test_setup_cursor_dry_run(self, recipe, monkeypatch):
        from daari.clients.registry import ClientRegistry

        registry = ClientRegistry()
        registry.register(recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)

        runner = CliRunner()
        result = runner.invoke(app, ["setup", "cursor", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry-run complete" in result.stdout

    def test_setup_models_list(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("models:\n  l3: llama3.2:3b\n", encoding="utf-8")

        def fake_load(config_path_arg=None):
            return Settings.model_validate(
                {
                    "server": {"host": "127.0.0.1", "port": 11435},
                    "models": {"l3": "llama3.2:3b"},
                    "ollama": {"base_url": "http://127.0.0.1:11434"},
                    "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
                }
            )

        monkeypatch.setattr("daari.setup.models.Settings.load", fake_load)
        runner = CliRunner()
        result = runner.invoke(app, ["setup", "models", "--list"])
        assert result.exit_code == 0
        assert "llama3.2:3b" in result.stdout

    def test_setup_intellij_dry_run(self, intellij_recipe, monkeypatch):
        from daari.clients.registry import ClientRegistry

        registry = ClientRegistry()
        registry.register(intellij_recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)

        runner = CliRunner()
        result = runner.invoke(app, ["setup", "intellij", "--dry-run"])
        assert result.exit_code == 0
        assert "Intellij detected: yes" in result.stdout
        assert "Dry-run complete" in result.stdout

    def test_setup_vscode_dry_run(self, vscode_recipe, monkeypatch):
        from daari.clients.registry import ClientRegistry

        registry = ClientRegistry()
        registry.register(vscode_recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)

        runner = CliRunner()
        result = runner.invoke(app, ["setup", "vscode", "--dry-run"])
        assert result.exit_code == 0
        assert "Vscode detected: yes" in result.stdout
        assert "Dry-run complete" in result.stdout

    def test_setup_claude_code_dry_run(self, claude_recipe, monkeypatch):
        from daari.clients.registry import ClientRegistry

        registry = ClientRegistry()
        registry.register(claude_recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)

        runner = CliRunner()
        result = runner.invoke(app, ["setup", "claude-code", "--dry-run"])
        assert result.exit_code == 0
        assert "Claude-code detected: yes" in result.stdout
        assert "Dry-run complete" in result.stdout

    def test_setup_all_runs_known_recipes(self, recipe, intellij_recipe, vscode_recipe, claude_recipe, monkeypatch):
        from daari.clients.registry import ClientRegistry

        registry = ClientRegistry()
        registry.register(claude_recipe)
        registry.register(recipe)
        registry.register(intellij_recipe)
        registry.register(vscode_recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)

        runner = CliRunner()
        result = runner.invoke(app, ["setup", "all", "--dry-run"])
        assert result.exit_code == 0
        assert "== claude-code ==" in result.stdout
        assert "== cursor ==" in result.stdout
        assert "== intellij ==" in result.stdout
        assert "== vscode ==" in result.stdout

    def test_setup_undo_missing_backup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "daari.setup.backup.backups_root",
            lambda root=None: tmp_path / "backups",
        )
        runner = CliRunner()
        result = runner.invoke(app, ["setup", "--undo", "cursor"])
        assert result.exit_code == 1

    def test_setup_openai_compat_writes_env_template(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".daari" / ".env.example"
        monkeypatch.setattr("daari.setup.openai_compat.OPENAI_COMPAT_ENV_PATH", env_path)
        monkeypatch.setattr(
            "daari.cli.app.get_settings",
            lambda: Settings.model_validate(
                {
                    "server": {"host": "127.0.0.1", "port": 11435},
                    "models": {"l3": "llama3.2:3b", "l4": "llama3.1:8b"},
                    "ollama": {"base_url": "http://127.0.0.1:11434"},
                }
            ),
        )
        runner = CliRunner()
        result = runner.invoke(app, ["setup", "openai-compat"])
        assert result.exit_code == 0
        assert "OPENAI_BASE_URL" in result.stdout
        assert env_path.is_file()
        assert "DAARI_FRONTIER_API_KEY" in env_path.read_text(encoding="utf-8")

    def test_setup_frontier_key_snippet(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".daari" / ".env.example"
        monkeypatch.setattr("daari.setup.openai_compat.OPENAI_COMPAT_ENV_PATH", env_path)
        monkeypatch.setattr("daari.setup.openai_compat.Path.home", lambda: tmp_path)
        monkeypatch.setattr(
            "daari.cli.app.get_settings",
            lambda: Settings.model_validate(
                {
                    "server": {"host": "127.0.0.1", "port": 11435},
                    "models": {"l3": "llama3.2:3b", "l4": "llama3.1:8b"},
                    "ollama": {"base_url": "http://127.0.0.1:11434"},
                }
            ),
        )
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["setup", "frontier-key", "--shell", "zsh", "--write-profile-snippet"],
        )
        assert result.exit_code == 0
        profile = tmp_path / ".zshrc"
        assert profile.is_file()
        assert "DAARI_FRONTIER_API_KEY" in profile.read_text(encoding="utf-8")

    def test_context_clear(self, tmp_path, monkeypatch):
        l0 = tmp_path / "cache" / "l0"
        l1 = tmp_path / "cache" / "l1"
        ccs = tmp_path / "context" / "commands"
        for root in (l0, l1, ccs):
            root.mkdir(parents=True, exist_ok=True)
            (root / "artifact.txt").write_text("x", encoding="utf-8")

        monkeypatch.setattr(
            "daari.cli.app.get_settings",
            lambda: Settings.model_validate(
                {
                    "cache": {
                        "l0": {"enabled": True, "path": str(l0)},
                        "l1": {"enabled": True, "path": str(l1)},
                    },
                    "context": {"enabled": True, "path": str(ccs)},
                }
            ),
        )
        runner = CliRunner()
        result = runner.invoke(app, ["context", "clear"])
        assert result.exit_code == 0
        assert not (l0 / "artifact.txt").exists()
        assert not (l1 / "artifact.txt").exists()
        assert not (ccs / "artifact.txt").exists()

    def test_context_clear_prints_restart_note_when_daemon_running(self, tmp_path, monkeypatch):
        l0 = tmp_path / "cache" / "l0"
        l1 = tmp_path / "cache" / "l1"
        ccs = tmp_path / "context" / "commands"
        for root in (l0, l1, ccs):
            root.mkdir(parents=True, exist_ok=True)
            (root / "artifact.txt").write_text("x", encoding="utf-8")

        monkeypatch.setattr(
            "daari.cli.app.get_settings",
            lambda: Settings.model_validate(
                {
                    "cache": {
                        "l0": {"enabled": True, "path": str(l0)},
                        "l1": {"enabled": True, "path": str(l1)},
                    },
                    "context": {"enabled": True, "path": str(ccs)},
                }
            ),
        )
        monkeypatch.setattr("daari.cli.app._daemon_is_running", lambda _settings: True)

        runner = CliRunner()
        result = runner.invoke(app, ["context", "clear"])
        assert result.exit_code == 0
        assert "Restart it now" in result.stdout

    def test_install_forwards_optional_pull_flags(self, monkeypatch):
        captured = {}

        class Result:
            returncode = 0

        def fake_run(cmd, cwd, env, check):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["env"] = env
            captured["check"] = check
            return Result()

        monkeypatch.setattr("daari.cli.app.subprocess.run", fake_run)
        runner = CliRunner()
        result = runner.invoke(app, ["install", "--no-run-doctor", "--pull-l4", "--pull-l5"])
        assert result.exit_code == 0
        assert captured["env"]["RUN_DOCTOR"] == "0"
        assert captured["env"]["PULL_L4"] == "1"
        assert captured["env"]["PULL_L5"] == "1"

    def test_serve_org_flag_enables_org_mode(self, monkeypatch):
        captured = {}

        def fake_load():
            return Settings.model_validate(
                {
                    "server": {"host": "127.0.0.1", "port": 11435},
                    "models": {"l3": "llama3.2:3b"},
                    "ollama": {"base_url": "http://127.0.0.1:11434"},
                }
            )

        def fake_create_app(settings):
            captured["settings"] = settings
            return object()

        def fake_run(_app, host, port, log_level):
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level

        monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
        monkeypatch.setattr("daari.cli.app.create_app", fake_create_app)
        monkeypatch.setattr("daari.cli.app.uvicorn.run", fake_run)

        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--org", "acme", "--port", "11501"])
        assert result.exit_code == 0
        assert captured["settings"].enterprise.enabled is True
        assert captured["settings"].enterprise.org_id == "acme"
        assert captured["port"] == 11501

    def test_org_cache_serve_uses_org_and_port(self, monkeypatch):
        captured = {}

        def fake_load():
            return Settings.model_validate(
                {
                    "enterprise": {"shared_cache_require_token": False},
                }
            )

        def fake_create_org_cache_app(org):
            captured["org"] = org
            return object()

        def fake_run(_app, host, port, log_level):
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level

        monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
        monkeypatch.setattr("daari.cli.app.create_org_cache_app", fake_create_org_cache_app)
        monkeypatch.setattr("daari.cli.app.uvicorn.run", fake_run)

        runner = CliRunner()
        result = runner.invoke(app, ["org-cache", "serve", "--org", "acme", "--port", "11439"])
        assert result.exit_code == 0
        assert captured["org"].org_id == "acme"
        assert captured["port"] == 11439

    def test_org_learning_stats_command(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "daari.cli.app.Settings.load",
            lambda: Settings.model_validate(
                {
                    "enterprise": {
                        "learning_url": "http://127.0.0.1:11436",
                        "learning_enabled": True,
                    }
                }
            ),
        )
        monkeypatch.setattr(
            "daari.enterprise.client.OrgLearningClient.get_stats_sync",
            lambda self: {"feedback_count": 4, "cache_hit_rate": 0.5},
        )
        runner = CliRunner()
        result = runner.invoke(app, ["org-learning", "stats"])
        assert result.exit_code == 0
        assert '"feedback_count": 4' in result.stdout

    def test_org_learning_export_command_writes_output(self, monkeypatch, tmp_path):
        output = tmp_path / "learning.json"
        monkeypatch.setattr(
            "daari.cli.app.Settings.load",
            lambda: Settings.model_validate(
                {
                    "enterprise": {
                        "learning_url": "http://127.0.0.1:11436",
                        "learning_enabled": True,
                    }
                }
            ),
        )
        monkeypatch.setattr(
            "daari.enterprise.client.OrgLearningClient.export_sync",
            lambda self: {"org_id": "acme", "metrics": {"feedback_count": 1}},
        )
        runner = CliRunner()
        result = runner.invoke(app, ["org-learning", "export", "--output", str(output)])
        assert result.exit_code == 0
        assert output.is_file()
        assert '"org_id": "acme"' in output.read_text(encoding="utf-8")

    def test_web_ui_serve_mounts_static_assets(self, monkeypatch):
        captured = {}

        def fake_run(app_instance, host, port, log_level):
            captured["app"] = app_instance
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level

        monkeypatch.setattr("daari.cli.app.uvicorn.run", fake_run)
        runner = CliRunner()
        result = runner.invoke(app, ["web-ui", "serve", "--port", "11439"])
        assert result.exit_code == 0
        assert captured["port"] == 11439
        assert captured["host"] == "127.0.0.1"
        client = TestClient(captured["app"])
        response = client.get("/")
        assert response.status_code == 200
        assert "daari stats dashboard" in response.text


class TestIntelliJSetupApply:
    def test_apply_writes_helper_file(self, intellij_recipe, backup_root):
        result = intellij_recipe.apply(backup_root=backup_root)
        assert result.changed is True
        assert len(result.files_changed) == 1
        payload = json.loads(Path(result.files_changed[0]).read_text(encoding="utf-8"))
        assert payload["managed_by"] == "daari"
        assert payload["model"] == "daari"

    def test_apply_idempotent(self, intellij_recipe, backup_root):
        intellij_recipe.apply(backup_root=backup_root)
        second = intellij_recipe.apply(backup_root=backup_root)
        assert second.changed is False
        assert "already configured" in second.message


class TestVSCodeSetupApply:
    def test_apply_writes_settings(self, vscode_recipe, backup_root):
        result = vscode_recipe.apply(backup_root=backup_root)
        assert result.changed is True
        payload = json.loads(Path(result.files_changed[0]).read_text(encoding="utf-8"))
        assert payload["openai.baseUrl"] == "http://127.0.0.1:11435/v1"
        assert payload[VSCODE_MARKER_KEY]["model"] == "daari"

    def test_apply_idempotent(self, vscode_recipe, backup_root):
        vscode_recipe.apply(backup_root=backup_root)
        second = vscode_recipe.apply(backup_root=backup_root)
        assert second.changed is False
        assert "already configured" in second.message


class TestClaudeCodeSetupApply:
    def test_apply_writes_env_and_pointer(self, claude_recipe, backup_root):
        result = claude_recipe.apply(backup_root=backup_root)
        assert result.changed is True
        env_file = Path(result.files_changed[0])
        pointer = Path(result.files_changed[1])
        assert "OPENAI_BASE_URL=http://127.0.0.1:11435/v1" in env_file.read_text(encoding="utf-8")
        assert "env_file=" in pointer.read_text(encoding="utf-8")

    def test_apply_idempotent(self, claude_recipe, backup_root):
        claude_recipe.apply(backup_root=backup_root)
        second = claude_recipe.apply(backup_root=backup_root)
        assert second.changed is False
        assert "already configured" in second.message
