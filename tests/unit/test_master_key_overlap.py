"""Master-key overlap rotation (#711)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.security.secret_refs import resolve_settings_secrets
from daari.server.app import create_app
from daari.server.auth import master_key_matches, resolve_auth
from daari.setup.doctor import run_doctor


def test_string_master_key_is_unchanged():
    assert master_key_matches("sekret", "sekret") is True
    assert master_key_matches("nope", "sekret") is False
    assert resolve_auth("sekret", master_key="sekret", store=None).kind == "master"


def test_list_accepts_either_key_and_rejects_others():
    keys = ["old-key", "new-key"]
    assert master_key_matches("old-key", keys) is True
    assert master_key_matches("new-key", keys) is True
    assert master_key_matches("other", keys) is False
    claims = resolve_auth("new-key", master_key=keys, store=None)
    assert claims is not None and claims.kind == "master"
    assert resolve_auth("other", master_key=keys, store=None) is None


def test_gateway_accepts_each_listed_key(settings):
    settings.server.api_key = ["old-key", "new-key"]
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    for key in ("old-key", "new-key"):
        response = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
        assert response.status_code != 401
    denied = client.get("/v1/models", headers={"Authorization": "Bearer nope"})
    assert denied.status_code == 401
    rows = AuditLog(settings.enterprise.audit_path).list()
    overlap = [row for row in rows if row["action"] == "auth.master_key_overlap"]
    assert len(overlap) == 1
    assert overlap[0]["detail"] == {"count": 2}
    blob = json.dumps(rows)
    assert "old-key" not in blob
    assert "new-key" not in blob


def test_secret_refs_resolve_each_list_entry(tmp_path):
    env = tmp_path / "master.env"
    env.write_text("CURRENT=alpha-secret\nNEXT=beta-secret\n", encoding="utf-8")
    settings = Settings.model_validate(
        {
            "server": {
                "api_key": [
                    f"secret://env-file/{env}#CURRENT",
                    f"secret://env-file/{env}#NEXT",
                ]
            }
        }
    )
    resolve_settings_secrets(settings)
    assert settings.server.master_keys() == ["alpha-secret", "beta-secret"]
    assert master_key_matches("beta-secret", settings.server.api_key) is True


def test_doctor_warns_above_two_master_keys(settings):
    settings.server.api_key = ["one", "two"]
    ok = next(row for row in run_doctor(settings) if row.name == "master_keys")
    assert ok.ok is True
    settings.server.api_key = ["one", "two", "three"]
    warn = next(row for row in run_doctor(settings) if row.name == "master_keys")
    assert warn.ok is False
    assert warn.optional is True
    assert "3 master keys" in warn.detail
    assert "one" not in warn.detail
    assert "two" not in warn.detail
    assert "three" not in warn.detail
