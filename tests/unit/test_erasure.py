"""Subject erasure across stores (#1130)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.compliance.erasure import ErasureSubject, erase_subject
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.batches import BatchGovernance, BatchStore
from daari.gateway.files import FileStore
from daari.gateway.idempotency_store import IdempotencyStore
from daari.gateway.postgres_responses import PostgresResponseStore
from daari.gateway.request_log import erase_subject_from_logs
from daari.gateway.response_store import ResponseStore
from daari.observability.spend import SpendLedger
from daari.observability.usage import UsageLedger


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "trace": {"path": str(tmp_path / "traces.sqlite3")},
            "usage": {
                "path": str(tmp_path / "usage.sqlite3"),
                "spend": {"enabled": True, "path": str(tmp_path / "spend.sqlite3")},
            },
            "enterprise": {"audit_path": str(tmp_path / "audit.sqlite3")},
            "files": {"enabled": True, "path": str(tmp_path / "files")},
            "batches": {"enabled": True, "path": str(tmp_path / "batches.sqlite3")},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
        }
    )


def test_spend_erase_keeps_other_key(tmp_path):
    settings = _settings(tmp_path)
    spend = SpendLedger(settings.usage.spend.path, enabled=True)
    spend.record(key_id="key-a", request_id="1", cost_usd=0.1)
    spend.record(key_id="key-b", request_id="2", cost_usd=0.2)
    assert spend.erase_subject(key_id="key-a", dry_run=True) == 1
    assert spend.erase_subject(key_id="key-a") == 1
    rows = list(spend.iter_rows(since="1970-01-01"))
    assert len(rows) == 1
    assert rows[0]["key_id"] == "key-b"


def test_postgres_responses_erase_memory():
    dsn = f"memory:erase-resp-{uuid.uuid4().hex}"
    store = PostgresResponseStore(dsn)
    store.put("resp-a", {"id": "resp-a"}, owner_key_id="key-a")
    store.put("resp-b", {"id": "resp-b"}, owner_key_id="key-b")
    assert store.erase_owner_keys(["key-a"]) == 1
    assert store.get("resp-a") is None
    assert store.get("resp-b") is not None


def test_usage_erase_user_keeps_other(tmp_path):
    settings = _settings(tmp_path)
    ledger = UsageLedger(settings.usage.path, enabled=True)
    ledger.record(tier="L3", client_id="c1", user_id="user-a", prompt_chars=10)
    ledger.record(tier="L3", client_id="c1", user_id="user-b", prompt_chars=10)
    assert ledger.erase_subject(user_id="user-a") == 1
    by_user = ledger.by_user(days=365)
    assert len(by_user) == 1
    assert by_user[0]["user_id"] == "user-b"


def test_responses_and_files_erase_owner(tmp_path):
    settings = _settings(tmp_path)
    responses = ResponseStore(Path(settings.trace.path).parent / "responses.sqlite3")
    responses.put("resp-a", {"id": "resp-a"}, owner_key_id="key-a")
    responses.put("resp-b", {"id": "resp-b"}, owner_key_id="key-b")
    assert responses.erase_owner_keys(["key-a"]) == 1
    assert responses.get("resp-a") is None
    assert responses.get("resp-b") is not None

    files = FileStore(settings.files_store_path)
    files.create(content=b"aaa", filename="a.txt", purpose="assistants", owner_key_id="key-a")
    files.create(content=b"bbb", filename="b.txt", purpose="assistants", owner_key_id="key-b")
    assert files.erase_owner_keys(["key-a"]) == 1
    listed = files.list_files()
    assert len(listed) == 1
    assert listed[0].owner_key_id == "key-b"


def test_batches_idempotency_and_request_log(tmp_path):
    settings = _settings(tmp_path)
    batches = BatchStore(path=settings.batches_store_path)
    batches.create(
        requests=[{"custom_id": "1", "method": "POST", "url": "/v1/chat/completions", "body": {}}],
        governance=BatchGovernance(key_id="key-a", team_id="team-a", user="user-a"),
    )
    batches.create(
        requests=[{"custom_id": "2", "method": "POST", "url": "/v1/chat/completions", "body": {}}],
        governance=BatchGovernance(key_id="key-b"),
    )
    assert batches.erase_subject(key_id="key-a") == 1
    assert len(batches.list_batches()) == 1

    idem = IdempotencyStore(Path(settings.trace.path).parent / "idempotency.sqlite3")
    assert idem.begin("vk:key-a", "ik-1", "h1") is True
    assert idem.begin("vk:key-b", "ik-2", "h2") is True
    assert idem.erase_principals(["vk:key-a"]) == 1

    log = tmp_path / "req.log"
    log.write_text(
        json.dumps({"ts": "t", "event": "x", "key_id": "key-a"})
        + "\n"
        + json.dumps({"ts": "t", "event": "y", "key_id": "key-b"})
        + "\n",
        encoding="utf-8",
    )
    assert erase_subject_from_logs(log, kind="key", value="key-a") == 1
    assert "key-a" not in log.read_text(encoding="utf-8")
    assert "key-b" in log.read_text(encoding="utf-8")


def test_erase_subject_orchestrator_dry_run_and_audit(tmp_path):
    settings = _settings(tmp_path)
    spend = SpendLedger(settings.usage.spend.path, enabled=True)
    spend.record(key_id="key-a", request_id="1", cost_usd=0.1)
    spend.record(key_id="key-b", request_id="2", cost_usd=0.2)

    dry = erase_subject(settings, ErasureSubject("key", "key-a"), dry_run=True)
    spend_row = next(r for r in dry.stores if r.store == "spend")
    assert spend_row.matched == 1
    assert len(list(spend.iter_rows(since="1970-01-01"))) == 2

    applied = erase_subject(settings, ErasureSubject("key", "key-a"), dry_run=False)
    assert next(r for r in applied.stores if r.store == "spend").deleted == 1
    assert [r["key_id"] for r in spend.iter_rows(since="1970-01-01")] == ["key-b"]

    audit = AuditLog(settings.enterprise.audit_path)
    rows = [r for r in audit.list() if r["action"] == "compliance.erase"]
    assert len(rows) == 1
    assert rows[0]["detail"]["subject_id"] == "key-a"


def test_cli_erase_dry_run(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    SpendLedger(settings.usage.spend.path, enabled=True).record(
        key_id="key-a", request_id="1", cost_usd=0.1
    )
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    result = CliRunner().invoke(cli_app, ["erase", "--key", "key-a", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry-run erase key=key-a" in result.output
    assert "spend" in result.output
