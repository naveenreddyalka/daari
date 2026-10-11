"""Filter GET /v1/models by virtual-key allowed_models (#1555)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import Settings
from daari.router.capabilities import anthropic_models_payload, openai_models_payload
from daari.router.router import AppContext
from daari.server.app import create_app


def _settings_with_lifecycle() -> Settings:
    return Settings.model_validate(
        {
            "server": {"api_key": "master"},
            "models": {
                "lifecycle": {
                    "llama3.2:3b": {
                        "lifecycle": "deprecated",
                        "deprecated_at": "2026-01-01T00:00:00Z",
                    },
                    "retired-model": {"lifecycle": "retired"},
                }
            },
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "anthropic", "model": "claude-sonnet-5-5"},
                    {"id": "local", "model": "retired-model"},
                ],
            },
            "model_groups": {"anthropic": ["claude-*"], "local": ["llama*"]},
        }
    )


def test_openai_payload_filters_by_allowlist_patterns():
    settings = _settings_with_lifecycle()
    full = {c["id"] for c in openai_models_payload(settings)["data"]}
    assert "claude-sonnet-5-5" in full
    assert "llama3.2:3b" in full

    filtered = openai_models_payload(settings, key_patterns=["claude-*"], team_patterns=None)
    ids = {c["id"] for c in filtered["data"]}
    assert "claude-sonnet-5-5" in ids
    assert "llama3.2:3b" not in ids
    assert ids <= full


def test_anthropic_payload_filters_by_allowlist_patterns():
    settings = _settings_with_lifecycle()
    filtered = anthropic_models_payload(
        settings, key_patterns=["llama*"], team_patterns=["llama*", "claude-*"]
    )
    ids = {c["id"] for c in filtered["data"]}
    assert "llama3.2:3b" in ids
    assert "claude-sonnet-5-5" not in ids


def test_lifecycle_composes_with_allowlist():
    settings = _settings_with_lifecycle()
    default = openai_models_payload(
        settings, key_patterns=["retired-model", "llama*"], team_patterns=None
    )
    default_ids = {c["id"] for c in default["data"]}
    assert "retired-model" not in default_ids
    assert "llama3.2:3b" in default_ids

    retired = openai_models_payload(
        settings,
        lifecycle="retired",
        key_patterns=["retired-model", "llama*"],
        team_patterns=None,
    )
    assert {c["id"] for c in retired["data"]} == {"retired-model"}


def test_unset_patterns_leave_payload_unfiltered():
    settings = _settings_with_lifecycle()
    assert openai_models_payload(settings) == openai_models_payload(
        settings, key_patterns=None, team_patterns=None
    )


@pytest.mark.asyncio
async def test_http_models_filtered_for_vk_full_for_master(tmp_path):
    settings = _settings_with_lifecycle()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["claude-*"], model_groups=["anthropic"])
    open_key = store.create("open")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        master = await client.get("/v1/models", headers={"Authorization": "Bearer master"})
        assert master.status_code == 200
        master_ids = {c["id"] for c in master.json()["data"]}
        assert "llama3.2:3b" in master_ids
        assert "claude-sonnet-5-5" in master_ids

        locked_list = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
        assert locked_list.status_code == 200
        locked_ids = {c["id"] for c in locked_list.json()["data"]}
        assert "claude-sonnet-5-5" in locked_ids
        assert "llama3.2:3b" not in locked_ids
        assert "daari" not in locked_ids

        anthropic_list = await client.get(
            "/v1/models",
            headers={
                "Authorization": f"Bearer {locked.plaintext}",
                "anthropic-version": "2023-06-01",
            },
        )
        assert anthropic_list.status_code == 200
        anth_ids = {c["id"] for c in anthropic_list.json()["data"]}
        assert "claude-sonnet-5-5" in anth_ids
        assert "llama3.2:3b" not in anth_ids

        open_list = await client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {open_key.plaintext}"},
        )
        assert open_list.status_code == 200
        assert {c["id"] for c in open_list.json()["data"]} == master_ids

        denied = await client.get(
            "/v1/models/llama3.2:3b",
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
        assert denied.status_code == 404

        allowed = await client.get(
            "/v1/models/claude-sonnet-5-5",
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["id"] == "claude-sonnet-5-5"

        anth_denied = await client.get(
            "/v1/models/llama3.2:3b",
            headers={
                "Authorization": f"Bearer {locked.plaintext}",
                "anthropic-version": "2023-06-01",
            },
        )
        assert anth_denied.status_code == 404

        master_retrieve = await client.get(
            "/v1/models/llama3.2:3b",
            headers={"Authorization": "Bearer master"},
        )
        assert master_retrieve.status_code == 200
