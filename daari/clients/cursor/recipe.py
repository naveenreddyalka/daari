from __future__ import annotations

import platform
import shutil
from pathlib import Path

from daari.clients.base import SetupChange, SetupPlan

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"


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
        return [str(p) for p in self._candidate_paths() if p.parent.exists()]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        paths = self._candidate_paths()
        existing = [p for p in paths if p.parent.exists()]
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
                changes.append(
                    SetupChange(
                        path=str(path),
                        action="would_patch",
                        detail=(
                            f"Add custom OpenAI-compatible model '{model_name}' "
                            f"with base URL {base_url} and API key {api_key}"
                        ),
                    )
                )
            if not existing:
                notes.append(
                    "Cursor may be installed but settings directory not found yet — "
                    "open Cursor once, then re-run."
                )

        return SetupPlan(
            client_id=self.id,
            detected=detected,
            settings_paths=[str(p) for p in paths],
            changes=changes,
            notes=notes,
        )

    def _candidate_paths(self) -> list[Path]:
        system = platform.system()
        home = Path.home()
        if system == "Darwin":
            base = home / "Library" / "Application Support" / "Cursor" / "User"
        elif system == "Windows":
            appdata = Path.home()
            if "APPDATA" in __import__("os").environ:
                appdata = Path(__import__("os").environ["APPDATA"])
            base = appdata / "Cursor" / "User"
        else:
            base = home / ".config" / "Cursor" / "User"
        return [base / "settings.json"]
