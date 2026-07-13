from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupChange, SetupPlan
from daari.setup.backup import create_backup, restore_latest_backup

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"


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


class IntelliJSetupRecipe:
    id = "intellij"

    def detect(self) -> bool:
        return bool(self._installation_dirs())

    def settings_paths(self) -> list[str]:
        return [str(p) for p in self._settings_files()]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        installs = self._installation_dirs()
        settings_files = self._settings_files()
        notes = [
            "Dry-run only - no files will be modified.",
            "Manual fallback: docs/setup/intellij.md",
            f"One-click path: daari exposes an Ollama-compatible API. In IntelliJ open "
            f"Settings > Tools > AI Assistant > Models, enable Ollama, and set the URL to "
            f"{self._ollama_facade_url(base_url)} — the 'daari' model appears automatically.",
        ]
        changes: list[SetupChange] = []
        if not installs:
            notes.append("IntelliJ not detected on this machine.")
        else:
            for settings in settings_files:
                action = (
                    "already_configured"
                    if self._is_configured_file(settings, base_url, model_name)
                    else "would_patch"
                )
                changes.append(
                    SetupChange(
                        path=str(settings),
                        action=action,
                        detail=(
                            f"Write daari OpenAI-compatible helper config for model '{model_name}' "
                            f"at {base_url} with API key {api_key}"
                        ),
                    )
                )
            notes.append(
                "JetBrains AI Assistant requires selecting the provider in the IDE UI once; "
                "after that daari handles routing."
            )

        return SetupPlan(
            client_id=self.id,
            detected=bool(installs),
            settings_paths=[str(p) for p in settings_files],
            changes=changes,
            notes=notes,
        )

    def is_configured(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> bool:
        return any(self._is_configured_file(path, base_url, model_name) for path in self._settings_files())

    def apply(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
        force: bool = False,
        backup_root: Path | None = None,
    ) -> ApplyResult:
        settings_files = self._settings_files()
        if not settings_files:
            return ApplyResult(changed=False, message="IntelliJ not detected on this machine.")
        if self.is_configured(base_url=base_url, model_name=model_name) and not force:
            return ApplyResult(
                changed=False,
                message="IntelliJ already configured for daari. Use --force to re-apply.",
            )

        existing = [path for path in settings_files if path.is_file()]
        backup = create_backup(self.id, existing, root=backup_root) if existing else None
        changed_files: list[str] = []
        payload = {
            "provider": "openai-compatible",
            "base_url": base_url,
            "api_key": api_key,
            "model": model_name,
            "managed_by": "daari",
        }

        for path in settings_files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            changed_files.append(str(path))

        return ApplyResult(
            changed=True,
            backup_dir=backup.backup_dir if backup else None,
            files_changed=changed_files,
            message="IntelliJ helper config written for daari.",
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        result = restore_latest_backup(self.id, root=backup_root)
        return UndoResult(backup_dir=result.backup_dir, files_restored=result.files_restored)

    @staticmethod
    def _ollama_facade_url(base_url: str) -> str:
        """The Ollama facade lives at the server root (no /v1 suffix)."""
        trimmed = base_url.rstrip("/")
        if trimmed.endswith("/v1"):
            trimmed = trimmed[: -len("/v1")]
        return trimmed

    def _settings_files(self) -> list[Path]:
        return [install / "options" / "daari-openai-compat.json" for install in self._installation_dirs()]

    def _installation_dirs(self) -> list[Path]:
        roots = self._jetbrains_roots()
        matches: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if child.is_dir() and child.name.startswith(("IntelliJIdea", "IdeaIC")):
                    matches.append(child)
        return sorted(matches, key=lambda p: p.name)

    def _jetbrains_roots(self) -> list[Path]:
        home = Path.home()
        system = platform.system()
        if system == "Darwin":
            return [home / "Library" / "Application Support" / "JetBrains"]
        if system == "Windows":
            appdata = Path(os.environ.get("APPDATA", str(home)))
            return [appdata / "JetBrains"]
        return [home / ".config" / "JetBrains"]

    @staticmethod
    def _is_configured_file(path: Path, base_url: str, model_name: str) -> bool:
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            data.get("managed_by") == "daari"
            and data.get("base_url") == base_url
            and data.get("model") == model_name
        )
