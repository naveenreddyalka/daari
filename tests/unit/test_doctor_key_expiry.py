"""Doctor key-expiry scan (#1546)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daari.auth.virtual_keys import VirtualKeyStore
from daari.setup.doctor import _check_key_expiry, run_doctor


NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class TestKeyExpiryDoctor:
    def _down_client(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_warns_expiring_soon_and_counts_expired(self, settings, tmp_path):
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        settings.alerts.key_expiry_warn_days = 14
        store = VirtualKeyStore(settings.virtual_keys_path)
        store.create(
            "soon",
            expires_at=(NOW + timedelta(days=7)).isoformat(),
        )
        store.create(
            "stale",
            expires_at=(NOW - timedelta(days=1)).isoformat(),
        )
        store.create(
            "far",
            expires_at=(NOW + timedelta(days=60)).isoformat(),
        )
        created = store.create("gone", expires_at=(NOW + timedelta(days=3)).isoformat())
        store.revoke(created.key.key_id)

        result = _check_key_expiry(settings, now=NOW)
        assert result.ok is False
        assert result.optional is True
        assert "soon" in result.detail
        assert "expired=1" in result.detail
        assert "gone" not in result.detail  # revoked excluded from expiry warn list

    def test_quiet_when_no_expiry_pressure(self, settings, tmp_path):
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        settings.alerts.key_expiry_warn_days = 14
        store = VirtualKeyStore(settings.virtual_keys_path)
        store.create("forever")
        store.create("later", expires_at=(NOW + timedelta(days=90)).isoformat())
        result = _check_key_expiry(settings, now=NOW)
        assert result.ok is True
        assert "expired=0" in result.detail or "no keys" in result.detail.lower() or "0" in result.detail

    def test_quiet_when_virtual_keys_disabled(self, settings):
        settings.server.virtual_keys.enabled = False
        result = _check_key_expiry(settings, now=NOW)
        assert result.ok is True
        assert result.optional is True

    def test_run_doctor_includes_check(self, settings, tmp_path):
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        settings.alerts.key_expiry_warn_days = 14
        VirtualKeyStore(settings.virtual_keys_path).create(
            "soon",
            expires_at=(NOW + timedelta(days=2)).isoformat(),
        )
        results = run_doctor(settings, httpx_client=self._down_client())
        by_name = {r.name: r for r in results}
        assert "key_expiry" in by_name
        assert by_name["key_expiry"].ok is False

    def test_warn_days_configurable(self, settings, tmp_path):
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.server.virtual_keys.enabled = True
        settings.alerts.key_expiry_warn_days = 3
        VirtualKeyStore(settings.virtual_keys_path).create(
            "week",
            expires_at=(NOW + timedelta(days=7)).isoformat(),
        )
        result = _check_key_expiry(settings, now=NOW)
        assert result.ok is True
