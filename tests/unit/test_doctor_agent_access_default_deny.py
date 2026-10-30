"""Doctor tip when agent_access_default_deny is on and no keys have grants (#2004)."""

from __future__ import annotations

from pathlib import Path

from daari.auth.virtual_keys import VirtualKeyStore
from daari.setup.doctor import _check_agent_access_default_deny, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def test_tip_when_deny_on_and_zero_grants(settings, tmp_path):
    settings.server.virtual_keys.agent_access_default_deny = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("nogrant", client_id="nogrant")
    row = _check_agent_access_default_deny(settings)
    assert row is not None
    assert row.name == "agent_access_default_deny"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "agent_access_default_deny" in detail
    assert "grant" in detail or "agents_access" in detail or "allowed_agents" in detail


def test_tip_absent_when_flag_off(settings, tmp_path):
    settings.server.virtual_keys.agent_access_default_deny = False
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    assert _check_agent_access_default_deny(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "agent_access_default_deny" for r in rows)


def test_tip_absent_when_at_least_one_grant(settings, tmp_path):
    settings.server.virtual_keys.agent_access_default_deny = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("granted", client_id="granted", metadata={"agents_access": True})
    assert _check_agent_access_default_deny(settings) is None


def test_doctor_health_docs_mention_agent_access_tip():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "agent_access_default_deny" in text
    row = next(
        line
        for line in text.splitlines()
        if "agent_access_default_deny" in line and line.startswith("|")
    )
    assert "grant" in row.lower() or "agents_access" in row or "allowed_agents" in row
