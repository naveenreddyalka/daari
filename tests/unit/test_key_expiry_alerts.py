"""Key-expiry webhook + Prometheus lifecycle gauge (#1546)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx

from daari.auth.virtual_keys import (
    VirtualKey,
    VirtualKeyStore,
    count_key_expiry_buckets,
    key_expiry_bucket,
)
from daari.config.settings import Settings
from daari.observability.budget_alerts import sign_webhook, verify_webhook_signature
from daari.observability.key_expiry_alerts import KeyExpiryAlerter
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def _key(
    name: str,
    *,
    expires_at: str | None = None,
    revoked: bool = False,
    key_id: str | None = None,
) -> VirtualKey:
    return VirtualKey(
        key_id=key_id or f"id-{name}",
        name=name,
        prefix=f"dk_{name[:4]}",
        expires_at=expires_at,
        revoked=revoked,
    )


class TestKeyExpiryBucket:
    def test_statuses(self):
        assert key_expiry_bucket(_key("a"), now=NOW, warn_days=14) == "active"
        assert (
            key_expiry_bucket(
                _key("b", expires_at=(NOW + timedelta(days=7)).isoformat()),
                now=NOW,
                warn_days=14,
            )
            == "expiring_soon"
        )
        assert (
            key_expiry_bucket(
                _key("c", expires_at=(NOW - timedelta(hours=1)).isoformat()),
                now=NOW,
                warn_days=14,
            )
            == "expired"
        )
        assert (
            key_expiry_bucket(
                _key("d", expires_at=(NOW + timedelta(days=1)).isoformat(), revoked=True),
                now=NOW,
                warn_days=14,
            )
            == "revoked"
        )

    def test_counts(self):
        keys = [
            _key("active"),
            _key("soon", expires_at=(NOW + timedelta(days=3)).isoformat()),
            _key("dead", expires_at=(NOW - timedelta(days=1)).isoformat()),
            _key("rev", expires_at=(NOW + timedelta(days=1)).isoformat(), revoked=True),
        ]
        counts = count_key_expiry_buckets(keys, now=NOW, warn_days=14)
        assert counts == {
            "active": 1,
            "expiring_soon": 1,
            "expired": 1,
            "revoked": 1,
        }


class TestPrometheusVirtualKeysGauge:
    def test_renders_status_labels(self):
        text = render_prometheus(
            Metrics(),
            virtual_keys={
                "active": 3,
                "expired": 1,
                "expiring_soon": 2,
                "revoked": 0,
            },
        )
        assert "# TYPE daari_virtual_keys gauge" in text
        assert 'daari_virtual_keys{status="active"} 3' in text
        assert 'daari_virtual_keys{status="expired"} 1' in text
        assert 'daari_virtual_keys{status="expiring_soon"} 2' in text
        assert 'daari_virtual_keys{status="revoked"} 0' in text


class TestKeyExpiryAlerter:
    def test_defaults_disabled(self):
        alerts = Settings().alerts
        assert alerts.key_expiry_webhook_url == ""
        assert alerts.key_expiry_webhook_secret == ""
        assert alerts.key_expiry_warn_days == 14
        assert KeyExpiryAlerter(webhook_url="").enabled is False

    def test_fires_once_per_key_entering_window(self):
        posted: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(request)
            return httpx.Response(204)

        alerter = KeyExpiryAlerter(
            webhook_url="https://hooks.example/key-expiry",
            warn_days=14,
            transport=httpx.MockTransport(handler),
        )
        soon = _key("soon", expires_at=(NOW + timedelta(days=5)).isoformat())
        far = _key("far", expires_at=(NOW + timedelta(days=40)).isoformat())
        bodies = alerter.notify([soon, far], now=NOW)
        assert len(bodies) == 1
        assert bodies[0]["key_id"] == soon.key_id
        assert bodies[0]["name"] == "soon"
        assert bodies[0]["status"] == "expiring_soon"
        assert "dk_" not in str(bodies[0].get("prefix", ""))
        assert len(posted) == 1

        # Second scan does not re-fire.
        assert alerter.notify([soon, far], now=NOW) == []
        assert len(posted) == 1

    def test_signs_with_x_daari_signature(self):
        posted: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(request)
            return httpx.Response(204)

        secret = "whsec_key_expiry"
        alerter = KeyExpiryAlerter(
            webhook_url="https://hooks.example/key-expiry",
            webhook_secret=secret,
            warn_days=14,
            transport=httpx.MockTransport(handler),
        )
        soon = _key("soon", expires_at=(NOW + timedelta(days=2)).isoformat())
        alerter.notify([soon], now=NOW)
        assert len(posted) == 1
        req = posted[0]
        ts = req.headers["X-Daari-Timestamp"]
        sig = req.headers["X-Daari-Signature"]
        assert verify_webhook_signature(req.content, sig, secret, ts, now=int(ts))
        # Round-trip with shared helper.
        assert sign_webhook(req.content, secret, ts) == sig
        body = json.loads(req.content)
        assert body["event"] == "key_expiry"

    def test_redis_dedupe_fail_open(self, monkeypatch):
        events: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda name, detail=None: events.append((name, detail or {})),
        )
        posted: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(request)
            return httpx.Response(204)

        class BoomRedis:
            def set(self, *a, **k):
                raise RuntimeError("redis down")

        alerter = KeyExpiryAlerter(
            webhook_url="https://hooks.example/key-expiry",
            warn_days=14,
            transport=httpx.MockTransport(handler),
            redis=BoomRedis(),
        )
        soon = _key("soon", expires_at=(NOW + timedelta(days=2)).isoformat())
        bodies = alerter.notify([soon], now=NOW)
        assert len(bodies) == 1
        assert len(posted) == 1
        assert any(name == "key_expiry.alert_dedupe_degraded" for name, _ in events)

    def test_redis_claim_suppresses_second_replica(self):
        posted: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            posted.append(request)
            return httpx.Response(204)

        store: dict[str, str] = {}

        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                if nx and key in store:
                    return False
                store[key] = value
                return True

        redis = FakeRedis()
        a = KeyExpiryAlerter(
            webhook_url="https://hooks.example/key-expiry",
            warn_days=14,
            transport=httpx.MockTransport(handler),
            redis=redis,
        )
        b = KeyExpiryAlerter(
            webhook_url="https://hooks.example/key-expiry",
            warn_days=14,
            transport=httpx.MockTransport(handler),
            redis=redis,
        )
        soon = _key("soon", expires_at=(NOW + timedelta(days=2)).isoformat())
        assert len(a.notify([soon], now=NOW)) == 1
        assert len(b.notify([soon], now=NOW)) == 0
        assert len(posted) == 1

    def test_store_integration(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "vk.sqlite3")
        store.create("soon", expires_at=(NOW + timedelta(days=4)).isoformat())
        store.create("ok", expires_at=(NOW + timedelta(days=90)).isoformat())
        counts = count_key_expiry_buckets(store.list(), now=NOW, warn_days=14)
        assert counts["expiring_soon"] == 1
        assert counts["active"] == 1
