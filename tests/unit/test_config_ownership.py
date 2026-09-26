"""Config editor live-vs-file ownership honesty (#1111)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from daari.config.ownership import (
    EPHEMERAL_WARNING,
    live_config_payload,
    ownership_fields,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def test_ownership_fields_default_vs_file_vs_runtime():
    live = {
        "routing": {
            "prefer": "balanced",
            "confidence_threshold": 0.55,
            "latency_budget_ms": 2000,
            "max_tier_for_chat": "L6",
        },
        "frontier": {
            "daily_budget_usd": 1.0,
            "monthly_budget_usd": 10.0,
            "soft_budget_ratio": 0.8,
        },
        "cache": {
            "l0_ttl_seconds": 60,
            "l1_ttl_seconds": 3600,
            "l1_similarity_threshold": 0.9,
        },
        "boundaries": {
            "enabled": False,
            "mode": "observe",
            "product_name": "",
            "product_description": "",
            "allow_topics": [],
            "deny_topics": [],
            "examples_in": [],
            "examples_out": [],
            "refuse_message": "",
            "clear_out_threshold": 0.0,
            "clear_in_threshold": 0.0,
            "stages_b0": True,
            "stages_b1": True,
            "stages_b2": True,
            "stages_b3": True,
        },
    }
    file_doc = {"routing": {"confidence_threshold": 0.7}}
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={"routing.confidence_threshold"},
    )
    assert meta["routing.confidence_threshold"]["source"] == "runtime"
    assert meta["routing.confidence_threshold"]["diverged"] is True
    assert meta["routing.confidence_threshold"]["file_value"] == 0.7
    assert meta["routing.prefer"]["source"] == "default"
    assert meta["routing.prefer"]["editable"] is True


@pytest.mark.asyncio
async def test_get_includes_ownership_and_patch_warns_without_persist(settings, tmp_path, monkeypatch):
    settings.observability.config_editor = True
    settings.routing.confidence_threshold = 0.7
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"routing": {"confidence_threshold": 0.7}}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    # ownership reads ~/.daari/config.yaml under HOME
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"routing": {"confidence_threshold": 0.7}}),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        assert "ownership" in body
        assert body["ownership"]["routing.confidence_threshold"]["source"] == "file"
        assert body["ownership"]["routing.confidence_threshold"]["editable"] is True

        patched = await client.patch(
            "/v1/daari/config",
            json={"routing": {"confidence_threshold": 0.55}},
        )
        assert patched.status_code == 200
        assert patched.json()["warning"] == EPHEMERAL_WARNING
        own = patched.json()["ownership"]["routing.confidence_threshold"]
        assert own["source"] == "runtime"
        assert own["diverged"] is True
        assert own["file_value"] == 0.7

        persisted = await client.patch(
            "/v1/daari/config",
            json={"routing": {"confidence_threshold": 0.4}, "persist": True},
        )
        assert persisted.status_code == 200
        assert "persisted_to" in persisted.json()
        assert "warning" not in persisted.json()
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["confidence_threshold"] == 0.4


def test_live_config_payload_matches_editor_shape(settings):
    payload = live_config_payload(settings)
    assert set(payload) >= {"routing", "frontier", "cache", "boundaries"}
    assert "confidence_threshold" in payload["routing"]
