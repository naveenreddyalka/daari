"""G5: /v1/models cards include local + L6 capability tags."""

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.gateway.decisions import BUILTIN_LOCAL_MODELS
from daari.router.capabilities import (
    anthropic_model_cards,
    openai_model_cards,
    openai_models_payload,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def test_openai_pool_slot_model_appears_with_capability_tags():
    settings = Settings.model_validate(
        {
            "models": {
                "capabilities": {
                    "meta-llama/Llama-3.1-8B": ["tools", "json", "long_context"],
                }
            },
            "routing": {
                "local_pool": {
                    "backends": [
                        {
                            "id": "vllm-a",
                            "kind": "openai",
                            "base_url": "http://127.0.0.1:8000",
                            "model": "meta-llama/Llama-3.1-8B",
                            "tiers": ["L4", "L5"],
                        }
                    ]
                }
            },
        }
    )
    cards = openai_model_cards(settings)
    card = next(item for item in cards if item["id"] == "meta-llama/Llama-3.1-8B")
    assert card["owned_by"] == "openai"
    assert "tools" in card["capabilities"]
    assert "json" in card["capabilities"]


def test_local_cards_include_capability_tags():
    settings = Settings()
    cards = openai_model_cards(settings)
    by_id = {card["id"]: card for card in cards}
    assert "daari" in by_id
    assert "tools" in by_id[settings.models.l3]["capabilities"]
    assert "long_context" in by_id[settings.models.l4]["capabilities"]
    assert "vision" in by_id[settings.models.l5]["capabilities"]


def test_l6_cards_include_known_frontier_capabilities():
    settings = Settings.model_validate(
        {
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "anthropic", "model": "claude-fable-5-1"},
                ],
            }
        }
    )
    cards = openai_model_cards(settings)
    card = next(item for item in cards if item["id"] == "claude-fable-5-1")
    assert {"tools", "json", "vision", "long_context"} <= set(card["capabilities"])


def test_l6_cards_include_zdr_when_configured():
    settings = Settings.model_validate(
        {
            "frontier": {
                "enabled": True,
                "providers": [
                    {
                        "id": "openrouter",
                        "model": "openrouter/auto",
                        "zdr": True,
                    }
                ],
            }
        }
    )
    cards = openai_model_cards(settings)
    l6 = next(card for card in cards if card["id"] == "openrouter/auto")
    assert "zdr" in l6["capabilities"]
    assert l6["owned_by"] == "openrouter"


def test_local_cards_include_context_length_from_routing():
    settings = Settings()
    cards = openai_model_cards(settings)
    by_id = {card["id"]: card for card in cards}
    assert by_id[settings.models.l3]["context_length"] == 8192
    assert by_id[settings.models.l4]["context_length"] == 32768
    assert by_id[settings.models.l5]["context_length"] == 131072
    assert by_id["daari"]["context_length"] == 131072


def test_unknown_context_window_is_omitted():
    settings = Settings.model_validate({"routing": {"context_windows": {"L4": 32768}}})
    cards = openai_model_cards(settings)
    by_id = {card["id"]: card for card in cards}
    assert "context_length" not in by_id[settings.models.l3]
    assert by_id[settings.models.l4]["context_length"] == 32768
    assert "context_length" not in by_id[settings.models.l5]


def test_frontier_cards_do_not_get_local_context_windows():
    settings = Settings.model_validate(
        {
            "frontier": {
                "enabled": True,
                "providers": [{"id": "anthropic", "model": "claude-fable-5-1"}],
            }
        }
    )
    cards = openai_model_cards(settings)
    card = next(item for item in cards if item["id"] == "claude-fable-5-1")
    assert "context_length" not in card


def test_decisions_catalog_on_models_when_systemone_enabled():
    settings = Settings.model_validate(
        {"decisions": {"local_models": ["my-judge"]}}
    )
    cards = openai_model_cards(settings)
    by_id = {card["id"]: card for card in cards}
    for model_id in BUILTIN_LOCAL_MODELS:
        assert model_id in by_id
        assert "decision" in by_id[model_id]["capabilities"]
    assert "my-judge" in by_id
    assert "decision" in by_id["my-judge"]["capabilities"]


def test_decisions_catalog_omitted_when_systemone_disabled():
    settings = Settings.model_validate({"systemone": {"enabled": False}})
    ids = {card["id"] for card in openai_model_cards(settings)}
    assert "nimble" not in ids
    assert "clef" not in ids


def test_decisions_catalog_respects_vk_allowlist():
    settings = Settings()
    filtered = openai_models_payload(settings, key_patterns=["nimble"], team_patterns=None)
    ids = {card["id"] for card in filtered["data"]}
    assert "nimble" in ids
    assert "clef" not in ids
    assert "daari" not in ids


def test_anthropic_decisions_catalog_includes_decision_capability():
    """Anthropic-shaped cards carry decision for local judges (#1658)."""
    settings = Settings.model_validate(
        {"decisions": {"local_models": ["my-judge"]}}
    )
    cards = anthropic_model_cards(settings)
    by_id = {card["id"]: card for card in cards}
    for model_id in (*BUILTIN_LOCAL_MODELS, "my-judge"):
        assert model_id in by_id
        caps = by_id[model_id]["capabilities"]
        assert caps.get("decision", {}).get("supported") is True
        # Non-decision Anthropic fields remain.
        assert "thinking" in caps
        assert "server_tools" in caps

    # Non-decision local card must not gain a decision flag.
    daari_caps = by_id["daari"]["capabilities"]
    assert "decision" not in daari_caps
    assert "thinking" in daari_caps
    assert "server_tools" in daari_caps


def test_anthropic_decisions_catalog_omitted_when_systemone_disabled():
    settings = Settings.model_validate({"systemone": {"enabled": False}})
    ids = {card["id"] for card in anthropic_model_cards(settings)}
    assert "nimble" not in ids
    assert "clef" not in ids


def test_anthropic_accept_path_lists_decision_capability():
    """GET /v1/models with Anthropic headers exposes decision (#1658)."""
    settings = Settings.model_validate(
        {"decisions": {"local_models": ["my-judge"]}}
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    client = TestClient(app)
    headers = {"anthropic-version": "2023-06-01"}
    listed = client.get("/v1/models", headers=headers)
    assert listed.status_code == 200
    by_id = {card["id"]: card for card in listed.json()["data"]}
    assert by_id["nimble"]["capabilities"]["decision"]["supported"] is True
    assert by_id["my-judge"]["capabilities"]["decision"]["supported"] is True
    assert "decision" not in by_id["daari"]["capabilities"]

    single = client.get("/v1/models/nimble", headers=headers)
    assert single.status_code == 200
    assert single.json()["capabilities"]["decision"]["supported"] is True
