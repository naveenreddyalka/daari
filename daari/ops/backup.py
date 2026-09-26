"""Full-state backup / restore for durable daari stores (#1131)."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from daari import __version__

# Bump when archive layout or per-store expectations change incompatibly.
ARCHIVE_SCHEMA_VERSION = 1

# Logical store schema markers recorded in the manifest (additive migrate ids).
STORE_SCHEMA_VERSIONS: dict[str, int] = {
    "virtual-keys": 1,
    "audit": 1,
    "ledger": 1,
    "spend": 1,
    "responses": 1,
    "idempotency": 1,
    "batches": 1,
    "files": 1,
    "request-log": 1,
    "traces": 1,
}


@dataclass
class StoreEntry:
    name: str
    backend: str  # sqlite | jsonl | directory | postgres
    schema_version: int
    archive_path: str | None = None  # relative path inside the tarball
    source_path: str | None = None
    pg_dump: str | None = None
    present: bool = False


@dataclass
class BackupManifest:
    daari_version: str
    archive_schema_version: int
    created_at: str
    stores: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "daari_version": self.daari_version,
            "archive_schema_version": self.archive_schema_version,
            "created_at": self.created_at,
            "stores": list(self.stores),
        }


class BackupError(ValueError):
    """Operator-facing backup/restore failure."""


def _obs_backend(settings: Any) -> str:
    return getattr(settings.observability, "backend", "sqlite") or "sqlite"


def _pg_url(settings: Any) -> str:
    return (getattr(settings.observability, "postgres_url", "") or "").strip()


def catalog_stores(settings: Any, *, request_log_path: Path | None = None) -> list[StoreEntry]:
    """Describe every durable store and whether it lives in sqlite or postgres."""
    from daari.gateway import request_log as rl

    entries: list[StoreEntry] = []
    obs = _obs_backend(settings)
    pg = _pg_url(settings)

    def sqlite_entry(name: str, path: Path) -> StoreEntry:
        return StoreEntry(
            name=name,
            backend="sqlite",
            schema_version=STORE_SCHEMA_VERSIONS.get(name, 1),
            archive_path=f"stores/{name.replace('/', '-')}",
            source_path=str(path),
            present=path.is_file(),
        )

    vk_backend = getattr(settings.server.virtual_keys, "backend", "sqlite") or "sqlite"
    vk_path = Path(settings.server.virtual_keys.path).expanduser()
    if vk_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="virtual-keys",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["virtual-keys"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=virtual_keys --table=teams --table=team_members',
            )
        )
    else:
        entries.append(sqlite_entry("virtual-keys", vk_path))

    audit_backend = getattr(settings.enterprise, "audit_backend", "sqlite") or "sqlite"
    audit_path = Path(settings.enterprise.audit_path).expanduser()
    if audit_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="audit",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["audit"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=audit',
            )
        )
    else:
        entries.append(sqlite_entry("audit", audit_path))

    if obs == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="ledger",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["ledger"],
                pg_dump=(
                    f'pg_dump --dbname="{pg}" --table=usage --table=client_usage '
                    f"--table=user_usage --table=budget_window_state"
                ),
            )
        )
        entries.append(
            StoreEntry(
                name="spend",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["spend"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=spend_requests',
            )
        )
        entries.append(
            StoreEntry(
                name="traces",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["traces"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=traces',
            )
        )
    else:
        entries.append(sqlite_entry("ledger", Path(settings.usage.path).expanduser()))
        spend_path = Path(settings.usage.spend.path).expanduser()
        entries.append(sqlite_entry("spend", spend_path))
        entries.append(sqlite_entry("traces", Path(settings.trace.path).expanduser()))

    responses_backend = getattr(settings.responses, "backend", "sqlite") or "sqlite"
    responses_path = Path(settings.trace.path).expanduser().parent / "responses.sqlite3"
    if responses_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="responses",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["responses"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=daari_responses',
            )
        )
    else:
        entries.append(sqlite_entry("responses", responses_path))

    idem_backend = getattr(settings.idempotency, "backend", "sqlite") or "sqlite"
    idem_path = Path(settings.trace.path).expanduser().parent / "idempotency.sqlite3"
    if idem_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="idempotency",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["idempotency"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=daari_idempotency',
            )
        )
    else:
        entries.append(sqlite_entry("idempotency", idem_path))

    batches_path = Path(settings.batches.path).expanduser()
    entries.append(sqlite_entry("batches", batches_path))

    files_path = Path(settings.files.path).expanduser()
    entries.append(
        StoreEntry(
            name="files",
            backend="directory",
            schema_version=STORE_SCHEMA_VERSIONS["files"],
            archive_path="stores/files",
            source_path=str(files_path),
            present=files_path.exists(),
        )
    )

    log_path = Path(request_log_path or rl.LOG_PATH).expanduser()
    entries.append(
        StoreEntry(
            name="request-log",
            backend="jsonl",
            schema_version=STORE_SCHEMA_VERSIONS["request-log"],
            archive_path="stores/request-log",
            source_path=str(log_path),
            present=log_path.is_file(),
        )
    )
    return entries


def create_backup(settings: Any, archive: Path) -> BackupManifest:
    """Write ``archive`` (.tar.gz) with manifest + durable sqlite/JSONL/dir stores."""
    archive = Path(archive).expanduser()
    if archive.suffixes[-2:] != [".tar", ".gz"] and not str(archive).endswith(".tar.gz"):
        raise BackupError("archive path must end with .tar.gz")
    archive.parent.mkdir(parents=True, exist_ok=True)

    entries = catalog_stores(settings)
    manifest = BackupManifest(
        daari_version=__version__,
        archive_schema_version=ARCHIVE_SCHEMA_VERSION,
        created_at=datetime.now(UTC).isoformat(),
    )

    with tempfile.TemporaryDirectory(prefix="daari-backup-") as tmp:
        root = Path(tmp)
        stores_dir = root / "stores"
        stores_dir.mkdir()
        for entry in entries:
            row = {
                "name": entry.name,
                "backend": entry.backend,
                "schema_version": entry.schema_version,
                "source_path": entry.source_path,
                "archive_path": entry.archive_path,
                "present": entry.present,
            }
            if entry.backend == "postgres":
                row["pg_dump"] = entry.pg_dump
                row["external"] = True
                manifest.stores.append(row)
                continue
            src = Path(entry.source_path) if entry.source_path else None
            if src is None or not entry.present:
                row["present"] = False
                manifest.stores.append(row)
                continue
            dest = root / (entry.archive_path or f"stores/{entry.name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if entry.backend == "directory":
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            row["present"] = True
            manifest.stores.append(row)

        (root / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(root / "manifest.json", arcname="manifest.json")
            for entry in entries:
                if entry.backend == "postgres" or not entry.present or not entry.archive_path:
                    continue
                path = root / entry.archive_path
                if path.exists():
                    tar.add(path, arcname=entry.archive_path)
    return manifest


def _read_manifest(archive: Path) -> BackupManifest:
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.getmember("manifest.json")
        raw = tar.extractfile(member)
        if raw is None:
            raise BackupError("archive missing manifest.json")
        data = json.loads(raw.read().decode("utf-8"))
    return BackupManifest(
        daari_version=str(data.get("daari_version") or ""),
        archive_schema_version=int(data.get("archive_schema_version") or 0),
        created_at=str(data.get("created_at") or ""),
        stores=list(data.get("stores") or []),
    )


def restore_backup(
    settings: Any,
    archive: Path,
    *,
    force: bool = False,
) -> BackupManifest:
    """Restore stores from ``archive`` onto paths from ``settings``."""
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise BackupError(f"archive not found: {archive}")
    manifest = _read_manifest(archive)
    if manifest.archive_schema_version > ARCHIVE_SCHEMA_VERSION:
        raise BackupError(
            f"archive schema version {manifest.archive_schema_version} is newer than "
            f"this binary ({ARCHIVE_SCHEMA_VERSION}); upgrade daari before restoring"
        )
    live = {e.name: e for e in catalog_stores(settings)}

    with tempfile.TemporaryDirectory(prefix="daari-restore-") as tmp:
        root = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            try:
                tar.extractall(root, filter="data")
            except TypeError:
                tar.extractall(root)
        for row in manifest.stores:
            name = str(row.get("name") or "")
            if row.get("backend") == "postgres" or row.get("external"):
                continue
            if not row.get("present"):
                continue
            rel = row.get("archive_path")
            if not rel:
                continue
            src = root / str(rel)
            if not src.exists():
                continue
            target_entry = live.get(name)
            if target_entry is None or not target_entry.source_path:
                continue
            dest = Path(target_entry.source_path)
            if dest.exists() and not force:
                raise BackupError(
                    f"refusing to overwrite existing {name} at {dest} (pass --force)"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if row.get("backend") == "directory":
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
    return manifest


def recent_backup_manifests(*, root: Path | None = None, max_age_days: int = 7) -> list[Path]:
    """Find recent ``*.tar.gz`` archives under ~/.daari/backups (best-effort)."""
    base = (root or Path.home() / ".daari" / "backups").expanduser()
    if not base.is_dir():
        return []
    cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
    found: list[Path] = []
    for path in base.rglob("*.tar.gz"):
        try:
            if path.stat().st_mtime >= cutoff:
                found.append(path)
        except OSError:
            continue
    return sorted(found)
