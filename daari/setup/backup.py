from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class BackupManifest:
    tool: str
    timestamp: str
    files: list[dict[str, str]] = field(default_factory=list)


@dataclass
class BackupResult:
    backup_dir: Path
    manifest: BackupManifest
    files_backed_up: list[str]


@dataclass
class RestoreResult:
    backup_dir: Path
    files_restored: list[str]


def backups_root(root: Path | None = None) -> Path:
    return (root or Path.home() / ".daari" / "backups").expanduser()


def tool_backups_dir(tool: str, root: Path | None = None) -> Path:
    return backups_root(root) / tool


def _timestamp_dir_name() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _unique_backup_dir(tool: str, root: Path | None = None) -> Path:
    base = tool_backups_dir(tool, root)
    for _ in range(100):
        candidate = base / _timestamp_dir_name()
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate backup directory for {tool}")


def create_backup(
    tool: str,
    files: list[Path],
    *,
    root: Path | None = None,
    keep: int = 5,
) -> BackupResult:
    """Copy files into ~/.daari/backups/<tool>/<timestamp>/ and write manifest.json."""
    existing = [path for path in files if path.is_file()]
    if not existing:
        raise FileNotFoundError(f"No files to back up for {tool}")

    backup_dir = _unique_backup_dir(tool, root)
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest = BackupManifest(tool=tool, timestamp=backup_dir.name)
    backed_up: list[str] = []

    for index, source in enumerate(existing):
        backup_name = f"{index:02d}_{source.name}"
        dest = backup_dir / backup_name
        shutil.copy2(source, dest)
        manifest.files.append({"original": str(source), "backup": backup_name})
        backed_up.append(str(source))

    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.__dict__, indent=2) + "\n", encoding="utf-8")

    prune_old_backups(tool, root=root, keep=keep)
    return BackupResult(backup_dir=backup_dir, manifest=manifest, files_backed_up=backed_up)


def list_backups(tool: str, *, root: Path | None = None) -> list[Path]:
    base = tool_backups_dir(tool, root)
    if not base.is_dir():
        return []
    return sorted(
        [path for path in base.iterdir() if path.is_dir() and (path / "manifest.json").is_file()],
        key=lambda path: path.name,
        reverse=True,
    )


def latest_backup(tool: str, *, root: Path | None = None) -> Path | None:
    backups = list_backups(tool, root=root)
    return backups[0] if backups else None


def restore_latest_backup(tool: str, *, root: Path | None = None) -> RestoreResult:
    backup_dir = latest_backup(tool, root=root)
    if backup_dir is None:
        raise FileNotFoundError(f"No backups found for {tool}")

    manifest_path = backup_dir / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = BackupManifest(**data)

    restored: list[str] = []
    for entry in manifest.files:
        original = Path(entry["original"])
        backup_file = backup_dir / entry["backup"]
        if not backup_file.is_file():
            raise FileNotFoundError(f"Backup file missing: {backup_file}")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, original)
        restored.append(str(original))

    return RestoreResult(backup_dir=backup_dir, files_restored=restored)


def prune_old_backups(tool: str, *, root: Path | None = None, keep: int = 5) -> None:
    backups = list_backups(tool, root=root)
    for old in backups[keep:]:
        shutil.rmtree(old)
