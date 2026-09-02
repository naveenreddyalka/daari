from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.clients.base import ClientSetupRecipe
from daari.clients.claude_desktop.recipe import (
    CONFIG_FILE_NAME,
    ClaudeDesktopSetupRecipe,
    desired_config,
)
from daari.clients.registry import ClientRegistry, default_registry

MODULE = "daari.clients.claude_desktop.recipe"


@pytest.fixture
def desktop_home(tmp_path):
    return tmp_path


@pytest.fixture
def recipe(desktop_home, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.Path.home", lambda: desktop_home)
    monkeypatch.setattr(
        f"{MODULE}._app_data_root",
        lambda: desktop_home / "Library" / "Application Support",
    )
    monkeypatch.setattr(f"{MODULE}._app_bundle_present", lambda: False)
    (desktop_home / "Library" / "Application Support" / "Claude").mkdir(parents=True)
    return ClaudeDesktopSetupRecipe()


@pytest.fixture
def undetected_recipe(desktop_home, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.Path.home", lambda: desktop_home)
    monkeypatch.setattr(
        f"{MODULE}._app_data_root",
        lambda: desktop_home / "Library" / "Application Support",
    )
    monkeypatch.setattr(f"{MODULE}._app_bundle_present", lambda: False)
    return ClaudeDesktopSetupRecipe()


@pytest.fixture
def backup_root(tmp_path):
    return tmp_path / "backups"


def _config_file(desktop_home: Path) -> Path:
    return (
        desktop_home
        / "Library"
        / "Application Support"
        / "Claude-3p"
        / "configLibrary"
        / CONFIG_FILE_NAME
    )


class TestDesiredConfig:
    def test_gateway_keys_use_documented_names(self):
        cfg = desired_config(
            base_url="http://127.0.0.1:11435/v1", api_key="daari-local", model_name="daari"
        )
        assert cfg["inferenceProvider"] == "gateway"
        # Claude Desktop appends /v1/messages itself, like Claude Code.
        assert cfg["inferenceGatewayBaseUrl"] == "http://127.0.0.1:11435"
        assert cfg["inferenceGatewayApiKey"] == "daari-local"
        assert cfg["inferenceGatewayAuthScheme"] == "x-api-key"
        assert cfg["inferenceModels"][0]["name"] == "daari"

    def test_no_dotted_keys_and_native_json_types(self):
        cfg = desired_config(base_url="http://h:1/v1", api_key="k", model_name="m")
        assert all("." not in key for key in cfg)
        assert isinstance(cfg["inferenceModels"], list)


class TestProtocolAndRegistry:
    def test_recipe_satisfies_protocol(self):
        assert isinstance(ClaudeDesktopSetupRecipe(), ClientSetupRecipe)

    def test_registered_in_default_registry(self):
        assert "claude-desktop" in default_registry().list_ids()


class TestDetect:
    def test_detects_app_data_dir(self, recipe):
        assert recipe.detect() is True

    def test_detects_app_bundle(self, undetected_recipe, monkeypatch):
        monkeypatch.setattr(f"{MODULE}._app_bundle_present", lambda: True)
        assert undetected_recipe.detect() is True

    def test_not_detected_when_absent(self, undetected_recipe):
        assert undetected_recipe.detect() is False


class TestDryRun:
    def test_dry_run_does_not_write(self, recipe, desktop_home):
        plan = recipe.dry_run(
            base_url="http://127.0.0.1:11435/v1", api_key="daari-local", model_name="daari"
        )
        assert plan.client_id == "claude-desktop"
        assert plan.detected is True
        assert plan.changes[0].action == "would_create"
        assert "inferenceGatewayBaseUrl=http://127.0.0.1:11435" in plan.changes[0].detail
        assert not _config_file(desktop_home).exists()

    def test_dry_run_reports_patch_when_present(self, recipe, desktop_home):
        target = _config_file(desktop_home)
        target.parent.mkdir(parents=True)
        target.write_text("{}", encoding="utf-8")
        plan = recipe.dry_run(base_url="http://h:1/v1", api_key="k", model_name="m")
        assert plan.changes[0].action == "would_patch"

    def test_dry_run_notes_missing_app(self, undetected_recipe):
        plan = undetected_recipe.dry_run(base_url="http://h:1/v1", api_key="k", model_name="m")
        assert plan.detected is False
        assert any("not detected" in note for note in plan.notes)


class TestApply:
    def test_apply_writes_config_library_file(self, recipe, desktop_home, backup_root):
        result = recipe.apply(backup_root=backup_root)
        assert result.changed is True
        target = _config_file(desktop_home)
        assert result.files_changed == [str(target)]
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["inferenceProvider"] == "gateway"
        assert data["inferenceGatewayBaseUrl"] == "http://127.0.0.1:11435"
        assert data["inferenceGatewayApiKey"] == "daari-local"
        assert result.backup_dir is None

    def test_apply_idempotent(self, recipe, backup_root):
        recipe.apply(backup_root=backup_root)
        second = recipe.apply(backup_root=backup_root)
        assert second.changed is False
        assert "already configured" in second.message

    def test_apply_force_rewrites(self, recipe, backup_root):
        recipe.apply(backup_root=backup_root)
        forced = recipe.apply(backup_root=backup_root, force=True)
        assert forced.changed is True
        assert forced.backup_dir is not None

    def test_apply_backs_up_existing_file(self, recipe, desktop_home, backup_root):
        target = _config_file(desktop_home)
        target.parent.mkdir(parents=True)
        target.write_text('{"inferenceProvider": "anthropic"}\n', encoding="utf-8")
        result = recipe.apply(backup_root=backup_root)
        assert result.changed is True
        assert result.backup_dir is not None
        assert (result.backup_dir / f"00_{CONFIG_FILE_NAME}").read_text(
            encoding="utf-8"
        ).startswith('{"inferenceProvider": "anthropic"}')

    def test_apply_skips_when_not_installed(self, undetected_recipe, desktop_home, backup_root):
        result = undetected_recipe.apply(backup_root=backup_root)
        assert result.changed is False
        assert "not detected" in result.message
        assert not _config_file(desktop_home).exists()

    def test_apply_recovers_from_corrupt_file(self, recipe, desktop_home, backup_root):
        target = _config_file(desktop_home)
        target.parent.mkdir(parents=True)
        target.write_text("{not json", encoding="utf-8")
        result = recipe.apply(backup_root=backup_root)
        assert result.changed is True
        assert result.backup_dir is not None
        assert json.loads(target.read_text(encoding="utf-8"))["inferenceProvider"] == "gateway"


class TestUndo:
    def test_undo_restores_backup(self, recipe, desktop_home, backup_root):
        target = _config_file(desktop_home)
        target.parent.mkdir(parents=True)
        original = '{"inferenceProvider": "anthropic"}\n'
        target.write_text(original, encoding="utf-8")
        recipe.apply(backup_root=backup_root)
        result = recipe.undo(backup_root=backup_root)
        assert str(target) in result.files_restored
        assert target.read_text(encoding="utf-8") == original

    def test_undo_without_backup_removes_daari_file(self, recipe, desktop_home, backup_root):
        recipe.apply(backup_root=backup_root)
        target = _config_file(desktop_home)
        assert target.is_file()
        result = recipe.undo(backup_root=backup_root)
        assert result.backup_dir is None
        assert str(target) in result.files_restored
        assert not target.exists()

    def test_undo_without_backup_leaves_foreign_file(self, recipe, desktop_home, backup_root):
        recipe.apply(backup_root=backup_root)
        target = _config_file(desktop_home)
        target.write_text('{"inferenceProvider": "vertex"}\n', encoding="utf-8")
        shutil.rmtree(backup_root, ignore_errors=True)
        with pytest.raises(FileNotFoundError):
            recipe.undo(backup_root=backup_root)
        assert target.exists()

    def test_undo_nothing_to_do(self, recipe, backup_root):
        with pytest.raises(FileNotFoundError):
            recipe.undo(backup_root=backup_root)


class TestCli:
    def test_setup_claude_desktop_dry_run(self, recipe, monkeypatch, desktop_home):
        registry = ClientRegistry()
        registry.register(recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)
        result = CliRunner().invoke(app, ["setup", "claude-desktop", "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "Claude-desktop detected: yes" in result.stdout
        assert "Dry-run complete" in result.stdout
        assert not _config_file(desktop_home).exists()

    def test_setup_all_skips_missing_app(self, undetected_recipe, monkeypatch):
        registry = ClientRegistry()
        registry.register(undetected_recipe)
        monkeypatch.setattr("daari.cli.setup_actions.default_registry", lambda: registry)
        result = CliRunner().invoke(app, ["setup", "all"])
        assert result.exit_code == 0, result.stdout
        assert "== claude-desktop ==" in result.stdout
        assert "not detected" in result.stdout
