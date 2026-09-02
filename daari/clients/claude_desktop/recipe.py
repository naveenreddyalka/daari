from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from daari.clients.base import SetupChange, SetupPlan
from daari.setup.backup import create_backup, restore_latest_backup

DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_API_KEY = "daari-local"
DEFAULT_MODEL_NAME = "daari"

# Claude Desktop's third-party mode keeps saved configurations in a per-user
# "configLibrary" directory (one JSON file per configuration, flat keys named
# exactly as in the managed-configuration reference). The recipe drops a
# daari configuration there; the app's Developer → Configure Third-Party
# Inference… window imports/activates it.
CONFIG_FILE_NAME = "daari.json"
_APP_DIR_3P = "Claude-3p"
_APP_DIR_STANDARD = "Claude"

_KEYS = (
    "inferenceProvider",
    "inferenceGatewayBaseUrl",
    "inferenceGatewayApiKey",
    "inferenceGatewayAuthScheme",
    "inferenceModels",
)


@dataclass
class ApplyResult:
    changed: bool
    backup_dir: Path | None = None
    files_changed: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class UndoResult:
    backup_dir: Path | None
    files_restored: list[str]


def _gateway_base_url(base_url: str) -> str:
    """Claude Desktop appends /v1/messages itself (Anthropic SDK semantics)."""
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return trimmed


def desired_config(*, base_url: str, api_key: str, model_name: str) -> dict:
    return {
        "inferenceProvider": "gateway",
        "inferenceGatewayBaseUrl": _gateway_base_url(base_url),
        "inferenceGatewayApiKey": api_key,
        # daari accepts Bearer too; x-api-key matches what Anthropic-shaped
        # clients send natively and never collides with a user's Bearer proxy.
        "inferenceGatewayAuthScheme": "x-api-key",
        "inferenceModels": [{"name": model_name, "labelOverride": f"{model_name} (local-first)"}],
    }


def _app_data_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA")
        return Path(local) if local else Path.home() / "AppData" / "Local"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else Path.home() / ".config"


def _app_bundle_present() -> bool:
    if sys.platform == "darwin":
        return any(
            (root / "Claude.app").exists()
            for root in (Path("/Applications"), Path.home() / "Applications")
        )
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA")
        return bool(local) and (Path(local) / "AnthropicClaude").exists()
    return False


class ClaudeDesktopSetupRecipe:
    id = "claude-desktop"

    def detect(self) -> bool:
        root = _app_data_root()
        return (
            (root / _APP_DIR_STANDARD).is_dir()
            or (root / _APP_DIR_3P).is_dir()
            or _app_bundle_present()
        )

    def settings_paths(self) -> list[str]:
        return [str(self._config_file())]

    def dry_run(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = DEFAULT_API_KEY,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> SetupPlan:
        config_file = self._config_file()
        detected = self.detect()
        desired = desired_config(base_url=base_url, api_key=api_key, model_name=model_name)
        notes = [
            "Dry-run only — no files will be modified.",
            "This recipe writes a Claude Desktop third-party configuration "
            f"({CONFIG_FILE_NAME}) into the app's configLibrary. Fully quit and reopen "
            "Claude Desktop; if it is not active, open Developer → Configure Third-Party "
            "Inference… → Import configuration and pick that file.",
            "Chat routes through daari's Anthropic gateway (/v1/messages): local tiers "
            "first, frontier only when needed, with cache/budgets/traces.",
        ]
        action = "would_patch" if config_file.exists() else "would_create"
        changes = [
            SetupChange(
                path=str(config_file),
                action=action,
                detail=(
                    "Write gateway config: inferenceProvider=gateway, "
                    f"inferenceGatewayBaseUrl={desired['inferenceGatewayBaseUrl']}, "
                    f"inferenceGatewayApiKey={api_key}, "
                    f"inferenceGatewayAuthScheme=x-api-key, inferenceModels=[{model_name}]"
                ),
            )
        ]
        if not detected:
            notes.append(
                "Claude Desktop not detected (no Claude.app / app data dir); apply will skip."
            )
        return SetupPlan(
            client_id=self.id,
            detected=detected,
            settings_paths=[str(config_file)],
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
        if not self.detect():
            return ApplyResult(
                changed=False,
                message=(
                    "Claude Desktop not detected — install it (https://claude.ai/download) "
                    "and re-run `daari setup claude-desktop`."
                ),
            )

        config_file = self._config_file()
        desired = desired_config(base_url=base_url, api_key=api_key, model_name=model_name)

        existing: dict | None = None
        parse_warning = ""
        if config_file.is_file():
            try:
                loaded = json.loads(config_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
                else:
                    parse_warning = f"Existing {CONFIG_FILE_NAME} was not an object; replaced (backup kept)."
            except (OSError, json.JSONDecodeError):
                parse_warning = f"Existing {CONFIG_FILE_NAME} was unreadable; replaced (backup kept)."

        if existing == desired and not force:
            return ApplyResult(
                changed=False,
                message="claude-desktop already configured for daari. Use --force to re-apply.",
            )

        backup = (
            create_backup(self.id, [config_file], root=backup_root)
            if config_file.is_file()
            else None
        )

        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(desired, indent=2) + "\n", encoding="utf-8")

        message = (
            "claude-desktop gateway config written — quit and reopen Claude Desktop "
            "(Developer → Configure Third-Party Inference… → Import configuration if it "
            "is not active)."
        )
        if parse_warning:
            message = f"{message} ({parse_warning})"
        return ApplyResult(
            changed=True,
            backup_dir=backup.backup_dir if backup else None,
            files_changed=[str(config_file)],
            message=message,
        )

    def undo(self, *, backup_root: Path | None = None) -> UndoResult:
        try:
            result = restore_latest_backup(self.id, root=backup_root)
        except FileNotFoundError:
            # The recipe created the file itself, so uninstall means removing
            # it — but only when it is still the daari-written configuration.
            return self._remove_daari_config()
        return UndoResult(backup_dir=result.backup_dir, files_restored=result.files_restored)

    def _remove_daari_config(self) -> UndoResult:
        config_file = self._config_file()
        if not config_file.is_file():
            raise FileNotFoundError(f"No backups and no {CONFIG_FILE_NAME} to remove for {self.id}")
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileNotFoundError(
                f"No backups for {self.id} and {CONFIG_FILE_NAME} is unreadable; remove it manually."
            ) from exc
        is_daari = (
            isinstance(data, dict)
            and data.get("inferenceProvider") == "gateway"
            and set(data) <= set(_KEYS)
            and any(
                entry == DEFAULT_MODEL_NAME
                or (isinstance(entry, dict) and entry.get("name") == DEFAULT_MODEL_NAME)
                for entry in data.get("inferenceModels", [])
            )
        )
        if not is_daari:
            raise FileNotFoundError(
                f"No backups for {self.id} and {config_file} was not written by daari; left untouched."
            )
        config_file.unlink()
        return UndoResult(backup_dir=None, files_restored=[str(config_file)])

    @staticmethod
    def _config_file() -> Path:
        return _app_data_root() / _APP_DIR_3P / "configLibrary" / CONFIG_FILE_NAME
