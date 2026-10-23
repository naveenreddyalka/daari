"""Anthropic organization enforcement webhook ingest (#1875)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import AnthropicSettings, Settings
from daari.enterprise.anthropic_org_webhooks import (
    ENFORCEMENT_OPENED,
    ENFORCEMENT_RESOLVED,
    sign_standard_webhook,
    verify_standard_webhook_signature,
)
from daari.enterprise.enforcement_sync import EnforcementStore
from daari.router.router import AppContext
from daari.server.app import create_app

SECRET_RAW = b"test-org-webhook-secret-key!!"
SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode()


def _event(
    event_type: str,
    *,
    profile_id: str = "uprof_011CZkZCu8hGbp5mYRQgUmz9",
    action_id: str = "enac_011CZkZEq4TnWb7xLfRgPm2v",
) -> dict:
    return {
        "type": "event",
        "id": "whe_4f2a9c1e7b3d5a8f0e6c2b9d1a7f3e5c",
        "created_at": "2026-10-15T17:02:41Z",
        "data": {
            "type": event_type,
            "id": profile_id,
            "enforcement_action_id": action_id,
            "organization_id": "org_011CZkZBj9RsYd3wNcHvKq6t",
        },
    }


def _signed_headers(body: bytes, secret: str = SECRET, *, ts: str | None = None) -> dict[str, str]:
    msg_id = "msg_test_org_webhook_1"
    timestamp = ts if ts is not None else str(int(time.time()))
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": sign_standard_webhook(body, secret, msg_id, timestamp),
        "content-type": "application/json",
    }


class TestStandardWebhookSignature:
    def test_round_trip(self):
        body = b'{"type":"event"}'
        headers = _signed_headers(body)
        assert verify_standard_webhook_signature(
            body,
            headers,
            SECRET,
            now=int(headers["webhook-timestamp"]),
        )

    def test_rejects_bad_signature(self):
        body = b'{"type":"event"}'
        headers = _signed_headers(body)
        headers["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        assert not verify_standard_webhook_signature(
            body,
            headers,
            SECRET,
            now=int(headers["webhook-timestamp"]),
        )

    def test_accepts_previous_secret_during_rotation(self):
        body = b'{"hello":"world"}'
        old = "whsec_" + base64.b64encode(b"old-secret-bytes-here!!!!").decode()
        headers = _signed_headers(body, secret=old)
        assert verify_standard_webhook_signature(
            body,
            headers,
            SECRET,
            previous_secret=old,
            now=int(headers["webhook-timestamp"]),
        )


@pytest.mark.asyncio
async def test_org_webhook_disabled_returns_404(settings, tmp_path):
    settings.anthropic = AnthropicSettings(
        enforcement_state_path=str(tmp_path / "e.json"),
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    body = json.dumps(_event(ENFORCEMENT_OPENED)).encode()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_headers(body),
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_org_webhook_bad_signature_returns_401(settings, tmp_path):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=SECRET,
        enforcement_state_path=str(tmp_path / "e.json"),
        user_profiles={"erin": "uprof_011CZkZCu8hGbp5mYRQgUmz9"},
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    body = json.dumps(_event(ENFORCEMENT_OPENED)).encode()
    headers = _signed_headers(body)
    headers["webhook-signature"] = "v1," + base64.b64encode(b"x" * 32).decode()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=headers,
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_org_webhook_unknown_event_acked(settings, tmp_path):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=SECRET,
        enforcement_state_path=str(tmp_path / "e.json"),
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    body = json.dumps(_event("user_profile.something_else")).encode()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_headers(body),
        )
    assert response.status_code == 200
    assert response.json()["ignored"] is True


@pytest.mark.asyncio
async def test_org_webhook_opened_updates_store_and_maps_end_users(
    settings, tmp_path, monkeypatch
):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    profile_id = "uprof_011CZkZCu8hGbp5mYRQgUmz9"
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=SECRET,
        enforcement_state_path=str(tmp_path / "e.json"),
        user_profiles={"erin": profile_id, "other": "uprof_other"},
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/v1/user_profiles/{profile_id}")
        return httpx.Response(
            200,
            json={
                "type": "user_profile",
                "id": profile_id,
                "enforcement_status": "banned",
                "enforcement_actions": [
                    {
                        "type": "ban",
                        "id": "enac_011CZkZEq4TnWb7xLfRgPm2v",
                        "reason": "fraud_or_abuse",
                        "opened_at": "2026-10-15T17:02:41Z",
                        "expires_at": None,
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "daari.enterprise.anthropic_org_webhooks._default_transport",
        lambda: httpx.MockTransport(handler),
    )
    # Provide a frontier key so the handler fetches the profile.
    monkeypatch.setattr(
        type(settings),
        "resolve_frontier_api_key",
        lambda self: "sk-ant-test",
        raising=False,
    )

    events: list[tuple[str, dict]] = []

    def capture(name: str, payload: dict | None = None, **_: object) -> None:
        events.append((name, payload or {}))

    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        capture,
    )

    body = json.dumps(_event(ENFORCEMENT_OPENED, profile_id=profile_id)).encode()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_headers(body),
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["profile_id"] == profile_id
    assert payload["enforcement_status"] == "banned"
    assert payload["end_users"] == ["erin"]

    store = EnforcementStore(Path(settings.anthropic.enforcement_state_path))
    rows = store.load()
    assert len(rows) == 1
    assert rows[0]["profile_id"] == profile_id
    assert rows[0]["enforcement_status"] == "banned"
    assert rows[0]["end_users"] == ["erin"]

    names = [n for n, _ in events]
    assert "anthropic.enforcement_webhook_ingested" in names
    assert "anthropic.enforcement_started" in names


@pytest.mark.asyncio
async def test_org_webhook_resolved_clears_unrestricted_profile(
    settings, tmp_path, monkeypatch
):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    profile_id = "uprof_clear_me"
    state_path = tmp_path / "e.json"
    store = EnforcementStore(state_path)
    store.save(
        [
            {
                "profile_id": profile_id,
                "enforcement_status": "restricted",
                "enforcement_actions": [{"id": "enac_old"}],
                "end_users": ["erin"],
                "updated_at": "2026-10-01T00:00:00+00:00",
            }
        ]
    )
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=SECRET,
        enforcement_state_path=str(state_path),
        user_profiles={"erin": profile_id},
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "type": "user_profile",
                "id": profile_id,
                "enforcement_status": "unrestricted",
                "enforcement_actions": [],
            },
        )

    monkeypatch.setattr(
        "daari.enterprise.anthropic_org_webhooks._default_transport",
        lambda: httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        type(settings),
        "resolve_frontier_api_key",
        lambda self: "sk-ant-test",
        raising=False,
    )
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda name, payload=None, **_: events.append(name),
    )

    body = json.dumps(
        _event(ENFORCEMENT_RESOLVED, profile_id=profile_id)
    ).encode()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_headers(body),
        )
    assert response.status_code == 200
    assert store.load() == []
    assert "anthropic.enforcement_ended" in events


def test_docs_cover_org_webhook_enable_and_rotate() -> None:
    root = Path(__file__).resolve().parents[2]
    guide = (
        root / "docs/developer/guides/features/anthropic-enforcement-webhooks.md"
    ).read_text(encoding="utf-8")
    assert "/v1/daari/webhooks/anthropic/org" in guide
    assert "org_webhook_signing_secret" in guide
    assert "org_webhook_signing_secret_previous" in guide
    assert "whsec_" in guide
    config = (root / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "anthropic.org_webhook_signing_secret" in config
