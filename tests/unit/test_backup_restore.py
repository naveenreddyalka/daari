"""Full-state backup/restore (#1131)."""

from __future__ import annotations

import json
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
