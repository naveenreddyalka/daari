"""Tell operators the native Gemini API is not served by daari (#1725).

Gemini CLI sends native requests when ``GOOGLE_GEMINI_BASE_URL`` is set.
This recipe never writes ``settings.json`` and never tells the operator to
point that variable at the daemon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupPlan


NOTICE = (
    "The native Gemini API is not a daari surface. "
    "Use an OpenAI-compatible client such as codex "
    "(`daari configure codex`) or opencode (`daari configure opencode`)."
)


@dataclass
class ApplyResult:
    changed: bool
    backup_dir: Path | None = None
    files_changed: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class UndoResult:
    backup_dir: Path | None = None
    files_restored: list[str] = field(default_factory=list)


class GeminiCliSetupRecipe:
    id = "gemini-cli"

    def detect(self) -> bool:
        return True

    def settings_paths(self) -> list[str]:
        return []

    def dry_run(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        model_name: str = "daari",
    ) -> SetupPlan:
        del base_url, api_key, model_name
        return SetupPlan(
            client_id=self.id,
            detected=True,
            settings_paths=[],
            changes=[],
            notes=[
                "Dry-run only — no files will be modified.",
                NOTICE,
                "No config files are written.",
            ],
        )

    def apply(
        self,
        *,
        base_url: str = "",
        api_key: str = "",
        model_name: str = "daari",
        force: bool = False,
        backup_root: Path | None = None,
    ) -> ApplyResult:
        del base_url, api_key, model_name, force, backup_root
        return ApplyResult(changed=False, message=NOTICE)

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        del backup_root
        raise FileNotFoundError("Gemini CLI config is not managed by daari; nothing to undo.")
