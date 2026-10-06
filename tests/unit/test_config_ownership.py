"""Config editor live-vs-file ownership honesty (#1111, #1322)."""

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

ROOT = Path(__file__).resolve().parents[2]
CONFIG_MD = ROOT / "docs/developer/reference/config.md"
HTTP_API = ROOT / "docs/developer/reference/http-api.md"

_CLASSIFIER_LEAVES = (
    "routing.decision_classifier.enabled",
    "routing.decision_classifier.model",
    "routing.decision_classifier.timeout_seconds",
    "routing.decision_classifier.agent_turns",
)
_COMPACT_LEAVES = (
    "routing.compact_to_fit.enabled",
    "routing.compact_to_fit.max_messages",
    "routing.compact_to_fit.max_tokens",
)
_MCP_LEAVES = (
    "integrations.mcp_oauth.local_as",
    "integrations.mcp_oauth.protected_resource",
    "integrations.mcp_aggregate_egress.enabled",
    "integrations.mcp_registry.enabled",
    "integrations.mcp_policy.require_key_access_defined",
)
_OBS_JSON_LOGS = "observability.structured_json_logs"


def _base_live() -> dict:
    return {
        "routing": {
            "prefer": "balanced",
            "confidence_threshold": 0.55,
            "latency_budget_ms": 2000,
            "max_tier_for_chat": "L6",
            "decision_classifier": {
                "enabled": False,
                "model": "nimble",
                "timeout_seconds": 5.0,
                "agent_turns": False,
            },
            "compact_to_fit": {
                "enabled": False,
                "max_messages": 32,
                "max_tokens": 0,
            },
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
        "integrations": {
            "mcp_oauth": {"local_as": False, "protected_resource": False},
            "mcp_aggregate_egress": {"enabled": False},
            "mcp_registry": {"enabled": False},
            "mcp_policy": {"require_key_access_defined": False},
        },
        "observability": {"structured_json_logs": False},
    }


def test_ownership_fields_default_vs_file_vs_runtime():
    live = _base_live()
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


def test_ownership_fields_include_classifier_and_mcp_leaves():
    live = _base_live()
    live["routing"]["decision_classifier"]["enabled"] = True
    file_doc = {
        "routing": {"decision_classifier": {"enabled": False, "model": "nimble"}},
        "integrations": {"mcp_registry": {"enabled": True}},
    }
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={"routing.decision_classifier.enabled"},
    )
    for key in _CLASSIFIER_LEAVES + _MCP_LEAVES:
        assert key in meta
        assert meta[key]["editable"] is True
    assert meta["routing.decision_classifier.enabled"]["source"] == "runtime"
    assert meta["routing.decision_classifier.enabled"]["file_value"] is False
    assert meta["routing.decision_classifier.model"]["source"] == "file"
    assert meta["integrations.mcp_registry.enabled"]["source"] == "runtime"
    assert meta["integrations.mcp_registry.enabled"]["diverged"] is True
    assert meta["integrations.mcp_registry.enabled"]["file_value"] is True
    for secret in (
        "integrations.mcp_oauth.signing_secret",
        "signing_secret",
        "client_secret",
    ):
        assert secret not in meta


def test_ownership_fields_include_compact_to_fit_leaves():
    live = _base_live()
    live["routing"]["compact_to_fit"]["enabled"] = True
    live["routing"]["compact_to_fit"]["max_messages"] = 16
    file_doc = {
        "routing": {"compact_to_fit": {"enabled": False, "max_messages": 32, "max_tokens": 0}},
    }
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={"routing.compact_to_fit.enabled"},
    )
    for key in _COMPACT_LEAVES:
        assert key in meta
        assert meta[key]["editable"] is True
        assert meta[key]["source"] in {"file", "runtime", "default"}
    assert meta["routing.compact_to_fit.enabled"]["source"] == "runtime"
    assert meta["routing.compact_to_fit.enabled"]["file_value"] is False
    assert meta["routing.compact_to_fit.max_messages"]["source"] == "runtime"
    assert meta["routing.compact_to_fit.max_messages"]["file_value"] == 32
    assert meta["routing.compact_to_fit.max_tokens"]["source"] == "file"


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


@pytest.mark.asyncio
async def test_patch_classifier_and_mcp_knobs_round_trip(settings, tmp_path, monkeypatch):
    settings.observability.config_editor = True
    settings.routing.decision_classifier.enabled = False
    settings.integrations.mcp_oauth.local_as = False
    settings.integrations.mcp_oauth.signing_secret = "unit-secret-must-stay"
    settings.integrations.mcp_registry.enabled = False
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "routing": {"decision_classifier": {"enabled": False, "model": "nimble"}},
                "integrations": {
                    "mcp_oauth": {"local_as": False, "signing_secret": "file-secret"},
                    "mcp_registry": {"enabled": False},
                },
            }
        ),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        for key in _CLASSIFIER_LEAVES + _MCP_LEAVES:
            assert key in body["ownership"]
            assert body["ownership"][key]["editable"] is True
        assert "signing_secret" not in body.get("integrations", {}).get("mcp_oauth", {})
        assert "integrations.mcp_oauth.signing_secret" not in body["ownership"]

        bad = await client.patch(
            "/v1/daari/config",
            json={"integrations": {"mcp_oauth": {"signing_secret": "nope"}}},
        )
        assert bad.status_code == 400

        persisted = await client.patch(
            "/v1/daari/config",
            json={
                "routing": {
                    "decision_classifier": {
                        "enabled": True,
                        "model": "nimble",
                        "timeout_seconds": 3.5,
                        "agent_turns": True,
                    }
                },
                "integrations": {
                    "mcp_oauth": {"local_as": True, "protected_resource": True},
                    "mcp_aggregate_egress": {"enabled": True},
                    "mcp_registry": {"enabled": True},
                    "mcp_policy": {"require_key_access_defined": True},
                },
                "persist": True,
            },
        )
        assert persisted.status_code == 200
        payload = persisted.json()
        assert payload["routing"]["decision_classifier"]["enabled"] is True
        assert payload["routing"]["decision_classifier"]["timeout_seconds"] == 3.5
        assert payload["routing"]["decision_classifier"]["agent_turns"] is True
        assert payload["integrations"]["mcp_oauth"]["local_as"] is True
        assert payload["integrations"]["mcp_registry"]["enabled"] is True
        assert payload["integrations"]["mcp_policy"]["require_key_access_defined"] is True
        assert payload["ownership"]["routing.decision_classifier.enabled"]["source"] == "file"
        assert (
            payload["ownership"]["integrations.mcp_policy.require_key_access_defined"][
                "source"
            ]
            == "file"
        )
        assert "signing_secret" not in payload["integrations"]["mcp_oauth"]

        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["decision_classifier"]["enabled"] is True
        assert written["routing"]["decision_classifier"]["timeout_seconds"] == 3.5
        assert written["integrations"]["mcp_oauth"]["local_as"] is True
        assert written["integrations"]["mcp_oauth"]["signing_secret"] == "file-secret"
        assert written["integrations"]["mcp_registry"]["enabled"] is True
        assert written["integrations"]["mcp_aggregate_egress"]["enabled"] is True
        assert written["integrations"]["mcp_policy"]["require_key_access_defined"] is True
        assert settings.routing.decision_classifier.enabled is True
        assert settings.integrations.mcp_policy.require_key_access_defined is True
        assert settings.integrations.mcp_oauth.signing_secret == "unit-secret-must-stay"


@pytest.mark.asyncio
async def test_patch_compact_to_fit_round_trip(settings, tmp_path, monkeypatch):
    settings.observability.config_editor = True
    assert settings.routing.compact_to_fit.enabled is False
    assert settings.routing.compact_to_fit.max_messages == 32
    assert settings.routing.compact_to_fit.max_tokens == 0
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "routing": {
                    "compact_to_fit": {
                        "enabled": False,
                        "max_messages": 32,
                        "max_tokens": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        for key in _COMPACT_LEAVES:
            assert key in body["ownership"]
            assert body["ownership"][key]["editable"] is True
            assert body["ownership"][key]["source"] in {"file", "default"}
        assert body["routing"]["compact_to_fit"]["enabled"] is False

        bad_enabled = await client.patch(
            "/v1/daari/config",
            json={"routing": {"compact_to_fit": {"enabled": "yes"}}},
        )
        assert bad_enabled.status_code == 400
        bad_messages = await client.patch(
            "/v1/daari/config",
            json={"routing": {"compact_to_fit": {"max_messages": 0}}},
        )
        assert bad_messages.status_code == 400
        bad_tokens = await client.patch(
            "/v1/daari/config",
            json={"routing": {"compact_to_fit": {"max_tokens": -1}}},
        )
        assert bad_tokens.status_code == 400
        assert settings.routing.compact_to_fit.enabled is False

        persisted = await client.patch(
            "/v1/daari/config",
            json={
                "routing": {
                    "compact_to_fit": {
                        "enabled": True,
                        "max_messages": 16,
                        "max_tokens": 4096,
                    }
                },
                "persist": True,
            },
        )
        assert persisted.status_code == 200
        payload = persisted.json()
        assert payload["routing"]["compact_to_fit"] == {
            "enabled": True,
            "max_messages": 16,
            "max_tokens": 4096,
        }
        assert payload["ownership"]["routing.compact_to_fit.enabled"]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["compact_to_fit"]["enabled"] is True
        assert written["routing"]["compact_to_fit"]["max_messages"] == 16
        assert written["routing"]["compact_to_fit"]["max_tokens"] == 4096
        assert settings.routing.compact_to_fit.enabled is True
        assert settings.routing.compact_to_fit.max_messages == 16
        assert settings.routing.compact_to_fit.max_tokens == 4096
        assert app.state.ctx.router.compact_to_fit_enabled is True
        assert app.state.ctx.router.compact_to_fit_max_messages == 16
        assert app.state.ctx.router.compact_to_fit_max_tokens == 4096


def test_ownership_fields_include_structured_json_logs():
    live = _base_live()
    live["observability"]["structured_json_logs"] = True
    file_doc = {"observability": {"structured_json_logs": False}}
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={_OBS_JSON_LOGS},
    )
    assert _OBS_JSON_LOGS in meta
    assert meta[_OBS_JSON_LOGS]["editable"] is True
    assert meta[_OBS_JSON_LOGS]["source"] == "runtime"
    assert meta[_OBS_JSON_LOGS]["file_value"] is False


def test_live_config_payload_matches_editor_shape(settings):
    payload = live_config_payload(settings)
    assert set(payload) >= {
        "routing",
        "frontier",
        "cache",
        "boundaries",
        "integrations",
        "observability",
    }
    assert "confidence_threshold" in payload["routing"]
    assert set(payload["routing"]["decision_classifier"]) == {
        "enabled",
        "model",
        "timeout_seconds",
        "agent_turns",
    }
    assert set(payload["routing"]["compact_to_fit"]) == {
        "enabled",
        "max_messages",
        "max_tokens",
    }
    assert payload["routing"]["compact_to_fit"]["enabled"] is False
    assert payload["routing"]["compact_to_fit"]["max_messages"] == 32
    assert payload["routing"]["compact_to_fit"]["max_tokens"] == 0
    assert set(payload["integrations"]["mcp_oauth"]) == {"local_as", "protected_resource"}
    assert "signing_secret" not in payload["integrations"]["mcp_oauth"]
    assert set(payload["integrations"]["mcp_policy"]) == {"require_key_access_defined"}
    assert payload["integrations"]["mcp_policy"]["require_key_access_defined"] is False
    assert set(payload["observability"]) == {"structured_json_logs"}
    assert payload["observability"]["structured_json_logs"] is False


@pytest.mark.asyncio
async def test_patch_mcp_require_key_access_round_trip(settings, tmp_path, monkeypatch):
    settings.observability.config_editor = True
    assert settings.integrations.mcp_policy.require_key_access_defined is False
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {"integrations": {"mcp_policy": {"require_key_access_defined": False}}}
        ),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        key = "integrations.mcp_policy.require_key_access_defined"
        assert key in body["ownership"]
        assert body["ownership"][key]["editable"] is True
        assert body["integrations"]["mcp_policy"]["require_key_access_defined"] is False

        bad = await client.patch(
            "/v1/daari/config",
            json={"integrations": {"mcp_policy": {"require_key_access_defined": "yes"}}},
        )
        assert bad.status_code == 400
        assert settings.integrations.mcp_policy.require_key_access_defined is False

        persisted = await client.patch(
            "/v1/daari/config",
            json={
                "integrations": {"mcp_policy": {"require_key_access_defined": True}},
                "persist": True,
            },
        )
        assert persisted.status_code == 200
        payload = persisted.json()
        assert payload["integrations"]["mcp_policy"]["require_key_access_defined"] is True
        assert payload["ownership"][key]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["integrations"]["mcp_policy"]["require_key_access_defined"] is True
        assert settings.integrations.mcp_policy.require_key_access_defined is True


@pytest.mark.asyncio
async def test_patch_structured_json_logs_round_trip(settings, tmp_path, monkeypatch):
    from daari.gateway import request_log

    settings.observability.config_editor = True
    assert settings.observability.structured_json_logs is False
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"observability": {"structured_json_logs": False}}),
        encoding="utf-8",
    )
    previous_stdout = request_log._stdout_json
    try:
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            got = await client.get("/v1/daari/config")
            assert got.status_code == 200
            body = got.json()
            assert _OBS_JSON_LOGS in body["ownership"]
            assert body["ownership"][_OBS_JSON_LOGS]["editable"] is True
            assert body["observability"]["structured_json_logs"] is False

            bad = await client.patch(
                "/v1/daari/config",
                json={"observability": {"structured_json_logs": "yes"}},
            )
            assert bad.status_code == 400
            unknown = await client.patch(
                "/v1/daari/config",
                json={"observability": {"prometheus": True}},
            )
            assert unknown.status_code == 400
            assert settings.observability.structured_json_logs is False
            assert request_log._stdout_json is False

            persisted = await client.patch(
                "/v1/daari/config",
                json={
                    "observability": {"structured_json_logs": True},
                    "persist": True,
                },
            )
            assert persisted.status_code == 200
            payload = persisted.json()
            assert payload["observability"]["structured_json_logs"] is True
            assert payload["ownership"][_OBS_JSON_LOGS]["source"] == "file"
            written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
            assert written["observability"]["structured_json_logs"] is True
            assert settings.observability.structured_json_logs is True
            assert request_log._stdout_json is True
    finally:
        request_log.configure_request_log(structured_json_logs=previous_stdout)


def test_docs_pin_classifier_mcp_config_ownership():
    config = CONFIG_MD.read_text(encoding="utf-8")
    http_api = HTTP_API.read_text(encoding="utf-8")
    for key in _CLASSIFIER_LEAVES + _MCP_LEAVES + _COMPACT_LEAVES + (_OBS_JSON_LOGS,):
        assert key in config
    assert "config editor" in config.lower() or "/v1/daari/config" in config
    assert "| `GET` | `/v1/daari/config`" in http_api
    assert "| `PATCH` | `/v1/daari/config`" in http_api
    assert "decision_classifier" in http_api or "ownership" in http_api.lower()
    assert "compact_to_fit" in http_api
    assert "require_key_access_defined" in http_api or "mcp_policy" in http_api
    assert "structured_json_logs" in http_api
