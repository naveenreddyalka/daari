from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.clients.cursor.recipe import (
    CURSOR_STORAGE_KEY,
    DAARI_MARKER_KEY,
    CursorSetupRecipe,
)
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
