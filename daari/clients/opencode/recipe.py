"""Print OpenCode steps for daari's OpenAI-compatible /v1 surface.

OpenCode config files are left untouched, matching Codex: operators paste a
provider snippet into their own opencode.json / opencode.jsonc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupPlan


DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
CLIENT_ID_HEADER = "opencode"
PACKAGE = "@opencode/ai/providers/openai-compatible"
ENV_KEY = "{env:DAARI_API_KEY}"


def openai_base(base_url: str) -> str:
    """OpenAI-compatible base URL, always ending in ``/v1``."""
    root = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if root.endswith("/v1"):
        return root or DEFAULT_BASE_URL
    return f"{root}/v1"


def provider_snippet(base_url: str) -> str:
    openai = openai_base(base_url)
    return (
        "{\n"
        '  "$schema": "https://opencode.ai/config.json",\n'
        '  "providers": {\n'
        '    "daari": {\n'
        f'      "package": "{PACKAGE}",\n'
        '      "settings": {\n'
        f'        "baseURL": "{openai}",\n'
        f'        "apiKey": "{ENV_KEY}"\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}"
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


class OpenCodeSetupRecipe:
    id = "opencode"

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
        openai = openai_base(base_url)
        return SetupPlan(
            client_id=self.id,
            detected=True,
            settings_paths=[],
            changes=[],
            notes=[
                "Dry-run only — no files will be modified.",
                f"OpenAI-compatible base URL: {openai}",
                "OpenCode v2 provider snippet (do not commit a live key):",
                provider_snippet(openai),
                (
                    "Older OpenCode configs use provider.daari.options.baseURL "
                    f"instead of providers.daari.settings.baseURL ({openai})."
                ),
                f"Pick model {model_name}.",
                f"Optional header: X-Daari-Client-Id: {CLIENT_ID_HEADER}",
                (f'Verify: curl -sS -H "Authorization: Bearer {api_key}" {openai}/models'),
                "OpenCode config files are not modified.",
                "Manual fallback: docs/developer/guides/clients/opencode.md",
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
        openai = openai_base(base_url)
        return ApplyResult(
            changed=False,
            message=(
                f"OpenCode: set providers.daari.settings.baseURL to {openai} "
                f"(package {PACKAGE}; apiKey {ENV_KEY}). "
                "Older configs use provider.daari.options.baseURL. "
                f"Model {model_name}. Optional header "
                f"X-Daari-Client-Id: {CLIENT_ID_HEADER}. "
                "OpenCode config files were not modified. "
                f"{provider_snippet(openai)} "
                f'Verify: curl -sS -H "Authorization: Bearer {api_key}" {openai}/models'
            ),
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        del backup_root
        raise FileNotFoundError("OpenCode config files are not managed by daari; nothing to undo.")
