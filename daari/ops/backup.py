"""Full-state backup / restore for durable daari stores (#1131, #1176)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from daari import __version__

EncryptMethod = Literal["openssl", "age"]
_ENCRYPT_SUFFIX: dict[str, str] = {"openssl": ".enc", "age": ".age"}
DEFAULT_PASSPHRASE_ENV = "DAARI_BACKUP_PASS"
DEFAULT_AGE_RECIPIENT_ENV = "DAARI_BACKUP_AGE_RECIPIENT"
DEFAULT_AGE_IDENTITY_ENV = "DAARI_BACKUP_AGE_IDENTITY"

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

    batches_backend = getattr(settings.batches, "backend", "sqlite") or "sqlite"
    batches_path = Path(settings.batches.path).expanduser()
    if batches_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="batches",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["batches"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=daari_batch_jobs',
            )
        )
    else:
        entries.append(sqlite_entry("batches", batches_path))

    files_backend = getattr(settings.files, "backend", "sqlite") or "sqlite"
    files_path = Path(settings.files.path).expanduser()
    if files_backend == "postgres" and pg:
        entries.append(
            StoreEntry(
                name="files",
                backend="postgres",
                schema_version=STORE_SCHEMA_VERSIONS["files"],
                pg_dump=f'pg_dump --dbname="{pg}" --table=daari_files',
            )
        )
    else:
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
    # Include every rotation slot so restore can write siblings onto a cold dest
    # even when the target host has no rotated files yet (#1171).
    backups = max(0, int(getattr(rl, "_backups", 0) or 0))
    existing = {p.name: p for p in rl._rotated_logs(log_path)}
    for index in range(1, backups + 1):
        rotated = log_path.with_name(f"{log_path.name}.{index}")
        if rotated.name in existing:
            rotated = existing[rotated.name]
        name = f"request-log.{index}"
        entries.append(
            StoreEntry(
                name=name,
                backend="jsonl",
                schema_version=STORE_SCHEMA_VERSIONS["request-log"],
                archive_path=f"stores/{name.replace('/', '-')}",
                source_path=str(rotated),
                present=rotated.is_file(),
            )
        )
    return entries


def detect_encrypt_method(path: Path) -> EncryptMethod | None:
    """Return openssl/age when ``path`` uses a known encrypted suffix."""
    name = path.name
    if name.endswith(".tar.gz.enc"):
        return "openssl"
    if name.endswith(".tar.gz.age"):
        return "age"
    return None


def encrypted_archive_path(archive: Path, method: EncryptMethod) -> Path:
    archive = Path(archive)
    plain = str(archive)
    if not plain.endswith(".tar.gz"):
        raise BackupError("archive path must end with .tar.gz before encryption")
    return Path(plain + _ENCRYPT_SUFFIX[method])


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise BackupError(f"{name} not found on PATH; install it to use --encrypt {name}")
    return path


def _passphrase_from_env(env_name: str) -> str:
    value = (os.environ.get(env_name) or "").strip()
    if not value:
        raise BackupError(
            f"encrypted backup requires passphrase in ${env_name} "
            f"(or pass --passphrase-env)"
        )
    return value


def encrypt_backup_archive(
    archive: Path,
    method: EncryptMethod,
    *,
    passphrase_env: str = DEFAULT_PASSPHRASE_ENV,
    age_recipient: str | None = None,
    remove_plaintext: bool = True,
) -> Path:
    """Encrypt a plaintext ``.tar.gz`` to ``.tar.gz.enc`` / ``.tar.gz.age`` (#1176)."""
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise BackupError(f"archive not found: {archive}")
    out = encrypted_archive_path(archive, method)
    if method == "openssl":
        binary = _require_binary("openssl")
        passphrase = _passphrase_from_env(passphrase_env)
        proc = subprocess.run(
            [
                binary,
                "enc",
                "-aes-256-cbc",
                "-salt",
                "-pbkdf2",
                "-in",
                str(archive),
                "-out",
                str(out),
                "-pass",
                f"env:{passphrase_env}",
            ],
            env={**os.environ, passphrase_env: passphrase},
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BackupError(f"openssl encrypt failed: {(proc.stderr or proc.stdout).strip()}")
    else:
        binary = _require_binary("age")
        recipient = (age_recipient or os.environ.get(DEFAULT_AGE_RECIPIENT_ENV) or "").strip()
        if not recipient:
            raise BackupError(
                f"age encrypt requires --age-recipient or ${DEFAULT_AGE_RECIPIENT_ENV}"
            )
        proc = subprocess.run(
            [binary, "-r", recipient, "-o", str(out), str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BackupError(f"age encrypt failed: {(proc.stderr or proc.stdout).strip()}")
    if remove_plaintext:
        try:
            archive.unlink()
        except OSError:
            pass
    return out


def decrypt_backup_archive(
    archive: Path,
    *,
    passphrase_env: str = DEFAULT_PASSPHRASE_ENV,
    age_identity: str | None = None,
    dest: Path | None = None,
) -> Path:
    """Decrypt an encrypted archive to a plaintext ``.tar.gz`` path (#1176)."""
    archive = Path(archive).expanduser()
    method = detect_encrypt_method(archive)
    if method is None:
        raise BackupError(f"not an encrypted daari backup archive: {archive}")
    if dest is None:
        # Strip .enc / .age → .tar.gz beside the encrypted file (or temp).
        plain_name = archive.name
        if plain_name.endswith(".enc"):
            plain_name = plain_name[: -len(".enc")]
        elif plain_name.endswith(".age"):
            plain_name = plain_name[: -len(".age")]
        dest = archive.with_name(plain_name)
    dest = Path(dest)
    if method == "openssl":
        binary = _require_binary("openssl")
        passphrase = _passphrase_from_env(passphrase_env)
        proc = subprocess.run(
            [
                binary,
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-in",
                str(archive),
                "-out",
                str(dest),
                "-pass",
                f"env:{passphrase_env}",
            ],
            env={**os.environ, passphrase_env: passphrase},
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BackupError(f"openssl decrypt failed: {(proc.stderr or proc.stdout).strip()}")
    else:
        binary = _require_binary("age")
        identity = (age_identity or os.environ.get(DEFAULT_AGE_IDENTITY_ENV) or "").strip()
        if not identity:
            raise BackupError(
                f"age decrypt requires --age-identity or ${DEFAULT_AGE_IDENTITY_ENV}"
            )
        id_path = Path(identity).expanduser()
        if not id_path.is_file():
            raise BackupError(f"age identity file not found: {id_path}")
        proc = subprocess.run(
            [binary, "-d", "-i", str(id_path), "-o", str(dest), str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise BackupError(f"age decrypt failed: {(proc.stderr or proc.stdout).strip()}")
    return dest


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


def server_appears_running(settings: Any) -> bool:
    """Best-effort probe: local /health returns 200 (#1171)."""
    try:
        import httpx

        host = getattr(settings.server, "host", "127.0.0.1")
        port = int(getattr(settings.server, "port", 11435) or 11435)
        response = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
        return response.status_code == 200
    except Exception:
        return False


def restore_backup(
    settings: Any,
    archive: Path,
    *,
    force: bool = False,
    allow_running_server: bool = False,
    passphrase_env: str = DEFAULT_PASSPHRASE_ENV,
    age_identity: str | None = None,
) -> BackupManifest:
    """Restore stores from ``archive`` onto paths from ``settings``."""
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise BackupError(f"archive not found: {archive}")
    if not allow_running_server and server_appears_running(settings):
        raise BackupError(
            "daari server appears to be running (GET /health succeeded); "
            "stop it before restore, or pass --i-know-server-is-stopped "
            "if you are certain no process holds the target stores"
        )
    method = detect_encrypt_method(archive)
    if method is not None:
        with tempfile.TemporaryDirectory(prefix="daari-decrypt-") as tmp:
            plain = Path(tmp) / "archive.tar.gz"
            decrypt_backup_archive(
                archive,
                passphrase_env=passphrase_env,
                age_identity=age_identity,
                dest=plain,
            )
            return restore_backup(
                settings,
                plain,
                force=force,
                allow_running_server=True,  # already checked above
            )
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
    """Find recent ``*.tar.gz`` / encrypted archives under ~/.daari/backups."""
    base = (root or Path.home() / ".daari" / "backups").expanduser()
    if not base.is_dir():
        return []
    cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
    found: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if not (
            name.endswith(".tar.gz")
            or name.endswith(".tar.gz.enc")
            or name.endswith(".tar.gz.age")
        ):
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                found.append(path)
        except OSError:
            continue
    return sorted(found)


def recent_backups_all_plaintext(paths: list[Path]) -> bool:
    """True when every recent archive is unencrypted (#1176 doctor hint)."""
    if not paths:
        return False
    return all(detect_encrypt_method(path) is None for path in paths)
