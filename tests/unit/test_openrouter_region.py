"""OpenRouter us/eu regional host rewrite (#1052)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.gateway.provider_prefs import (
    RegionUnavailable,
    filter_slots_for_region,
    require_region_slot,
)
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.openrouter import (
    OPENROUTER_BASE_URL,
    openrouter_base_for_region,
    openrouter_can_satisfy_region,
)


def test_openrouter_base_for_region_rewrites_us_eu():
    assert (
        openrouter_base_for_region("us", OPENROUTER_BASE_URL)
        == "https://us.openrouter.ai/api/v1"
    )
    assert (
        openrouter_base_for_region("EU", "https://openrouter.ai/api/v1/")
        == "https://eu.openrouter.ai/api/v1"
    )
    assert openrouter_base_for_region("us", "https://api.openai.com/v1") == (
        "https://api.openai.com/v1"
    )
    assert openrouter_base_for_region(None, OPENROUTER_BASE_URL) == OPENROUTER_BASE_URL
    assert openrouter_base_for_region("ap", OPENROUTER_BASE_URL) == OPENROUTER_BASE_URL


def test_openrouter_can_satisfy_region():
    assert openrouter_can_satisfy_region("us", OPENROUTER_BASE_URL)
    assert openrouter_can_satisfy_region("eu", "https://us.openrouter.ai/api/v1")
    assert not openrouter_can_satisfy_region("us", "https://api.openai.com/v1")
    assert not openrouter_can_satisfy_region("ap", OPENROUTER_BASE_URL)


class _Exec:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.api_key = "k"
        self.default_model = "openrouter/auto"
        self.seen_bases: list[str] = []

    async def execute(self, *args, **kwargs):
        self.seen_bases.append(self.base_url)
        return InternalResponse(
            content="ok",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L6", executor="frontier"),
        )


def test_filter_keeps_global_openrouter_for_us_pin():
    exec_or = _Exec(OPENROUTER_BASE_URL)
    slots = [
        ProviderSlot(id="or", executor=exec_or, keys=["sk"], region=""),
        ProviderSlot(id="us-only", executor=_Exec("https://api.openai.com/v1"), keys=["sk"], region="us"),
    ]
    kept = filter_slots_for_region("eu", slots)
    assert [s.id for s in kept] == ["or"]
    require_region_slot("eu", slots)


def test_require_still_fails_without_openrouter_or_match():
    slots = [ProviderSlot(id="us", executor=_Exec("https://api.openai.com/v1"), keys=["sk"], region="us")]
    with pytest.raises(RegionUnavailable, match="eu"):
        require_region_slot("eu", slots)


@pytest.mark.asyncio
async def test_pool_rewrites_openrouter_base_for_region_pin():
    exec_or = _Exec(OPENROUTER_BASE_URL)
    pool = FrontierPool(
        slots=[ProviderSlot(id="openrouter", executor=exec_or, keys=["sk-test"], region="")],
        base_url=OPENROUTER_BASE_URL,
        default_model="openrouter/auto",
        api_key="sk-test",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        meta=RequestMeta(region_pin="us"),
    )
    response = await pool.execute(request, escalated_from="L5", local_confidence=0.1)
    assert exec_or.seen_bases == ["https://us.openrouter.ai/api/v1"]
    # Restored after the attempt so the next request can choose again.
    assert exec_or.base_url == OPENROUTER_BASE_URL
    assert response.daari_meta.region == "us"
