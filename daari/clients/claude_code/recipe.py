from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupChange, SetupPlan
from daari.setup.backup import create_backup, restore_latest_backup

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"

# Env vars Claude Code reads from the `env` block of ~/.claude/settings.json.
_ENV_BASE_URL = "ANTHROPIC_BASE_URL"
_ENV_AUTH_TOKEN = "ANTHROPIC_AUTH_TOKEN"
_ENV_MODEL = "ANTHROPIC_MODEL"


@dataclass
class ApplyResult:
    changed: bool
    backup_dir: Path | None = None
    files_changed: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class UndoResult:
    backup_dir: Path
    files_restored: list[str]


def _anthropic_base_url(base_url: str) -> str:
    """Claude Code appends /v1/messages itself, so strip a trailing /v1."""
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed


class ClaudeCodeSetupRecipe:
    id = "claude-code"

    def detect(self) -> bool:
        return shutil.which("claude") is not None or (Path.home() / ".claude").exists()

    def settings_paths(self) -> list[str]:
        return [str(self._settings_file())]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        settings_file = self._settings_file()
        detected = self.detect()
        anthropic_url = _anthropic_base_url(base_url)
        notes = [
            "Dry-run only — no files will be modified.",
            "This recipe merges an `env` block into ~/.claude/settings.json "
            "(ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN). Claude Code picks it up "
            "on next launch — no manual sourcing needed.",
            "Note: only plain chat routes through daari today; Claude Code tool/agent "
            "turns need Anthropic tool passthrough (tracked separately).",
        ]
        action = "would_patch" if settings_file.exists() else "would_create"
        changes = [
            SetupChange(
                path=str(settings_file),
                action=action,
                detail=(
                    f"Merge env block: {_ENV_BASE_URL}={anthropic_url}, "
                    f"{_ENV_AUTH_TOKEN}={api_key}, {_ENV_MODEL}={model_name}"
                ),
            )
        ]
        if not detected:
            notes.append("claude-code binary not detected; settings can still be generated for later use.")
        return SetupPlan(
            client_id=self.id,
            detected=detected,
            settings_paths=[str(settings_file)],
            changes=changes,
            notes=notes,
        )

    def apply(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
        force: bool = False,
        backup_root: Path | None = None,
    ) -> ApplyResult:
        settings_file = self._settings_file()
        desired_env = {
            _ENV_BASE_URL: _anthropic_base_url(base_url),
            _ENV_AUTH_TOKEN: api_key,
            _ENV_MODEL: model_name,
        }

        existing_data: dict = {}
        parse_warning = ""
        if settings_file.is_file():
            try:
                loaded = json.loads(settings_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing_data = loaded
                else:
                    parse_warning = "Existing settings.json was not an object; replaced (backup kept)."
            except (OSError, json.JSONDecodeError):
                parse_warning = "Existing settings.json was unreadable; replaced (backup kept)."

        current_env = existing_data.get("env")
        if not isinstance(current_env, dict):
            current_env = {}
        already = all(current_env.get(key) == value for key, value in desired_env.items())
        if already and not force:
            return ApplyResult(
                changed=False,
                message="claude-code already configured for daari. Use --force to re-apply.",
            )

        backup = (
            create_backup(self.id, [settings_file], root=backup_root)
            if settings_file.is_file()
            else None
        )

        merged = dict(existing_data)
        merged["env"] = {**current_env, **desired_env}
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

        message = "claude-code settings.json updated — launch `claude` to route through daari."
        if parse_warning:
            message = f"{message} ({parse_warning})"
        return ApplyResult(
            changed=True,
            backup_dir=backup.backup_dir if backup else None,
            files_changed=[str(settings_file)],
            message=message,
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        result = restore_latest_backup(self.id, root=backup_root)
        return UndoResult(backup_dir=result.backup_dir, files_restored=result.files_restored)

    @staticmethod
    def _settings_file() -> Path:
        return Path.home() / ".claude" / "settings.json"
