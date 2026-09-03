"""Virtual key expiry (issue #331).

Keys gain `expires_at`; an expired key is rejected with a `key_expired` 401
distinct from invalid/revoked, writes an audit row, and SSO-minted keys carry
a TTL so the local trust window tracks the IdP session instead of outliving it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore, expiry_from
from daari.cli.app import app as cli_app
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import resolve_auth

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
PAST = (NOW - timedelta(hours=1)).isoformat()
FUTURE = (NOW + timedelta(days=30)).isoformat()
CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


class TestExpiryFrom:
    def test_relative_durations(self):
        assert expiry_from("30d", now=NOW) == (NOW + timedelta(days=30)).isoformat()
        assert expiry_from("12h", now=NOW) == (NOW + timedelta(hours=12)).isoformat()
        assert expiry_from("45m", now=NOW) == (NOW + timedelta(minutes=45)).isoformat()
        assert expiry_from(" 2D ", now=NOW) == (NOW + timedelta(days=2)).isoformat()

    def test_iso_8601_is_normalised_to_utc(self):
        assert expiry_from("2026-12-31T00:00:00Z", now=NOW) == "2026-12-31T00:00:00+00:00"
        assert expiry_from("2026-12-31T02:00:00+02:00", now=NOW) == "2026-12-31T00:00:00+00:00"
        # A bare date means end of that day is not assumed: midnight UTC.
        assert expiry_from("2026-12-31", now=NOW) == "2026-12-31T00:00:00+00:00"

    def test_none_or_empty_means_never(self):
        assert expiry_from(None, now=NOW) is None
        assert expiry_from("", now=NOW) is None
        assert expiry_from("never", now=NOW) is None

    @pytest.mark.parametrize("raw", ["soon", "0d", "-3h", "3w", "12", "2026-13-40"])
    def test_invalid_is_rejected(self, raw):
        with pytest.raises(ValueError):
            expiry_from(raw, now=NOW)


class TestStore:
    def test_create_with_expiry_round_trips(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("temp", expires_at=FUTURE)
        assert created.key.expires_at == FUTURE
        assert not created.key.is_expired(now=NOW)
        assert created.key.status(now=NOW) == "active"
        listed = store.list()[0]
        assert listed.expires_at == FUTURE
        assert store.to_dict(listed)["expires_at"] == FUTURE
        assert store.to_dict(listed)["status"] == "active"

    def test_existing_keys_never_expire(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("forever")
        assert created.key.expires_at is None
        assert not created.key.is_expired(now=NOW + timedelta(days=3650))
        assert store.resolve(created.plaintext) is not None

    def test_expired_key_resolves_with_expired_status(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("old", expires_at=PAST)
        resolved = store.resolve(created.plaintext)
        assert resolved is not None
        assert resolved.is_expired(now=NOW)
        assert resolved.status(now=NOW) == "expired"

    def test_revoked_is_distinct_from_expired(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("gone", expires_at=FUTURE)
        store.revoke(created.key.key_id)
        assert store.resolve(created.plaintext) is None
        listed = store.list()[0]
        assert listed.revoked and listed.status(now=NOW) == "revoked"

    def test_migration_adds_column_to_old_database(self, tmp_path):
        path = tmp_path / "old.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.executescript(
                """
                CREATE TABLE virtual_keys (
                    key_hash TEXT PRIMARY KEY, key_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, prefix TEXT NOT NULL, created_at TEXT NOT NULL,
                    revoked_at TEXT, daily_budget_usd REAL NOT NULL DEFAULT 0,
                    monthly_budget_usd REAL NOT NULL DEFAULT 0, rpm INTEGER NOT NULL DEFAULT 0,
                    tier_cap TEXT, client_id TEXT
                );
                INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at)
                VALUES ('h', 'k1', 'legacy', 'dk_legacy', '2026-01-01T00:00:00+00:00');
                """
            )
        store = VirtualKeyStore(path)
        cols = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(virtual_keys)")}
        assert "expires_at" in cols
        legacy = store.list()[0]
        assert legacy.expires_at is None and legacy.status(now=NOW) == "active"


class TestResolveAuth:
    def test_expired_key_yields_expired_claims(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("old", client_id="c1", expires_at=PAST)
        claims = resolve_auth(created.plaintext, master_key="", store=store)
        assert claims is not None and claims.kind == "expired"
        assert claims.key_id == created.key.key_id

    def test_live_key_yields_virtual_claims(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        created = store.create("live", expires_at=FUTURE)
        claims = resolve_auth(created.plaintext, master_key="", store=store)
        assert claims is not None and claims.kind == "virtual"


def _app(settings, tmp_path, store):
    settings.server.api_key = "master"
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    return app


@pytest.mark.asyncio
async def test_middleware_rejects_expired_key_with_distinct_code_and_audits(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    expired = store.create("old", client_id="old-client", expires_at=PAST)
    live = store.create("live", client_id="live-client", expires_at=FUTURE, daily_budget_usd=5.0)
    app = _app(settings, tmp_path, store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {expired.plaintext}"},
        )
        bogus = await client.post(
            "/v1/chat/completions", json=CHAT, headers={"Authorization": "Bearer dk_nope"}
        )
        ok = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {live.plaintext}", "X-Daari-No-Cache": "true"},
        )

    assert denied.status_code == 401
    body = denied.json()["error"]
    assert body["code"] == "key_expired"
    assert body["type"] == "authentication_error"
    assert "expired" in body["message"].lower()
    assert expired.plaintext not in denied.text

    assert bogus.status_code == 401
    assert bogus.json()["error"].get("code") != "key_expired"

    # Unexpired keys keep their budget/tier behaviour (#319 headers still present).
    assert ok.status_code == 200
    assert "x-daari-budget-remaining" in ok.headers

    rows = AuditLog(settings.enterprise.audit_path).list()
    hit = [row for row in rows if row["action"] == "auth.key_expired"]
    assert len(hit) == 1
    assert hit[0]["detail"]["key_id"] == expired.key.key_id
    assert hit[0]["detail"]["expires_at"] == PAST
    assert expired.plaintext not in str(hit[0])


class TestCLI:
    def test_create_with_expires_and_list_shows_status(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        runner = CliRunner()
        created = runner.invoke(cli_app, ["keys", "create", "temp", "--expires", "30d"])
        assert created.exit_code == 0, created.output
        assert "expires:" in created.output

        store = VirtualKeyStore(settings.virtual_keys_path)
        assert store.list()[0].expires_at is not None
        store.create("stale", expires_at=PAST)
        revoked = store.create("dead")
        store.revoke(revoked.key.key_id)

        listed = runner.invoke(cli_app, ["keys", "list"])
        assert listed.exit_code == 0
        lines = {line.split()[1]: line for line in listed.output.splitlines()[1:] if line.strip()}
        assert lines["temp"].split()[-1] == "active"
        assert lines["stale"].split()[-1] == "expired"
        assert lines["dead"].split()[-1] == "revoked"
        assert "expires" in listed.output.splitlines()[0]

    def test_bad_expires_flag_exits_nonzero(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        result = CliRunner().invoke(cli_app, ["keys", "create", "temp", "--expires", "fortnight"])
        assert result.exit_code != 0
        assert VirtualKeyStore(settings.virtual_keys_path).list() == []


class TestSsoTtl:
    def _sync(self, store, sso, subject="alice"):
        from daari.enterprise.sso_keys import sync_sso_virtual_key

        return sync_sso_virtual_key(
            store,
            subject=subject,
            claims={"groups": ["eng"]},
            sso=sso,
            audit=AuditLog(store.path.parent / "audit.sqlite3"),
            role="member",
        )

    def test_key_ttl_sets_expiry_on_minted_key(self, tmp_path):
        from daari.enterprise.config import SsoKeyPolicy, SsoSettings

        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        sso = SsoSettings(mapping_claim="groups", key_mappings={"eng": SsoKeyPolicy(key_ttl="8h")})
        result = self._sync(store, sso)
        assert result["virtual_key_minted"] is True
        key = store.list()[0]
        assert key.expires_at is not None
        remaining = datetime.fromisoformat(key.expires_at) - datetime.now(timezone.utc)
        assert timedelta(hours=7, minutes=55) < remaining <= timedelta(hours=8)

    def test_expired_sso_key_is_treated_as_absent_and_reminted(self, tmp_path, monkeypatch):
        from daari.enterprise import sso_keys
        from daari.enterprise.config import SsoKeyPolicy, SsoSettings

        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        sso = SsoSettings(mapping_claim="groups", key_mappings={"eng": SsoKeyPolicy(key_ttl="8h")})
        first = self._sync(store, sso)
        # Fast-forward: the minted key is now past its TTL.
        with sqlite3.connect(store.path) as conn:
            conn.execute("UPDATE virtual_keys SET expires_at = ?", (PAST,))
        assert sso_keys.find_sso_key(store, "alice") is None

        second = self._sync(store, sso)
        assert second["virtual_key_minted"] is True
        assert second["virtual_key_id"] != first["virtual_key_id"]
        live = [k for k in store.list() if not k.is_expired()]
        assert len(live) == 1 and live[0].key_id == second["virtual_key_id"]

    def test_no_ttl_keeps_previous_behaviour(self, tmp_path):
        from daari.enterprise.config import SsoKeyPolicy, SsoSettings

        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        sso = SsoSettings(mapping_claim="groups", key_mappings={"eng": SsoKeyPolicy(rpm=5)})
        self._sync(store, sso)
        assert store.list()[0].expires_at is None
        again = self._sync(store, sso)
        assert again["virtual_key_minted"] is False

    def test_invalid_ttl_is_rejected_at_config_time(self):
        from pydantic import ValidationError

        from daari.enterprise.config import SsoKeyPolicy

        with pytest.raises(ValidationError):
            SsoKeyPolicy(key_ttl="fortnight")
