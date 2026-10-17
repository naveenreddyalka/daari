"""Print Codex CLI steps for daari's OpenAI and Ollama surfaces.

Codex config files are left untouched, matching ChatGPT Desktop: operators
either point the OpenAI-compatible base URL at ``/v1`` or, for
``ollama launch codex``, set the Ollama host to daari's root (no ``/v1``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupPlan


DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
CLIENT_ID_HEADER = "codex"


def ollama_host(base_url: str) -> str:
    """Daari root for ``ollama launch codex``. Must not include ``/v1``."""
    root = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root or "http://127.0.0.1:11435"


def openai_base(base_url: str) -> str:
    """OpenAI-compatible base URL, always ending in ``/v1``."""
    root = ollama_host(base_url)
    return f"{root}/v1"


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


class CodexSetupRecipe:
    id = "codex"

    def detect(self) -> bool:
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
        openai = openai_base(base_url)
        return SetupPlan(
            client_id=self.id,
            detected=True,
            settings_paths=[],
            changes=[],
            notes=[
                "Dry-run only — no files will be modified.",
                f"OpenAI-compatible base URL: {openai}",
                (
                    "ollama launch codex users should set the Ollama host to "
                    f"{host} (no /v1)."
                ),
                f"Pick model {model_name}.",
                f"Optional header: X-Daari-Client-Id: {CLIENT_ID_HEADER}",
                (
                    "Verify: curl -sS -H "
                    f'"Authorization: Bearer {api_key}" {openai}/models'
                ),
                "Codex config files are not modified.",
                "Manual fallback: docs/developer/guides/clients/codex.md",
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
        del force, backup_root
        host = ollama_host(base_url)
        openai = openai_base(base_url)
        return ApplyResult(
            changed=False,
            message=(
                f"Codex CLI: set the OpenAI-compatible base URL to {openai}, "
                f"or for ollama launch codex set the Ollama host to {host} "
                f"(no /v1). Model {model_name}. Optional header "
                f"X-Daari-Client-Id: {CLIENT_ID_HEADER}. "
                "Codex config files were not modified. "
                f'Verify: curl -sS -H "Authorization: Bearer {api_key}" {openai}/models'
            ),
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        del backup_root
        raise FileNotFoundError(
            "Codex config files are not managed by daari; nothing to undo."
        )
