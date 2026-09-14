"""Region-pinned L6 frontier (#466)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.gateway.internal import DaariMeta, InternalRequest, Message, RequestMeta
from daari.gateway.provider_prefs import (
    RegionUnavailable,
    filter_slots_for_region,
    require_region_slot,
)
from daari.router.frontier_pool import ProviderSlot


class _Slot:
    def __init__(self, *, region: str = "", zdr: bool = False, id: str = "x") -> None:
        self.region = region
        self.zdr = zdr
        self.id = id


def test_require_region_slot_fails_closed():
    with pytest.raises(RegionUnavailable, match="eu"):
        require_region_slot("eu", [_Slot(region="us")])


def test_require_region_slot_ok_when_match():
    require_region_slot("eu", [_Slot(region="EU")])
    require_region_slot(None, [_Slot(region="")])
    require_region_slot("", [_Slot(region="us")])


def test_filter_slots_for_region():
    slots = [_Slot(region="us", id="a"), _Slot(region="eu", id="b"), _Slot(id="c")]
    assert [s.id for s in filter_slots_for_region("eu", slots)] == ["b"]
    assert len(filter_slots_for_region(None, slots)) == 3


@pytest.mark.asyncio
async def test_pool_raises_when_pin_unmatched(monkeypatch):
    from daari.router.frontier_pool import FrontierPool

    class FakeExec:
        api_key = "k"
        default_model = "m"

        async def execute(self, *args, **kwargs):
            raise AssertionError("must not execute")

    slot = ProviderSlot(id="us", executor=FakeExec(), keys=["sk"], region="us")
    pool = FrontierPool(
        slots=[slot],
        base_url="https://example",
        default_model="m",
        api_key="k",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        meta=RequestMeta(region_pin="eu"),
    )
    with pytest.raises(RegionUnavailable, match="eu"):
        await pool.execute(request, escalated_from="L5", local_confidence=0.1)


def test_keys_create_region_pin_round_trip(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created = runner.invoke(cli_app, ["keys", "create", "eu-key", "--region-pin", "eu"])
    assert created.exit_code == 0, created.output
    assert "region:" in created.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.list()[0]
    assert key.region_pin == "eu"
    assert store.to_dict(key)["region_pin"] == "eu"


def test_team_region_pin_inherited(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eu-team", region_pin="eu")
    assert team.region_pin == "eu"
    created = store.create("member", team="eu-team")
    # Key itself may be unpinned; auth inherits from team at resolve time.
    assert created.key.region_pin is None
    from daari.server.auth import resolve_auth

    claims = resolve_auth(created.plaintext, master_key="", store=store)
    assert claims is not None
    assert claims.region_pin == "eu"


def test_response_cost_headers_include_region():
    from daari.gateway.cost_headers import REGION_HEADER, response_cost_headers
    from daari.config.settings import Settings

    meta = DaariMeta(tier="L6", executor="frontier", region="eu")
    headers = response_cost_headers(meta, Settings())
    assert headers[REGION_HEADER] == "eu"
