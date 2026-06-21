from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupChange, SetupPlan
from daari.setup.backup import create_backup, restore_latest_backup
from daari.setup.jsonc import dump_jsonc, load_jsonc

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"
DAARI_MARKER_KEY = "daari.setup.vscode"


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


class VSCodeSetupRecipe:
    id = "vscode"

    def detect(self) -> bool:
        if shutil.which("code"):
            return True
        return any(path.parent.exists() for path in self._candidate_paths())

    def settings_paths(self) -> list[str]:
        return [str(path) for path in self._candidate_paths()]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        paths = self._candidate_paths()
        detected = self.detect()
        notes = [
            "Dry-run only — no files will be modified.",
            "Manual fallback: docs/setup/vscode.md",
        ]
        changes: list[SetupChange] = []

        if not detected:
            notes.append("VS Code not detected on this machine.")
        else:
            for path in paths:
                action = (
                    "already_configured"
                    if self._is_configured(path, base_url=base_url, model_name=model_name)
                    else "would_patch"
                )
                changes.append(
                    SetupChange(
                        path=str(path),
                        action=action,
                        detail=(
                            f"Ensure OpenAI-compatible marker '{model_name}' "
                            f"with base URL {base_url} and API key {api_key}"
                        ),
                    )
                )
            if not any(path.is_file() for path in paths):
                notes.append("VS Code settings file not present yet — open VS Code once, then re-run.")

        return SetupPlan(
            client_id=self.id,
            detected=detected,
            settings_paths=[str(path) for path in paths],
            changes=changes,
            notes=notes,
        )

    def is_configured(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> bool:
        return any(self._is_configured(path, base_url=base_url, model_name=model_name) for path in self._candidate_paths())

    def apply(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
        force: bool = False,
        backup_root: Path | None = None,
    ) -> ApplyResult:
        if not self.detect():
            return ApplyResult(changed=False, message="VS Code not detected on this machine.")

        path = self._candidate_paths()[0]
        existing = [path] if path.is_file() else []
        if self._is_configured(path, base_url=base_url, model_name=model_name) and not force:
            return ApplyResult(changed=False, message="VS Code already configured for daari. Use --force to re-apply.")

        backup = create_backup(self.id, existing, root=backup_root) if existing else None
        data = load_jsonc(path) if path.is_file() else {}
        data["openai.baseUrl"] = base_url
        data["openai.apiKey"] = api_key
        data[DAARI_MARKER_KEY] = {
            "version": 1,
            "baseUrl": base_url,
            "apiKey": api_key,
            "model": model_name,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_jsonc(data), encoding="utf-8")
        return ApplyResult(
            changed=True,
            backup_dir=backup.backup_dir if backup else None,
            files_changed=[str(path)],
            message="VS Code configured for daari.",
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        result = restore_latest_backup(self.id, root=backup_root)
        return UndoResult(backup_dir=result.backup_dir, files_restored=result.files_restored)

    def _candidate_paths(self) -> list[Path]:
        home = Path.home()
        system = platform.system()
        if system == "Darwin":
            return [home / "Library" / "Application Support" / "Code" / "User" / "settings.json"]
        if system == "Windows":
            appdata = Path(os.environ.get("APPDATA", str(home)))
            return [appdata / "Code" / "User" / "settings.json"]
        return [home / ".config" / "Code" / "User" / "settings.json"]

    def _is_configured(self, path: Path, *, base_url: str, model_name: str) -> bool:
        if not path.is_file():
            return False
        try:
            data = load_jsonc(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        marker = data.get(DAARI_MARKER_KEY)
        if isinstance(marker, dict):
            return marker.get("baseUrl") == base_url and marker.get("model") == model_name
        return data.get("openai.baseUrl") == base_url
