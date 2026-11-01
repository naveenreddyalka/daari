"""Per-key / per-team signal_overrides binding (#2050)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import SignalOverrideRule
from daari.gateway.internal import ContentImage, InternalRequest, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.router.signals import (
    match_scoped_signal_override,
    merge_scoped_signal_overrides,
    signal_overrides_from_meta,
)


def _img_rule(rule_id: str = "key-img", *, category: str = "doc_qa") -> dict:
    return {
        "id": rule_id,
        "match": {"has_images": True},
        "category": category,
    }


def test_signal_overrides_from_meta_validates_and_rejects():
    rules = signal_overrides_from_meta({"signal_overrides": [_img_rule()]})
    assert len(rules) == 1
    assert rules[0].id == "key-img"

    with pytest.raises((ValidationError, ValueError), match=r"unknown match key|has_image"):
        signal_overrides_from_meta(
            {"signal_overrides": [{"id": "bad", "match": {"has_image": True}, "category": "doc_qa"}]}
        )


def test_merge_precedence_key_beats_team_beats_global():
    key = [SignalOverrideRule.model_validate(_img_rule("key-rule", category="doc_qa"))]
    team = [
        SignalOverrideRule(
            id="team-rule", match={"has_images": True}, category="code_gen"
        )
    ]
    global_rules = [
        SignalOverrideRule(
            id="global-rule", match={"has_images": True}, max_tier="L3"
        )
    ]
    merged = merge_scoped_signal_overrides(
        key_rules=key, team_rules=team, global_rules=global_rules
    )
    assert [scope for _, scope in merged] == ["key", "team", "global"]
    signals = {"has_images": True}
    matched, scope = match_scoped_signal_override(signals, merged)
    assert matched is not None
    assert matched.id == "key-rule"
    assert scope == "key"

    matched, scope = match_scoped_signal_override(
        signals,
        merge_scoped_signal_overrides(key_rules=[], team_rules=team, global_rules=global_rules),
    )
    assert matched.id == "team-rule"
    assert scope == "team"

    matched, scope = match_scoped_signal_override(
        signals,
        merge_scoped_signal_overrides(key_rules=[], team_rules=[], global_rules=global_rules),
    )
    assert matched.id == "global-rule"
    assert scope == "global"


def test_store_persists_key_and_team_signal_overrides(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("alpha", signal_overrides=[_img_rule("team-img")])
    assert len(team.signal_overrides) == 1
    assert team.signal_overrides[0].id == "team-img"

    created = store.create(
        "agent",
        team="alpha",
        signal_overrides=[_img_rule("key-img", category="code_gen")],
    )
    assert created.key.signal_overrides[0].id == "key-img"

    reloaded = store.get_key(created.key.key_id) if hasattr(store, "get_key") else None
    if reloaded is None:
        reloaded = next(k for k in store.list() if k.key_id == created.key.key_id)
    assert reloaded.signal_overrides[0].category == "code_gen"

    team2 = store.get_team(team.team_id)
    assert team2 is not None
    assert team2.signal_overrides[0].id == "team-img"

    with pytest.raises((ValidationError, ValueError)):
        store.create("bad", signal_overrides=[{"id": "x", "match": {}, "category": "doc_qa"}])


def test_store_update_signal_overrides_rejects_bad_rules(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("k1")
    with pytest.raises((ValidationError, ValueError)):
        store.update_signal_overrides(
            created.key.key_id,
            [{"id": "no-lever", "match": {"has_images": True}}],
        )
    ok = store.update_signal_overrides(created.key.key_id, [_img_rule("updated")])
    assert ok is True
    key = next(k for k in store.list() if k.key_id == created.key.key_id)
    assert key.signal_overrides[0].id == "updated"

    team = store.create_team("t1")
    with pytest.raises((ValidationError, ValueError)):
        store.update_team_signal_overrides(
            team.team_id,
            [{"id": "typo", "match": {"has_image": True}, "max_tier": "L4"}],
        )
    store.update_team_signal_overrides(team.team_id, [_img_rule("team-u")])
    assert store.get_team(team.team_id).signal_overrides[0].id == "team-u"


@pytest.mark.asyncio
async def test_router_key_scoped_rule_wins_over_global(tmp_path, monkeypatch):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalResponse
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(
                    tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    metrics = Metrics()
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=metrics,
        signal_overrides=[
            SignalOverrideRule(
                id="global-img",
                match={"has_images": True},
                category="doc_qa",
            )
        ],
    )
    request = InternalRequest(
        messages=[
            Message(
                role="user",
                content="describe this",
                images=[ContentImage(data="AAAA", media_type="image/png")],
            )
        ],
        model="daari",
        meta=RequestMeta(
            key_id="k1",
            key_signal_overrides=[
                SignalOverrideRule(
                    id="key-img",
                    match={"has_images": True},
                    category="code_gen",
                )
            ],
        ),
    )
    response = await router.route(request)
    assert response.daari_meta.task_type == "code_gen"
    snap = metrics.snapshot(include_histograms=True)
    so = snap.get("signal_override") or {}
    assert so.get("key-img:key", 0) >= 1 or any(
        str(k).startswith("key-img") and so[k] >= 1 for k in so
    )
    override_events = [p for e, p in events if e == "signal_override"]
    assert override_events
    assert override_events[0].get("scope") == "key"
    signals_events = [p for e, p in events if e == "signals"]
    assert signals_events
    assert signals_events[0].get("scope") in (None, "key") or "scope" in override_events[0]


def test_apply_auth_claims_stamps_key_and_team_overrides(tmp_path):
    from daari.server.auth import AuthClaims, apply_auth_claims_to_meta

    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("t", signal_overrides=[_img_rule("team-r")])
    created = store.create(
        "k",
        team="t",
        signal_overrides=[_img_rule("key-r", category="code_gen")],
    )
    claims = AuthClaims(
        kind="virtual",
        key_id=created.key.key_id,
        client_id=created.key.key_id,
        virtual_key=created.key,
        team_signal_overrides=list(team.signal_overrides),
    )
    # Prefer stamping from the key object when claims omit explicit lists.
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims)
    assert meta.key_id == created.key.key_id
    assert meta.key_signal_overrides
    assert meta.key_signal_overrides[0].id == "key-r"
    assert meta.team_signal_overrides
    assert meta.team_signal_overrides[0].id == "team-r"


def test_admin_inventory_includes_signal_overrides(tmp_path):
    from daari.gateway.admin_read import redact_key, redact_team

    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("inv", signal_overrides=[_img_rule("t")])
    created = store.create("inv-k", team="inv", signal_overrides=[_img_rule("k")])
    key_row = redact_key(created.key)
    team_row = redact_team(team)
    assert key_row["signal_overrides"][0]["id"] == "k"
    assert team_row["signal_overrides"][0]["id"] == "t"


def test_cli_keys_update_signal_override(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("cli-k")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    rule = json.dumps(_img_rule("cli-rule"))
    result = CliRunner().invoke(
        cli_app,
        ["keys", "update", created.key.key_id, "--signal-override", rule],
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")
    key = next(
        k for k in VirtualKeyStore(settings.virtual_keys_path).list() if k.key_id == created.key.key_id
    )
    assert key.signal_overrides[0].id == "cli-rule"
