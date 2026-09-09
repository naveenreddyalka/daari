"""Virtual key rotation with grace overlap (issue #377)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore, grace_from
from daari.cli.app import app as cli_app
from daari.enterprise.audit import AuditLog

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


class TestGraceFrom:
    def test_default_and_relative(self):
        assert grace_from("24h", now=NOW) == (NOW + timedelta(hours=24)).isoformat()
        assert grace_from("30m", now=NOW) == (NOW + timedelta(minutes=30)).isoformat()

    def test_zero_is_immediate(self):
        assert grace_from("0", now=NOW) == NOW.isoformat()
        assert grace_from("0h", now=NOW) == NOW.isoformat()
        assert grace_from(None, now=NOW) == (NOW + timedelta(hours=24)).isoformat()


class TestRotate:
    def test_preserves_identity_and_budgets(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create(
            "alice",
            daily_budget_usd=5.0,
            rpm=10,
            tpm=1000,
            tier_cap="L3",
            team="eng",
            metadata={"mcp": {"deny": ["secret_*"]}},
        )
        rotated = store.rotate(created.key.key_id, grace="24h", now=NOW)
        assert rotated.key.key_id == created.key.key_id
        assert rotated.key.name == "alice"
        assert rotated.key.daily_budget_usd == 5.0
        assert rotated.key.rpm == 10
        assert rotated.key.tpm == 1000
        assert rotated.key.tier_cap == "L3"
        assert rotated.key.team_name == "eng"
        assert rotated.key.metadata == {"mcp": {"deny": ["secret_*"]}}
        assert rotated.plaintext != created.plaintext
        assert rotated.plaintext.startswith("dk_")
        assert rotated.key.previous_expires_at == (NOW + timedelta(hours=24)).isoformat()

    def test_both_secrets_valid_during_grace(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("alice")
        rotated = store.rotate(created.key.key_id, grace="24h", now=NOW)
        old = store.resolve(created.plaintext, now=NOW)
        new = store.resolve(rotated.plaintext, now=NOW)
        assert old is not None and new is not None
        assert old.key_id == new.key_id == created.key.key_id
        assert old.status(now=NOW) == "active"
        assert new.status(now=NOW) == "active"

    def test_old_secret_rejected_after_grace(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("alice")
        rotated = store.rotate(created.key.key_id, grace="1h", now=NOW)
        after = NOW + timedelta(hours=2)
        old = store.resolve(created.plaintext, now=after)
        assert old is not None
        assert old.is_expired(now=after)
        assert old.status(now=after) == "expired"
        assert store.resolve(rotated.plaintext, now=after) is not None
        assert store.resolve(rotated.plaintext, now=after).status(now=after) == "active"

    def test_grace_zero_immediate_cutover(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("alice")
        rotated = store.rotate(created.key.key_id, grace="0", now=NOW)
        old = store.resolve(created.plaintext, now=NOW)
        assert old is not None and old.is_expired(now=NOW)
        assert store.resolve(rotated.plaintext, now=NOW) is not None

    def test_list_shows_pending_rotation(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("alice")
        store.rotate(created.key.key_id, grace="24h", now=NOW)
        listed = store.list()[0]
        assert listed.previous_expires_at == (NOW + timedelta(hours=24)).isoformat()
        assert store.to_dict(listed)["previous_expires_at"] == listed.previous_expires_at

    def test_unknown_key_raises(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        with pytest.raises(KeyError):
            store.rotate("missing", grace="24h", now=NOW)


class TestRotateCLI:
    def test_rotate_prints_secret_and_audits(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        runner = CliRunner()
        created = runner.invoke(cli_app, ["keys", "create", "demo"])
        assert created.exit_code == 0
        key_id = [
            line.split(":", 1)[1].strip()
            for line in created.output.splitlines()
            if line.startswith("key_id:")
        ][0]
        rotated = runner.invoke(cli_app, ["keys", "rotate", key_id, "--grace", "12h"])
        assert rotated.exit_code == 0
        assert "dk_" in rotated.output
        assert "grace_until:" in rotated.output
        listed = runner.invoke(cli_app, ["keys", "list"])
        assert listed.exit_code == 0
        assert "grace" in listed.output.lower() or key_id in listed.output
        log = AuditLog(settings.enterprise.audit_path)
        rows = log.list(limit=20, action="keys.rotate")
        assert rows
        detail = rows[0].get("detail") or {}
        if isinstance(detail, str):
            import json

            detail = json.loads(detail)
        assert detail.get("key_id") == key_id
        assert "dk_" not in str(detail)
        assert "grace_until" in detail
