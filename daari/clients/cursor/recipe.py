from __future__ import annotations

import json
import platform
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from daari.clients.base import SetupChange, SetupPlan
from daari.setup.backup import create_backup, restore_latest_backup
from daari.setup.jsonc import dump_jsonc, load_jsonc

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"
DAARI_MARKER_KEY = "daari.setup.cursor"
CURSOR_STORAGE_KEY = (
    "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl.persistentStorage.applicationUser"
)


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


class CursorSetupRecipe:
    id = "cursor"

    def detect(self) -> bool:
        if shutil.which("cursor"):
            return True
        for path in self._candidate_paths():
            if path.parent.exists():
                return True
        return False

    def settings_paths(self) -> list[str]:
        return [str(p) for p in self._config_paths() if p.parent.exists()]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        paths = self._config_paths()
        existing = [p for p in paths if p.is_file()]
        detected = self.detect()

        changes: list[SetupChange] = []
        notes: list[str] = [
            "Dry-run only — no files will be modified.",
            "Manual fallback: docs/setup/cursor.md",
        ]

        if not detected:
            notes.append("Cursor not detected on this machine.")
        else:
            for path in existing:
                action = (
                    "already_configured"
                    if self._is_configured_in_file(path, base_url, model_name)
                    else "would_patch"
                )
                changes.append(
                    SetupChange(
                        path=str(path),
                        action=action,
                        detail=(
                            f"Ensure custom OpenAI-compatible model '{model_name}' "
                            f"with base URL {base_url} and API key {api_key}"
                        ),
                    )
                )
            missing = [p for p in paths if not p.is_file()]
            if missing:
                notes.append(
                    "Some Cursor config files are not present yet — "
                    "open Cursor once, then re-run."
                )

        return SetupPlan(
            client_id=self.id,
            detected=detected,
            settings_paths=[str(p) for p in paths],
            changes=changes,
            notes=notes,
        )

    def is_configured(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> bool:
        for path in self._config_paths():
            if path.is_file() and self._is_configured_in_file(path, base_url, model_name):
                return True
        return False

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
            return ApplyResult(changed=False, message="Cursor not detected on this machine.")

        paths = [p for p in self._config_paths() if p.is_file()]
        if not paths:
            return ApplyResult(
                changed=False,
                message="Cursor settings not found — open Cursor once, then re-run.",
            )

        if self.is_configured(base_url=base_url, model_name=model_name) and not force:
            return ApplyResult(
                changed=False,
                message=(
                    "Cursor already configured for daari. "
                    "Use --force to re-apply."
                ),
            )

        backup = create_backup(self.id, paths, root=backup_root)
        changed_files: list[str] = []

        for path in paths:
            if path.suffix == ".vscdb":
                self._patch_vscdb(path, base_url=base_url, api_key=api_key, model_name=model_name)
            else:
                self._patch_settings_json(
                    path,
                    base_url=base_url,
                    api_key=api_key,
                    model_name=model_name,
                )
            changed_files.append(str(path))

        return ApplyResult(
            changed=True,
            backup_dir=backup.backup_dir,
            files_changed=changed_files,
            message="Cursor configured for daari.",
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        result = restore_latest_backup(self.id, root=backup_root)
        return UndoResult(backup_dir=result.backup_dir, files_restored=result.files_restored)

    def _config_paths(self) -> list[Path]:
        paths = self._candidate_paths()
        storage = self._storage_db_path()
        if storage is not None:
            paths.append(storage)
        return paths

    def _candidate_paths(self) -> list[Path]:
        system = platform.system()
        home = Path.home()
        if system == "Darwin":
            base = home / "Library" / "Application Support" / "Cursor" / "User"
        elif system == "Windows":
            appdata = home
            if "APPDATA" in __import__("os").environ:
                appdata = Path(__import__("os").environ["APPDATA"])
            base = appdata / "Cursor" / "User"
        else:
            base = home / ".config" / "Cursor" / "User"
        return [base / "settings.json"]

    def _storage_db_path(self) -> Path | None:
        system = platform.system()
        home = Path.home()
        if system == "Darwin":
            base = home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage"
        elif system == "Windows":
            appdata = home
            if "APPDATA" in __import__("os").environ:
                appdata = Path(__import__("os").environ["APPDATA"])
            base = appdata / "Cursor" / "User" / "globalStorage"
        else:
            base = home / ".config" / "Cursor" / "User" / "globalStorage"
        path = base / "state.vscdb"
        return path if path.parent.exists() else None

    def _is_configured_in_file(
        self,
        path: Path,
        base_url: str,
        model_name: str,
    ) -> bool:
        if path.suffix == ".vscdb":
            return self._read_vscdb_configured(path, base_url, model_name)
        return self._read_settings_configured(path, base_url, model_name)

    def _read_settings_configured(self, path: Path, base_url: str, model_name: str) -> bool:
        try:
            data = load_jsonc(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        marker = data.get(DAARI_MARKER_KEY)
        if isinstance(marker, dict):
            return marker.get("baseUrl") == base_url and marker.get("model") == model_name
        for key in ("openai.baseUrl", "openai.baseURL"):
            if data.get(key) == base_url:
                return True
        return False

    def _read_vscdb_configured(self, path: Path, base_url: str, model_name: str) -> bool:
        try:
            conn = sqlite3.connect(path)
            row = conn.execute(
                "SELECT value FROM ItemTable WHERE key = ?",
                (CURSOR_STORAGE_KEY,),
            ).fetchone()
            conn.close()
        except sqlite3.Error:
            return False
        if row is None:
            return False
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return False
        if data.get("openAIBaseUrl") != base_url:
            return False
        models = data.get("availableAPIKeyModels") or []
        names = {
            item if isinstance(item, str) else item.get("name")
            for item in models
            if isinstance(item, (str, dict))
        }
        return model_name in names or data.get("useOpenAIKey") is True

    def _patch_settings_json(
        self,
        path: Path,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
    ) -> None:
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

    def _patch_vscdb(
        self,
        path: Path,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
    ) -> None:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            (CURSOR_STORAGE_KEY,),
        ).fetchone()
        if row is None:
            conn.close()
            return

        data: dict[str, Any] = json.loads(row[0])
        data["openAIBaseUrl"] = base_url
        data["useOpenAIKey"] = True

        models = list(data.get("availableAPIKeyModels") or [])
        names = {
            item if isinstance(item, str) else item.get("name")
            for item in models
            if isinstance(item, (str, dict))
        }
        if model_name not in names:
            models.append({"name": model_name, "enabled": True})
        data["availableAPIKeyModels"] = models

        # Cursor stores the API key in secure storage; record intent in aiSettings marker.
        ai_settings = dict(data.get("aiSettings") or {})
        ai_settings["daariOpenAIApiKey"] = api_key
        data["aiSettings"] = ai_settings

        conn.execute(
            "UPDATE ItemTable SET value = ? WHERE key = ?",
            (json.dumps(data), CURSOR_STORAGE_KEY),
        )
        conn.commit()
        conn.close()
