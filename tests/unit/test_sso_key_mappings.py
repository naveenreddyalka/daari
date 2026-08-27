"""IdP claim → virtual-key policy (issue #176)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.audit import AuditLog
from daari.enterprise.config import SsoKeyPolicy, SsoSettings
from daari.enterprise.sso import mint_dev_token
from daari.enterprise.sso_keys import resolve_policy, sync_sso_virtual_key
from daari.router.router import AppContext
from daari.server.app import create_app


def test_resolve_policy_picks_first_mapped_group():
    sso = SsoSettings(
        mapping_claim="groups",
        key_mappings={
            "eng": SsoKeyPolicy(rpm=60, daily_budget_usd=5, tier_cap="L4"),
            "contractors": SsoKeyPolicy(tier_cap="L3"),
        },
    )
    value, policy = resolve_policy({"groups": ["unknown", "eng"]}, sso)
    assert value == "eng"
    assert policy is not None
    assert policy.rpm == 60


def test_resolve_policy_falls_back_to_default():
    sso = SsoSettings(
        mapping_claim="department",
        key_mappings={"eng": SsoKeyPolicy(rpm=10)},
        default_policy=SsoKeyPolicy(tier_cap="L3"),
    )
    value, policy = resolve_policy({"department": "sales"}, sso)
    assert value == "__default__"
    assert policy is not None
    assert policy.tier_cap == "L3"


def test_sync_mints_with_mapped_limits(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    audit = AuditLog(tmp_path / "audit.sqlite3")
    sso = SsoSettings(
        mapping_claim="groups",
        key_mappings={"eng": SsoKeyPolicy(rpm=60, daily_budget_usd=5, tier_cap="L4")},
    )
    minted = sync_sso_virtual_key(
        store,
        subject="alice",
        claims={"groups": ["eng"]},
        sso=sso,
        audit=audit,
        role="user",
    )
    assert minted["virtual_key_minted"] is True
    key = store.list()[0]
    assert key.rpm == 60
    assert key.daily_budget_usd == 5
    assert key.tier_cap == "L4"
    events = audit.list()
    assert events[0]["action"] == "sso.mint_virtual_key"
    assert events[0]["detail"]["claim_value"] == "eng"


def test_sync_revokes_when_mapped_claim_disappears(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    audit = AuditLog(tmp_path / "audit.sqlite3")
    sso = SsoSettings(
        mapping_claim="groups",
        deny_unmapped=True,
        key_mappings={"eng": SsoKeyPolicy(rpm=60)},
    )
    sync_sso_virtual_key(
        store,
        subject="alice",
        claims={"groups": ["eng"]},
        sso=sso,
        audit=audit,
        role="user",
    )
    from daari.enterprise.sso_keys import UnmappedSsoPolicy

    with pytest.raises(UnmappedSsoPolicy):
        sync_sso_virtual_key(
            store,
            subject="alice",
            claims={"groups": ["sales"]},
            sso=sso,
            audit=audit,
            role="user",
        )
    assert all(k.revoked for k in store.list())
    assert any(e["action"] == "sso.revoke_virtual_key" for e in audit.list())


def _app(settings, tmp_path):
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sekret"
    settings.enterprise.sso.mint_virtual_key_on_login = True
    settings.enterprise.sso.mapping_claim = "groups"
    settings.enterprise.sso.key_mappings = {
        "eng": SsoKeyPolicy(rpm=60, daily_budget_usd=2, boundary_profile="fintech")
    }
    settings.enterprise.sso.default_policy = SsoKeyPolicy(tier_cap="L3")
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_session_mints_mapped_key(settings, tmp_path):
    app = _app(settings, tmp_path)
    token = mint_dev_token(subject="bob", role="user", secret="sekret", extra={"groups": ["eng"]})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/daari/sso/session", headers={"Authorization": f"Bearer {token}"}
        )
        again = await client.post(
            "/v1/daari/sso/session", headers={"Authorization": f"Bearer {token}"}
        )
    assert first.status_code == 200
    body = first.json()
    assert body["virtual_key_minted"] is True
    assert body["claim_value"] == "eng"
    assert body["boundary_profile"] == "fintech"
    assert again.json()["virtual_key_minted"] is False
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    assert store.list()[0].rpm == 60


@pytest.mark.asyncio
async def test_session_denies_unmapped_when_configured(settings, tmp_path):
    app = _app(settings, tmp_path)
    settings.enterprise.sso.default_policy = None
    settings.enterprise.sso.deny_unmapped = True
    token = mint_dev_token(subject="zoe", role="user", secret="sekret", extra={"groups": ["sales"]})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/sso/session", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403
