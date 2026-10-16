"""Print the Ollama-host steps for ChatGPT Desktop (#1686).

ChatGPT Desktop app preferences are undocumented, so this recipe never writes
them. It only tells the operator to point the Ollama host at daari's root
(no ``/v1``) and to leave native Ollama on 11434.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupPlan


DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
CLIENT_ID_HEADER = "chatgpt-desktop"


def ollama_host(base_url: str) -> str:
    """Daari root for the Ollama facade. ChatGPT Desktop must not use ``/v1``."""
    root = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root or "http://127.0.0.1:11435"


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


class ChatGPTDesktopSetupRecipe:
    id = "chatgpt-desktop"

    def detect(self) -> bool:
        # Steps are valid without the desktop app installed.
        return True

    def settings_paths(self) -> list[str]:
        return []

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "daari-local",
        model_name: str = "daari",
    ) -> SetupPlan:
        host = ollama_host(base_url)
        return SetupPlan(
            client_id=self.id,
            detected=True,
            settings_paths=[],
            changes=[],
            notes=[
                "Dry-run only — no files will be modified.",
                f"In ChatGPT Desktop, set the Ollama host to {host} (no /v1).",
                "Leave native Ollama on port 11434 if you still use it directly.",
                f"Pick model {model_name}.",
                "Optional header when the client allows it: "
                f"X-Daari-Client-Id: {CLIENT_ID_HEADER}",
                "App preferences are not modified (undocumented).",
                "Manual fallback: docs/developer/guides/clients/chatgpt-desktop.md",
            ],
        )

    def apply(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "daari-local",
        model_name: str = "daari",
        force: bool = False,
        backup_root: Path | None = None,
    ) -> ApplyResult:
        del api_key, force, backup_root
        host = ollama_host(base_url)
        return ApplyResult(
            changed=False,
            message=(
                f"ChatGPT Desktop: set the Ollama host to {host} (no /v1), "
                f"model {model_name}, and optional header "
                f"X-Daari-Client-Id: {CLIENT_ID_HEADER}. "
                "Leave native Ollama on 11434. App preferences were not modified."
            ),
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        del backup_root
        raise FileNotFoundError(
            "ChatGPT Desktop preferences are not managed by daari; nothing to undo."
        )
