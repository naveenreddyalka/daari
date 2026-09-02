"""G5: /v1/models cards include local + L6 capability tags."""

from daari.config.settings import Settings
from daari.router.capabilities import openai_model_cards


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
