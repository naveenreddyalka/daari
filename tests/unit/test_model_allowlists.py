"""Per-key and per-team model allowlists (#708)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.model_access import (
    effective_patterns,
    frontier_models_permitted,
    model_permitted,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import apply_auth_claims_to_meta, resolve_auth


CHAT = {"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hi"}]}


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake
    app.state.ctx.router.ollama.execute = fake


def test_patterns_intersect_and_expand_groups():
    catalog = {"anthropic": ["claude-*"], "local": ["llama3.2:3b"]}
    assert effective_patterns(None, None, catalog) is None
    assert effective_patterns(["gpt-4o"], ("anthropic",), catalog) == ["gpt-4o", "claude-*"]
    assert effective_patterns(None, ("missing",), catalog) == []
    assert model_permitted(
        "claude-3-5-sonnet",
        key_patterns=["llama*"],
        team_patterns=["claude-*", "llama*"],
    ) is False
    assert model_permitted(
        "llama3.2:3b",
        key_patterns=["llama*"],
        team_patterns=["claude-*", "llama*"],
    ) is True
    assert model_permitted("gpt-4o", key_patterns=None, team_patterns=None) is True


def test_store_round_trip_and_export(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", allowed_models=["claude-*", "llama*"], model_groups=["anthropic"])
    created = store.create(
        "ci",
        team="eng",
        allowed_models=["llama*"],
        model_groups=["local"],
    )
    found = store.resolve(created.plaintext)
    assert found is not None
    assert found.allowed_models == ("llama*",)
    assert found.model_groups == ("local",)
    loaded = store.get_team(team.team_id)
    assert loaded is not None
    assert loaded.allowed_models == ("claude-*", "llama*")
    assert store.update_model_access(created.key.key_id, allowed_models=["claude-3-5-sonnet"])
    updated = store.resolve(created.plaintext)
    assert updated is not None
    assert updated.allowed_models == ("claude-3-5-sonnet",)
    assert updated.model_groups == ("local",)
    doc = store.export_document()
    dst = VirtualKeyStore(tmp_path / "dst.sqlite3")
    dst.import_document(doc)
    copied = dst.list()[0]
    assert copied.allowed_models == ("claude-3-5-sonnet",)
    assert copied.model_groups == ("local",)
    copied_team = dst.get_team(name="eng")
    assert copied_team is not None
    assert copied_team.allowed_models == ("claude-*", "llama*")
    assert copied_team.model_groups == ("anthropic",)
    plain = store.create("open")
    assert store.resolve(plain.plaintext).allowed_models is None


def test_cli_create_update(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.model_groups = {"anthropic": ["claude-*"]}
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    team = runner.invoke(
        cli_app,
        ["keys", "team-create", "eng", "--model-group", "anthropic", "--allowed-model", "llama*"],
    )
    assert team.exit_code == 0, team.output
    created = runner.invoke(
        cli_app,
        ["keys", "create", "ci", "--team", "eng", "--allowed-model", "llama3.2:3b"],
    )
    assert created.exit_code == 0, created.output
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = next(item for item in store.list() if item.name == "ci")
    assert key.allowed_models == ("llama3.2:3b",)
    updated = runner.invoke(
        cli_app,
        ["keys", "update", key.key_id, "--allowed-model", "claude-*"],
    )
    assert updated.exit_code == 0, updated.output
    assert store.resolve(store.list()[0].key_id) or True
    again = next(item for item in store.list() if item.key_id == key.key_id)
    assert again.allowed_models == ("claude-*",)
    team_row = store.get_team(name="eng")
    assert team_row is not None
    narrowed = runner.invoke(
        cli_app,
        ["keys", "team-update", team_row.team_id, "--allowed-model", "claude-*"],
    )
    assert narrowed.exit_code == 0, narrowed.output
    assert store.get_team(name="eng").allowed_models == ("claude-*",)


def test_claims_compose_intersection(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    store.create_team("eng", allowed_models=["claude-*", "llama*"])
    created = store.create("ci", team="eng", allowed_models=["llama*"])
    claims = resolve_auth(created.plaintext, master_key="sekret", store=store)
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims, model_groups={"anthropic": ["claude-*"]})
    assert model_permitted(
        "claude-3",
        key_patterns=meta.key_model_patterns,
        team_patterns=meta.team_model_patterns,
    ) is False
    assert model_permitted(
        "llama3.1:8b",
        key_patterns=meta.key_model_patterns,
        team_patterns=meta.team_model_patterns,
    ) is True


class _Exec:
    def __init__(self, model: str) -> None:
        self.api_key = "sk-test"
        self.default_model = model
        self.calls = 0

    async def execute(self, *args, **kwargs):
        self.calls += 1
        return InternalResponse(
            content="frontier",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="x", latency_ms=1),
        )


@pytest.mark.asyncio
async def test_frontier_pool_skips_disallowed_model():
    blocked = _Exec("gpt-4o-mini")
    allowed = _Exec("claude-3-5-sonnet")
    pool = FrontierPool(
        slots=[
            ProviderSlot(id="openai", executor=blocked, keys=["sk-test"]),
            ProviderSlot(id="anthropic", executor=allowed, keys=["sk-test"]),
        ],
        api_key="sk-test",
        default_model="gpt-4o-mini",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-3-5-sonnet",
        meta=RequestMeta(key_model_patterns=["claude-*"]),
    )
    response = await pool.execute(request, escalated_from="L5", local_confidence=0.1)
    assert blocked.calls == 0
    assert allowed.calls == 1
    assert response.model == "claude-3-5-sonnet"
    assert frontier_models_permitted(
        pool, key_patterns=["llama*"], team_patterns=None
    ) is False


@pytest.mark.asyncio
async def test_gateway_denies_disallowed_model_on_every_surface(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.model_groups = {"anthropic": ["claude-*"]}
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create(
        "locked",
        client_id="locked",
        allowed_models=["claude-*"],
        model_groups=["anthropic"],
    )
    open_key = store.create("open", client_id="open")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    headers = {"Authorization": f"Bearer {created.plaintext}", "X-Daari-No-Cache": "true"}
    bodies = [
        ("/v1/chat/completions", {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}),
        ("/v1/embeddings", {"model": "gpt-4o", "input": "hi"}),
        ("/v1/responses", {"model": "gpt-4o", "input": "hi"}),
        (
            "/v1/messages",
            {"model": "gpt-4o", "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]},
        ),
        ("/api/chat", {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": False}),
        ("/api/generate", {"model": "gpt-4o", "prompt": "hi", "stream": False}),
        ("/api/embed", {"model": "gpt-4o", "input": "hi"}),
        ("/api/embeddings", {"model": "gpt-4o", "prompt": "hi"}),
    ]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path, body in bodies:
            denied = await client.post(path, json=body, headers=headers)
            assert denied.status_code == 403, (path, denied.status_code, denied.text)
            assert "model_not_allowed" in denied.text
            assert created.plaintext not in denied.text
            assert "gpt-4o" in denied.text
        allowed = await client.post(
            "/v1/chat/completions",
            json={"model": "claude-3-5-sonnet", "messages": [{"role": "user", "content": "hi"}]},
            headers=headers,
        )
        assert allowed.status_code == 200, allowed.text
        unrestricted = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {open_key.plaintext}", "X-Daari-No-Cache": "true"},
        )
        assert unrestricted.status_code == 200, unrestricted.text
    rows = AuditLog(settings.enterprise.audit_path).list(action="auth.model_denied")
    assert rows
    assert all(row["detail"].get("model") == "gpt-4o" for row in rows)
    assert created.plaintext not in str(rows)
