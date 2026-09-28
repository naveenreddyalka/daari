"""Full-state backup/restore (#1131, #1176)."""

from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.observability.spend import SpendLedger
from daari.ops.backup import (
    ARCHIVE_SCHEMA_VERSION,
    BackupError,
    create_backup,
    restore_backup,
)
from daari.setup.doctor import _check_recent_backup


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "trace": {"path": str(tmp_path / "traces.sqlite3")},
            "usage": {
                "path": str(tmp_path / "usage.sqlite3"),
                "spend": {"enabled": True, "path": str(tmp_path / "spend.sqlite3")},
            },
            "server": {
                "virtual_keys": {
                    "enabled": True,
                    "path": str(tmp_path / "keys.sqlite3"),
                }
            },
            "enterprise": {"audit_path": str(tmp_path / "audit.sqlite3")},
            "files": {"enabled": True, "path": str(tmp_path / "files")},
            "batches": {"enabled": True, "path": str(tmp_path / "batches.sqlite3")},
        }
    )


def _seed(settings: Settings) -> None:
    keys = VirtualKeyStore(settings.server.virtual_keys.path, enabled=True)
    keys.create(name="alpha", daily_budget_usd=1.0)
    AuditLog(settings.enterprise.audit_path).record(
        actor="op", role="admin", action="test.seed"
    )
    SpendLedger(settings.usage.spend.path, enabled=True).record(
        key_id="k1", request_id="r1", cost_usd=0.42
    )


def test_create_restore_round_trip(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    log = src / "requests.log"
    log.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", log)
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "daari.tar.gz"
    manifest = create_backup(settings, archive)
    assert archive.is_file()
    assert manifest.archive_schema_version == ARCHIVE_SCHEMA_VERSION
    assert any(s["name"] == "virtual-keys" and s["present"] for s in manifest.stores)

    dst = tmp_path / "dst"
    dst.mkdir()
    dst_log = dst / "requests.log"
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", dst_log)
    restored_settings = _settings(dst)
    restore_backup(restored_settings, archive)

    keys = VirtualKeyStore(restored_settings.server.virtual_keys.path, enabled=True)
    assert any(k.name == "alpha" for k in keys.list())
    audit = AuditLog(restored_settings.enterprise.audit_path)
    assert any(r["action"] == "test.seed" for r in audit.list())
    spend = SpendLedger(restored_settings.usage.spend.path, enabled=True)
    rows = list(spend.iter_rows(since="1970-01-01"))
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == pytest.approx(0.42)
    assert dst_log.is_file()


def test_newer_schema_archive_refused(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "new.tar.gz"
    create_backup(settings, archive)

    # Rewrite manifest inside the archive with a future schema version.
    with tarfile.open(archive, "r:gz") as tar:
        data = json.loads(tar.extractfile("manifest.json").read().decode())
    data["archive_schema_version"] = ARCHIVE_SCHEMA_VERSION + 5
    rebuilt = tmp_path / "future.tar.gz"
    with tarfile.open(rebuilt, "w:gz") as tar:
        with tarfile.open(archive, "r:gz") as old:
            for member in old.getmembers():
                if member.name == "manifest.json":
                    continue
                extracted = old.extractfile(member)
                if extracted is None:
                    continue
                info = tarfile.TarInfo(name=member.name)
                payload = extracted.read()
                info.size = len(payload)
                tar.addfile(info, fileobj=__import__("io").BytesIO(payload))
        blob = json.dumps(data).encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(blob)
        tar.addfile(info, fileobj=__import__("io").BytesIO(blob))

    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(BackupError, match="newer than"):
        restore_backup(_settings(dst), rebuilt)


def test_cli_backup_create(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    _seed(settings)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    archive = tmp_path / "out.tar.gz"
    result = CliRunner().invoke(cli_app, ["backup", "create", str(archive)])
    assert result.exit_code == 0, result.output
    assert archive.is_file()


def test_doctor_backup_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daari.ops.backup.recent_backup_manifests",
        lambda **kwargs: [],
    )
    result = _check_recent_backup(_settings(tmp_path))
    assert result.optional is True
    assert result.ok is False
    assert "daari backup create" in result.detail


def test_catalog_postgres_batches_and_files(tmp_path):
    from daari.ops.backup import catalog_stores

    settings = _settings(tmp_path)
    settings.batches.backend = "postgres"
    settings.files.backend = "postgres"
    settings.observability.postgres_url = "postgresql://localhost/daari"
    by_name = {e.name: e for e in catalog_stores(settings)}
    assert by_name["batches"].backend == "postgres"
    assert "daari_batch_jobs" in (by_name["batches"].pg_dump or "")
    assert by_name["files"].backend == "postgres"
    assert "daari_files" in (by_name["files"].pg_dump or "")


def test_rotated_request_logs_round_trip(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    log = src / "requests.log"
    log.write_text('{"event":"active"}\n', encoding="utf-8")
    rotated = src / "requests.log.1"
    rotated.write_text('{"event":"old"}\n', encoding="utf-8")
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", log)
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "with-rotated.tar.gz"
    manifest = create_backup(settings, archive)
    assert any(s["name"] == "request-log.1" and s["present"] for s in manifest.stores)

    dst = tmp_path / "dst"
    dst.mkdir()
    dst_log = dst / "requests.log"
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", dst_log)
    restore_backup(_settings(dst), archive, allow_running_server=True)
    assert dst_log.is_file()
    assert (dst / "requests.log.1").read_text(encoding="utf-8") == '{"event":"old"}\n'


def test_restore_refuses_when_server_healthy(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    log = src / "requests.log"
    log.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", log)
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "hot.tar.gz"
    create_backup(settings, archive)
    monkeypatch.setattr("daari.ops.backup.server_appears_running", lambda _s: True)
    dst = tmp_path / "dst"
    dst.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", dst / "requests.log")
    with pytest.raises(BackupError, match="server appears to be running"):
        restore_backup(_settings(dst), archive)
    restore_backup(_settings(dst), archive, allow_running_server=True)


def test_docs_mention_pg_batches_files_and_interlock():
    doc = Path("docs/developer/guides/operations/backup-restore.md").read_text(
        encoding="utf-8"
    )
    assert "daari_batch_jobs" in doc
    assert "daari_files" in doc
    assert "i-know-server-is-stopped" in doc
    assert "request-log" in doc.lower() or "rotated" in doc.lower()
    assert "--encrypt openssl" in doc
    assert "DAARI_BACKUP_PASS" in doc


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not on PATH")
def test_openssl_encrypt_restore_round_trip(tmp_path, monkeypatch):
    from daari.ops.backup import encrypt_backup_archive

    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "secret.tar.gz"
    create_backup(settings, archive)
    monkeypatch.setenv("DAARI_BACKUP_PASS", "unit-test-passphrase-1176")
    enc = encrypt_backup_archive(archive, "openssl")
    assert enc.name.endswith(".tar.gz.enc")
    assert enc.is_file()
    assert not archive.exists()

    dst = tmp_path / "dst"
    dst.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", dst / "requests.log")
    restore_backup(_settings(dst), enc, allow_running_server=True)
    keys = VirtualKeyStore(_settings(dst).server.virtual_keys.path, enabled=True)
    assert any(k.name == "alpha" for k in keys.list())


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not on PATH")
def test_encrypted_restore_refuses_without_passphrase(tmp_path, monkeypatch):
    from daari.ops.backup import encrypt_backup_archive

    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _settings(src)
    _seed(settings)
    archive = tmp_path / "locked.tar.gz"
    create_backup(settings, archive)
    monkeypatch.setenv("DAARI_BACKUP_PASS", "unit-test-passphrase-1176")
    enc = encrypt_backup_archive(archive, "openssl")
    monkeypatch.delenv("DAARI_BACKUP_PASS", raising=False)
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(BackupError, match="passphrase"):
        restore_backup(_settings(dst), enc, allow_running_server=True)


def test_doctor_hints_plaintext_when_encrypt_available(tmp_path, monkeypatch):
    plain = tmp_path / "daari.tar.gz"
    plain.write_bytes(b"not-a-real-archive")
    monkeypatch.setattr(
        "daari.ops.backup.recent_backup_manifests",
        lambda **kwargs: [plain],
    )
    result = _check_recent_backup(_settings(tmp_path))
    assert result.ok is True
    assert "--encrypt openssl" in result.detail


def test_cli_backup_create_encrypt_openssl(tmp_path, monkeypatch):
    import shutil

    if shutil.which("openssl") is None:
        pytest.skip("openssl not on PATH")
    settings = _settings(tmp_path)
    _seed(settings)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setenv("DAARI_BACKUP_PASS", "cli-pass-1176")
    archive = tmp_path / "cli.tar.gz"
    result = CliRunner().invoke(
        cli_app,
        ["backup", "create", str(archive), "--encrypt", "openssl"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "cli.tar.gz.enc").is_file()
    assert not archive.exists()


def _install_pg_dump_shim(tmp_path: Path, monkeypatch, *, fail: bool = False) -> Path:
    """Put a fake ``pg_dump`` on PATH that writes a deterministic SQL payload."""
    import hashlib
    import os
    import stat

    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "pg_dump"
    if fail:
        shim.write_text("#!/bin/sh\necho boom >&2\nexit 1\n", encoding="utf-8")
    else:
        shim.write_text(
            "#!/bin/sh\nprintf '%s\\n' '-- fake pg_dump for unit test'\n",
            encoding="utf-8",
        )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return shim


def _pg_settings(tmp_path: Path) -> Settings:
    settings = _settings(tmp_path)
    settings.batches.backend = "postgres"
    settings.files.backend = "postgres"
    settings.observability.postgres_url = "postgresql://localhost/daari"
    return settings


def test_create_embeds_pg_dump_when_on_path(tmp_path, monkeypatch):
    import hashlib

    _install_pg_dump_shim(tmp_path, monkeypatch)
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _pg_settings(src)
    _seed(settings)
    archive = tmp_path / "with-pg.tar.gz"
    manifest = create_backup(settings, archive)
    by_name = {s["name"]: s for s in manifest.stores}
    batches = by_name["batches"]
    assert batches["backend"] == "embedded"
    assert batches.get("external") is not True
    assert batches["archive_path"] == "stores/pg/batches.sql"
    assert batches["present"] is True
    assert batches["size_bytes"] > 0
    expected = hashlib.sha256(b"-- fake pg_dump for unit test\n").hexdigest()
    assert batches["sha256"] == expected

    with tarfile.open(archive, "r:gz") as tar:
        raw = tar.extractfile("stores/pg/batches.sql")
        assert raw is not None
        assert raw.read() == b"-- fake pg_dump for unit test\n"


def test_create_falls_back_external_without_pg_dump(tmp_path, monkeypatch):
    import os

    # Ensure no real pg_dump is visible.
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _pg_settings(src)
    archive = tmp_path / "hint-only.tar.gz"
    manifest = create_backup(settings, archive)
    batches = next(s for s in manifest.stores if s["name"] == "batches")
    assert batches["backend"] == "postgres"
    assert batches.get("external") is True
    assert "pg_dump" in (batches.get("pg_dump") or "")
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert not any(n.startswith("stores/pg/") for n in names)


def test_create_require_pg_dump_fails_when_missing(tmp_path, monkeypatch):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _pg_settings(src)
    with pytest.raises(BackupError, match="pg_dump"):
        create_backup(settings, tmp_path / "req.tar.gz", require_pg_dump=True)


def test_create_require_pg_dump_fails_on_dump_error(tmp_path, monkeypatch):
    _install_pg_dump_shim(tmp_path, monkeypatch, fail=True)
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _pg_settings(src)
    with pytest.raises(BackupError, match="pg_dump"):
        create_backup(settings, tmp_path / "fail.tar.gz", require_pg_dump=True)


def test_restore_embedded_pg_offers_psql(tmp_path, monkeypatch):
    _install_pg_dump_shim(tmp_path, monkeypatch)
    # Fake psql that records the -f path.
    import os
    import stat

    bin_dir = tmp_path / "fake-bin"
    psql = bin_dir / "psql"
    record = tmp_path / "psql-invocations.txt"
    psql.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{record}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    psql.chmod(psql.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", src / "requests.log")
    (src / "requests.log").write_text("{}\n", encoding="utf-8")
    settings = _pg_settings(src)
    archive = tmp_path / "embed.tar.gz"
    create_backup(settings, archive)

    dst = tmp_path / "dst"
    dst.mkdir()
    monkeypatch.setattr("daari.gateway.request_log.LOG_PATH", dst / "requests.log")
    restored = restore_backup(
        _pg_settings(dst),
        archive,
        allow_running_server=True,
        restore_pg=True,
    )
    assert any(s.get("backend") == "embedded" for s in restored.stores)
    text = record.read_text(encoding="utf-8")
    assert "stores/pg/batches.sql" in text or "batches.sql" in text


def test_docs_mention_embedded_pg_dump():
    doc = Path("docs/developer/guides/operations/backup-restore.md").read_text(
        encoding="utf-8"
    )
    assert "embedded" in doc.lower()
    assert "--require-pg-dump" in doc
    assert "stores/pg/" in doc
