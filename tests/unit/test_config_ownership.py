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
_SIGNAL_OVERRIDES = "routing.signal_overrides"
_VIRTUAL_MODELS = "routing.virtual_models"
_VIRTUAL_MODEL_LATENCY_SLO = "routing.virtual_model_latency_slo_ms"
_MCP_LEAVES = (
    "integrations.mcp_oauth.local_as",
    "integrations.mcp_oauth.protected_resource",
    "integrations.mcp_aggregate_egress.enabled",
    "integrations.mcp_registry.enabled",
    "integrations.mcp_policy.require_key_access_defined",
    "integrations.mcp_servers",
)
_OBS_JSON_LOGS = "observability.structured_json_logs"
_OBS_TEAM_METRICS = "observability.team_metrics"
_OBS_OTEL_TAGS = "observability.otel_include_request_tags"
_SEC_OFFLINE_MODE = "security.offline_mode"
_SEC_OFFLINE_ALLOW_HOSTS = "security.offline_allow_hosts"


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
            "signal_overrides": [],
            "virtual_models": {},
            "virtual_model_latency_slo_ms": {},
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
            "mcp_servers": [],
        },
        "observability": {
            "structured_json_logs": False,
            "team_metrics": False,
            "otel_include_request_tags": False,
        },
        "security": {
            "offline_mode": False,
            "offline_allow_hosts": [],
        },
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


def test_ownership_fields_include_team_metrics():
    """observability.team_metrics is an ownership leaf (#2021)."""
    live = _base_live()
    live["observability"]["team_metrics"] = True
    file_doc = {"observability": {"team_metrics": False}}
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={_OBS_TEAM_METRICS},
    )
    assert _OBS_TEAM_METRICS in meta
    assert meta[_OBS_TEAM_METRICS]["editable"] is True
    assert meta[_OBS_TEAM_METRICS]["source"] == "runtime"
    assert meta[_OBS_TEAM_METRICS]["file_value"] is False


def test_ownership_fields_include_otel_include_request_tags():
    """observability.otel_include_request_tags is an ownership leaf (#2172)."""
    live = _base_live()
    live["observability"]["otel_include_request_tags"] = True
    file_doc = {"observability": {"otel_include_request_tags": False}}
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={_OBS_OTEL_TAGS},
    )
    assert _OBS_OTEL_TAGS in meta
    assert meta[_OBS_OTEL_TAGS]["editable"] is True
    assert meta[_OBS_OTEL_TAGS]["source"] == "runtime"
    assert meta[_OBS_OTEL_TAGS]["file_value"] is False


def test_ownership_fields_include_offline_mode():
    """security.offline_mode / offline_allow_hosts are ownership leaves (#2076)."""
    live = _base_live()
    live["security"]["offline_mode"] = True
    live["security"]["offline_allow_hosts"] = ["corp.example"]
    file_doc = {
        "security": {"offline_mode": False, "offline_allow_hosts": []},
    }
    meta = ownership_fields(
        live,
        file_doc=file_doc,
        runtime_overrides={_SEC_OFFLINE_MODE},
    )
    assert _SEC_OFFLINE_MODE in meta
    assert meta[_SEC_OFFLINE_MODE]["editable"] is True
    assert meta[_SEC_OFFLINE_MODE]["source"] == "runtime"
    assert meta[_SEC_OFFLINE_MODE]["file_value"] is False
    assert _SEC_OFFLINE_ALLOW_HOSTS in meta
    assert meta[_SEC_OFFLINE_ALLOW_HOSTS]["editable"] is True
    assert "at_rest_key" not in ".".join(meta)


def test_live_config_payload_matches_editor_shape(settings):
    payload = live_config_payload(settings)
    assert set(payload) >= {
        "routing",
        "frontier",
        "cache",
        "boundaries",
        "integrations",
        "observability",
        "security",
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
    assert payload["routing"]["signal_overrides"] == []
    assert set(payload["integrations"]["mcp_oauth"]) == {"local_as", "protected_resource"}
    assert "signing_secret" not in payload["integrations"]["mcp_oauth"]
    assert set(payload["integrations"]["mcp_policy"]) == {"require_key_access_defined"}
    assert payload["integrations"]["mcp_policy"]["require_key_access_defined"] is False
    assert payload["integrations"]["mcp_servers"] == []
    assert set(payload["observability"]) == {
        "structured_json_logs",
        "team_metrics",
        "otel_include_request_tags",
    }
    assert payload["observability"]["structured_json_logs"] is False
    assert payload["observability"]["team_metrics"] is False
    assert payload["observability"]["otel_include_request_tags"] is False
    assert set(payload["security"]) == {"offline_mode", "offline_allow_hosts"}
    assert payload["security"]["offline_mode"] is False
    assert payload["security"]["offline_allow_hosts"] == []
    assert "at_rest_key" not in payload["security"]


def test_live_config_payload_mcp_servers_ceilings_omit_secrets(settings):
    from daari.config.settings import McpServerSettings

    settings.integrations.mcp_servers = [
        McpServerSettings(
            id="tools",
            url="http://mcp.local/mcp",
            token="sekret",
            client_secret="also-secret",
            rpm=60,
            tpm=1000,
        )
    ]
    payload = live_config_payload(settings)
    assert payload["integrations"]["mcp_servers"] == [
        {"id": "tools", "rpm": 60, "tpm": 1000}
    ]


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


@pytest.mark.asyncio
async def test_patch_team_metrics_round_trip_and_metrics_label(
    settings, tmp_path, monkeypatch
):
    """PATCH observability.team_metrics toggles scrape team label (#2021)."""
    settings.observability.config_editor = True
    settings.observability.prometheus = True
    assert settings.observability.team_metrics is False
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"observability": {"team_metrics": False}}),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        assert _OBS_TEAM_METRICS in body["ownership"]
        assert body["ownership"][_OBS_TEAM_METRICS]["editable"] is True
        assert body["observability"]["team_metrics"] is False

        off_metrics = await client.get("/metrics")
        assert off_metrics.status_code == 200
        assert "daari_requests_total" in off_metrics.text
        assert 'team="' not in off_metrics.text

        bad = await client.patch(
            "/v1/daari/config",
            json={"observability": {"team_metrics": "yes"}},
        )
        assert bad.status_code == 400
        assert settings.observability.team_metrics is False

        on = await client.patch(
            "/v1/daari/config",
            json={"observability": {"team_metrics": True}, "persist": True},
        )
        assert on.status_code == 200
        payload = on.json()
        assert payload["observability"]["team_metrics"] is True
        assert payload["ownership"][_OBS_TEAM_METRICS]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["observability"]["team_metrics"] is True
        assert settings.observability.team_metrics is True

        on_metrics = await client.get("/metrics")
        assert on_metrics.status_code == 200
        assert 'team="-"' in on_metrics.text

        off = await client.patch(
            "/v1/daari/config",
            json={"observability": {"team_metrics": False}},
        )
        assert off.status_code == 200
        assert settings.observability.team_metrics is False
        restored = await client.get("/metrics")
        assert restored.status_code == 200
        assert 'team="' not in restored.text


@pytest.mark.asyncio
async def test_patch_otel_include_request_tags_round_trip_hot_apply(
    settings, tmp_path, monkeypatch
):
    """PATCH observability.otel_include_request_tags applies without restart (#2172)."""
    settings.observability.config_editor = True
    assert settings.observability.otel_include_request_tags is False
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"observability": {"otel_include_request_tags": False}}),
        encoding="utf-8",
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        assert _OBS_OTEL_TAGS in body["ownership"]
        assert body["ownership"][_OBS_OTEL_TAGS]["editable"] is True
        assert body["observability"]["otel_include_request_tags"] is False
        assert app.state.ctx.router.otel_include_request_tags is False

        bad = await client.patch(
            "/v1/daari/config",
            json={"observability": {"otel_include_request_tags": "yes"}},
        )
        assert bad.status_code == 400
        assert settings.observability.otel_include_request_tags is False
        assert app.state.ctx.router.otel_include_request_tags is False

        on = await client.patch(
            "/v1/daari/config",
            json={"observability": {"otel_include_request_tags": True}, "persist": True},
        )
        assert on.status_code == 200
        payload = on.json()
        assert payload["observability"]["otel_include_request_tags"] is True
        assert payload["ownership"][_OBS_OTEL_TAGS]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["observability"]["otel_include_request_tags"] is True
        assert settings.observability.otel_include_request_tags is True
        assert app.state.ctx.router.otel_include_request_tags is True

        off = await client.patch(
            "/v1/daari/config",
            json={"observability": {"otel_include_request_tags": False}},
        )
        assert off.status_code == 200
        assert settings.observability.otel_include_request_tags is False
        assert app.state.ctx.router.otel_include_request_tags is False


@pytest.mark.asyncio
async def test_patch_offline_mode_round_trip_and_egress_refusal(
    settings, tmp_path, monkeypatch
):
    """PATCH security.offline_mode arms air gap without restart (#2076)."""
    from daari.security.offline_mode import (
        OfflineEgressBlocked,
        assert_offline_url_allowed,
        configure_offline_mode,
        offline_mode_enabled,
    )

    settings.observability.config_editor = True
    assert settings.security.offline_mode is False
    configure_offline_mode(enabled=False, allow_hosts=())
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {"security": {"offline_mode": False, "offline_allow_hosts": []}}
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
        assert _SEC_OFFLINE_MODE in body["ownership"]
        assert body["ownership"][_SEC_OFFLINE_MODE]["editable"] is True
        assert _SEC_OFFLINE_ALLOW_HOSTS in body["ownership"]
        assert body["security"]["offline_mode"] is False
        assert "at_rest_key" not in body["security"]

        bad = await client.patch(
            "/v1/daari/config",
            json={"security": {"offline_mode": "yes"}},
        )
        assert bad.status_code == 400
        assert settings.security.offline_mode is False
        assert offline_mode_enabled() is False

        on = await client.patch(
            "/v1/daari/config",
            json={
                "security": {
                    "offline_mode": True,
                    "offline_allow_hosts": ["corp.example"],
                },
                "persist": True,
            },
        )
        assert on.status_code == 200
        payload = on.json()
        assert payload["security"]["offline_mode"] is True
        assert payload["security"]["offline_allow_hosts"] == ["corp.example"]
        assert payload["ownership"][_SEC_OFFLINE_MODE]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["security"]["offline_mode"] is True
        assert written["security"]["offline_allow_hosts"] == ["corp.example"]
        assert settings.security.offline_mode is True
        assert settings.security.offline_allow_hosts == ["corp.example"]
        assert offline_mode_enabled() is True
        with pytest.raises(OfflineEgressBlocked, match="offline_mode"):
            assert_offline_url_allowed(
                "https://api.openai.com/v1",
                resolver=lambda _h: ["93.184.216.34"],
            )
        assert_offline_url_allowed(
            "https://corp.example/v1",
            resolver=lambda _h: ["93.184.216.34"],
        )

        off = await client.patch(
            "/v1/daari/config",
            json={"security": {"offline_mode": False}},
        )
        assert off.status_code == 200
        assert settings.security.offline_mode is False
        assert offline_mode_enabled() is False
        assert_offline_url_allowed(
            "https://api.openai.com/v1",
            resolver=lambda _h: ["93.184.216.34"],
        )


@pytest.mark.asyncio
async def test_patch_mcp_server_ceilings_round_trip(settings, tmp_path, monkeypatch):
    from daari.config.settings import McpServerSettings

    settings.observability.config_editor = True
    settings.integrations.mcp_servers = [
        McpServerSettings(
            id="tools",
            url="http://mcp.local/mcp",
            token="keep-me",
            rpm=0,
            tpm=0,
        )
    ]
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "integrations": {
                    "mcp_servers": [
                        {
                            "id": "tools",
                            "url": "http://mcp.local/mcp",
                            "token": "keep-me",
                            "rpm": 0,
                            "tpm": 0,
                        }
                    ]
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
        assert "integrations.mcp_servers" in body["ownership"]
        assert body["integrations"]["mcp_servers"] == [
            {"id": "tools", "rpm": 0, "tpm": 0}
        ]
        assert "token" not in str(body["integrations"]["mcp_servers"])

        bad_secret = await client.patch(
            "/v1/daari/config",
            json={
                "integrations": {
                    "mcp_servers": [{"id": "tools", "rpm": 10, "token": "nope"}]
                }
            },
        )
        assert bad_secret.status_code == 400

        bad_neg = await client.patch(
            "/v1/daari/config",
            json={"integrations": {"mcp_servers": [{"id": "tools", "rpm": -1}]}},
        )
        assert bad_neg.status_code == 400
        assert settings.integrations.mcp_servers[0].rpm == 0

        persisted = await client.patch(
            "/v1/daari/config",
            json={
                "integrations": {
                    "mcp_servers": [{"id": "tools", "rpm": 60, "tpm": 5000}]
                },
                "persist": True,
            },
        )
        assert persisted.status_code == 200
        payload = persisted.json()
        assert payload["integrations"]["mcp_servers"] == [
            {"id": "tools", "rpm": 60, "tpm": 5000}
        ]
        assert settings.integrations.mcp_servers[0].rpm == 60
        assert settings.integrations.mcp_servers[0].tpm == 5000
        assert settings.integrations.mcp_servers[0].token == "keep-me"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        entry = written["integrations"]["mcp_servers"][0]
        assert entry["rpm"] == 60
        assert entry["tpm"] == 5000
        assert entry["url"] == "http://mcp.local/mcp"
        assert entry["token"] == "keep-me"


def test_docs_pin_classifier_mcp_config_ownership():
    config = CONFIG_MD.read_text(encoding="utf-8")
    http_api = HTTP_API.read_text(encoding="utf-8")
    for key in _CLASSIFIER_LEAVES + _MCP_LEAVES + _COMPACT_LEAVES + (
        _OBS_JSON_LOGS,
        _OBS_TEAM_METRICS,
        _OBS_OTEL_TAGS,
        _SIGNAL_OVERRIDES,
        _SEC_OFFLINE_MODE,
        _SEC_OFFLINE_ALLOW_HOSTS,
    ):
        assert key in config
    assert "config editor" in config.lower() or "/v1/daari/config" in config
    assert "| `GET` | `/v1/daari/config`" in http_api
    assert "| `PATCH` | `/v1/daari/config`" in http_api
    assert "decision_classifier" in http_api or "ownership" in http_api.lower()
    assert "compact_to_fit" in http_api
    assert "signal_overrides" in http_api
    assert "virtual_models" in http_api
    assert "virtual_model_latency_slo_ms" in http_api
    assert "require_key_access_defined" in http_api or "mcp_policy" in http_api
    assert "structured_json_logs" in http_api
    assert "team_metrics" in http_api
    assert "otel_include_request_tags" in http_api
    assert "offline_mode" in http_api
    assert "offline_allow_hosts" in http_api
    assert "mcp_servers" in http_api


@pytest.mark.asyncio
async def test_patch_signal_overrides_round_trip_invalid_and_forbidden(
    settings, tmp_path, monkeypatch
):
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.enterprise.postgres_audit import audit_log_from_settings

    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    assert settings.routing.signal_overrides == []
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"routing": {"signal_overrides": []}}),
        encoding="utf-8",
    )
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", daily_budget_usd=1.0)

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    headers_vk = {"Authorization": f"Bearer {created.plaintext}"}
    headers_master = {"Authorization": "Bearer master-sekret"}
    rule = {
        "id": "img-doc",
        "match": {"has_images": True},
        "category": "doc_qa",
        "max_tier": "L4",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config", headers=headers_master)
        assert got.status_code == 200
        body = got.json()
        assert _SIGNAL_OVERRIDES in body["ownership"]
        assert body["ownership"][_SIGNAL_OVERRIDES]["editable"] is True
        assert body["routing"]["signal_overrides"] == []

        denied = await client.patch(
            "/v1/daari/config",
            headers=headers_vk,
            json={"routing": {"signal_overrides": [rule]}},
        )
        assert denied.status_code == 403

        bad = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={
                "routing": {
                    "signal_overrides": [
                        {"id": "dead", "match": {"has_image": True}, "category": "doc_qa"}
                    ]
                }
            },
        )
        assert bad.status_code == 400
        assert settings.routing.signal_overrides == []
        assert app.state.ctx.router.signal_overrides == []

        patched = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"signal_overrides": [rule]}, "persist": True},
        )
        assert patched.status_code == 200
        payload = patched.json()
        assert payload["routing"]["signal_overrides"][0]["id"] == "img-doc"
        assert payload["ownership"][_SIGNAL_OVERRIDES]["source"] == "file"
        assert settings.routing.signal_overrides[0].id == "img-doc"
        assert app.state.ctx.router.signal_overrides[0].id == "img-doc"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["signal_overrides"][0]["id"] == "img-doc"
        audit = audit_log_from_settings(settings).list(limit=20)
        assert any(entry.get("action") == "config.patch" for entry in audit)


@pytest.mark.asyncio
async def test_patch_virtual_models_round_trip_invalid_and_live_reload(
    settings, tmp_path, monkeypatch
):
    """Ownership + PATCH for routing.virtual_models; router reloads without restart (#2051)."""
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse

    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    assert settings.routing.virtual_models == {}
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump({"routing": {"virtual_models": {}}}),
        encoding="utf-8",
    )
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", daily_budget_usd=1.0)

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def ok_l4(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-l4-after-patch",
            model=settings.models.l4,
            daari_meta=DaariMeta(tier="L4", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", ok_l4)

    transport = ASGITransport(app=app)
    headers_vk = {"Authorization": f"Bearer {created.plaintext}"}
    headers_master = {"Authorization": "Bearer master-sekret"}
    mapping = {"chat-default": ["L4"]}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config", headers=headers_master)
        assert got.status_code == 200
        body = got.json()
        assert _VIRTUAL_MODELS in body["ownership"]
        assert body["ownership"][_VIRTUAL_MODELS]["editable"] is True
        assert body["routing"]["virtual_models"] == {}

        denied = await client.patch(
            "/v1/daari/config",
            headers=headers_vk,
            json={"routing": {"virtual_models": mapping}},
        )
        assert denied.status_code == 403

        bad = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_models": {"bad": []}}},
        )
        assert bad.status_code == 400
        assert settings.routing.virtual_models == {}
        assert app.state.ctx.router.virtual_models == {}

        # Unknown-looking candidates are soft (accepted); empty lists are hard 400.
        soft = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_models": {"soft": ["mystery-model"]}}},
        )
        assert soft.status_code == 200
        assert settings.routing.virtual_models["soft"] == ["mystery-model"]

        patched = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_models": mapping}, "persist": True},
        )
        assert patched.status_code == 200
        payload = patched.json()
        assert payload["routing"]["virtual_models"] == mapping
        assert payload["ownership"][_VIRTUAL_MODELS]["source"] == "file"
        assert settings.routing.virtual_models == mapping
        assert app.state.ctx.router.virtual_models == mapping
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["virtual_models"] == mapping
        audit = audit_log_from_settings(settings).list(limit=20)
        assert any(entry.get("action") == "config.patch" for entry in audit)

        # Live reload: chat to the virtual name uses the patched candidate list.
        chat = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "route me"}],
            },
            headers={**headers_master, "X-Daari-Meta": "1"},
        )
        assert chat.status_code == 200
        meta = chat.json().get("daari_meta") or {}
        assert meta.get("virtual_model") == "chat-default"
        assert meta.get("virtual_candidate") == "L4"
        assert meta.get("tier") == "L4"


@pytest.mark.asyncio
async def test_patch_virtual_model_latency_slo_ms_ownership_and_live_reload(
    settings, tmp_path, monkeypatch
):
    """Ownership + PATCH for routing.virtual_model_latency_slo_ms (#2125)."""
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.enterprise.postgres_audit import audit_log_from_settings

    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.virtual_models = {"chat": ["L3", "L4"]}
    settings.routing.virtual_model_selection = "ordered"
    settings.routing.virtual_model_latency_slo_ms = {}
    monkeypatch.setenv("HOME", str(tmp_path))
    daari_dir = tmp_path / ".daari"
    daari_dir.mkdir()
    (daari_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "routing": {
                    "virtual_models": {"chat": ["L3", "L4"]},
                    "virtual_model_latency_slo_ms": {},
                }
            }
        ),
        encoding="utf-8",
    )
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", daily_budget_usd=1.0)

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    transport = ASGITransport(app=app)
    headers_vk = {"Authorization": f"Bearer {created.plaintext}"}
    headers_master = {"Authorization": "Bearer master-sekret"}
    slo_map = {"chat": 500.0}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config", headers=headers_master)
        assert got.status_code == 200
        body = got.json()
        assert _VIRTUAL_MODEL_LATENCY_SLO in body["ownership"]
        assert body["ownership"][_VIRTUAL_MODEL_LATENCY_SLO]["editable"] is True
        assert body["routing"]["virtual_model_latency_slo_ms"] == {}

        denied = await client.patch(
            "/v1/daari/config",
            headers=headers_vk,
            json={"routing": {"virtual_model_latency_slo_ms": slo_map}},
        )
        assert denied.status_code == 403

        unknown = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_model_latency_slo_ms": {"nope": 100.0}}},
        )
        assert unknown.status_code == 400
        detail = str(unknown.json().get("detail") or unknown.text).lower()
        assert "virtual_models" in detail or "no matching" in detail or "nope" in detail
        assert settings.routing.virtual_model_latency_slo_ms == {}
        assert app.state.ctx.router.virtual_model_latency_slo_ms == {}

        nonpos = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_model_latency_slo_ms": {"chat": 0}}},
        )
        assert nonpos.status_code == 400
        assert settings.routing.virtual_model_latency_slo_ms == {}

        patched = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_model_latency_slo_ms": slo_map}},
        )
        assert patched.status_code == 200
        payload = patched.json()
        assert payload["routing"]["virtual_model_latency_slo_ms"] == slo_map
        assert settings.routing.virtual_model_latency_slo_ms == slo_map
        assert app.state.ctx.router.virtual_model_latency_slo_ms == slo_map
        # Ordered mode still stores the map (selection ignores it).
        assert settings.routing.virtual_model_selection == "ordered"

        cleared = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"virtual_model_latency_slo_ms": {}}, "persist": True},
        )
        assert cleared.status_code == 200
        assert cleared.json()["routing"]["virtual_model_latency_slo_ms"] == {}
        assert settings.routing.virtual_model_latency_slo_ms == {}
        assert app.state.ctx.router.virtual_model_latency_slo_ms == {}
        assert cleared.json()["ownership"][_VIRTUAL_MODEL_LATENCY_SLO]["source"] == "file"
        written = yaml.safe_load((daari_dir / "config.yaml").read_text(encoding="utf-8"))
        assert written["routing"]["virtual_model_latency_slo_ms"] == {}
        audit = audit_log_from_settings(settings).list(limit=20)
        assert any(entry.get("action") == "config.patch" for entry in audit)


def test_ownership_fields_include_virtual_model_latency_slo_ms():
    """routing.virtual_model_latency_slo_ms is an ownership leaf (#2125)."""
    live = _base_live()
    live["routing"]["virtual_model_latency_slo_ms"] = {"chat": 250.0}
    meta = ownership_fields(
        live,
        file_doc={},
        runtime_overrides=set(),
    )
    assert _VIRTUAL_MODEL_LATENCY_SLO in meta
    assert meta[_VIRTUAL_MODEL_LATENCY_SLO]["editable"] is True
    assert meta[_VIRTUAL_MODEL_LATENCY_SLO]["source"] == "default"
