from daari.gateway.cost_tier import apply_cost_tier, extract_cost_tier
from daari.gateway.internal import RequestMeta
from daari.gateway.openai import ChatCompletionRequest


def _body(**kwargs) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="daari", messages=[], **kwargs)


def test_maps_openrouter_aliases():
    assert extract_cost_tier(_body(cost_tier="low")) == "low"
    for raw, expected in (
        ("LOW", "L3"),
        ("medium", "L4"),
        ("high", "L5"),
        ("xhigh", "L6"),
        ("max", "L6"),
    ):
        meta = RequestMeta()
        assert apply_cost_tier(_body(cost_tier=raw), meta) == expected
        assert meta.tier_cap == expected


def test_plugins_auto_router_cost_tier():
    body = _body(plugins=[{"id": "auto-router", "cost_tier": "low"}])
    meta = RequestMeta()
    assert apply_cost_tier(body, meta) == "L3"
    assert meta.tier_cap == "L3"


def test_header_wins_over_body():
    meta = RequestMeta(tier_cap="L3")
    assert apply_cost_tier(_body(cost_tier="max"), meta) == "L6"
    assert meta.tier_cap == "L3"


def test_unknown_cost_tier_ignored(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.cost_tier.log_gateway_event",
        lambda event, payload: events.append(event),
    )
    meta = RequestMeta()
    assert apply_cost_tier(_body(cost_tier="enterprise"), meta) is None
    assert meta.tier_cap is None
    assert "cost_tier_ignored" in events
