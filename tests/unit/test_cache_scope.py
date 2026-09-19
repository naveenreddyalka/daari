"""Tenant cache_scope on virtual keys and teams (#768)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cache.exact import ExactCache, cache_key
from daari.cache.redis_exact import RedisExactCache
from daari.cache.semantic import SemanticCache, semantic_context_key
from daari.cli.app import app as cli_app
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.server.auth import apply_auth_claims_to_meta, introspect_token, resolve_auth


class _Embedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    async def embed(self, text: str) -> list[float] | None:
        return self.vectors.get(text)


def _request(
    content: str,
    *,
    scope: str = "global",
    team_id: str | None = None,
    key_id: str | None = None,
) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=content)],
        model="llama3.2:3b",
        meta=RequestMeta(cache_scope=scope, team_id=team_id, key_id=key_id),
    )


def _response(content: str) -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
    )


def test_global_scope_keeps_today_cache_keys():
    plain = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="llama3.2:3b",
    )
    attributed = _request("hi", scope="global", team_id="team-b", key_id="key-b")
    assert cache_key(plain) == cache_key(attributed)
    assert semantic_context_key(plain) == semantic_context_key(attributed)


def test_team_scope_folds_team_id_and_key_scope_folds_key_id():
    team_a = _request("hi", scope="team", team_id="team-a", key_id="key-1")
    team_a_other = _request("hi", scope="team", team_id="team-a", key_id="key-2")
    team_b = _request("hi", scope="team", team_id="team-b", key_id="key-3")
    key_a = _request("hi", scope="key", team_id="team-a", key_id="key-1")
    key_b = _request("hi", scope="key", team_id="team-a", key_id="key-2")
    assert cache_key(team_a) == cache_key(team_a_other)
    assert cache_key(team_a) != cache_key(team_b)
    assert cache_key(key_a) != cache_key(key_b)
    assert cache_key(team_a) != cache_key(_request("hi"))
    assert semantic_context_key(team_a) == semantic_context_key(team_a_other)
    assert semantic_context_key(team_a) != semantic_context_key(team_b)
    assert semantic_context_key(key_a) != semantic_context_key(key_b)


def test_l0_and_redis_do_not_cross_teams(tmp_path):
    disk = ExactCache(str(tmp_path / "l0"))
    client_data: dict[str, str] = {}

    class _Redis:
        def get(self, key: str):
            return client_data.get(key)

        def set(self, key: str, value: str, ex: int | None = None):
            client_data[key] = value

        def delete(self, key: str):
            client_data.pop(key, None)

    redis = RedisExactCache("redis://test", client=_Redis(), enabled=True)
    team_a = _request("same prompt", scope="team", team_id="team-a", key_id="k1")
    team_b = _request("same prompt", scope="team", team_id="team-b", key_id="k2")
    disk.put(team_a, _response("from-a"))
    redis.put(team_a, _response("from-a"))
    assert disk.get(team_b) is None
    assert redis.get(team_b) is None
    assert disk.get(team_a) is not None
    assert redis.get(team_a) is not None
    assert redis.get(team_a).content == "from-a"
    assert all(key.startswith("daari:l0:") for key in client_data)
    assert len(client_data) == 1


@pytest.mark.asyncio
async def test_l1_similar_prompts_do_not_cross_teams(tmp_path):
    original = "user:Write a commit message for this diff"
    paraphrase = "user:Please draft a commit message for the diff"
    cache = SemanticCache(
        str(tmp_path / "l1"),
        _Embedder({original: [1.0, 0.0, 0.0], paraphrase: [0.99, 0.01, 0.0]}),
        enabled=True,
        similarity_threshold=0.92,
    )
    stored = InternalRequest(
        messages=[Message(role="user", content="Write a commit message for this diff")],
        model="llama3.2:3b",
        meta=RequestMeta(cache_scope="team", team_id="team-a", key_id="k1"),
    )
    await cache.put(stored, _response("feat: add widget"))
    other_team = InternalRequest(
        messages=[Message(role="user", content="Please draft a commit message for the diff")],
        model="llama3.2:3b",
        meta=RequestMeta(cache_scope="team", team_id="team-b", key_id="k2"),
    )
    same_team = InternalRequest(
        messages=[Message(role="user", content="Please draft a commit message for the diff")],
        model="llama3.2:3b",
        meta=RequestMeta(cache_scope="team", team_id="team-a", key_id="k9"),
    )
    miss, _ = await cache.get(other_team)
    hit, score = await cache.get(same_team)
    assert miss is None
    assert hit is not None
    assert hit.content == "feat: add widget"
    assert score is not None and score >= 0.92


def test_scope_persists_and_auth_applies_it(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("secret", cache_scope="team")
    assert store.get_team(team.team_id).cache_scope == "team"
    left = store.create("left", team="secret", cache_scope="team")
    right = store.create("right", team="secret")
    assert store.resolve(left.plaintext).cache_scope == "team"
    assert store.list()[0].cache_scope in {"team", "global"}
    listed = {item.name: item for item in store.list()}
    assert listed["left"].cache_scope == "team"

    def meta_for(plaintext: str) -> RequestMeta:
        claims = resolve_auth(plaintext, master_key="master", store=store)
        meta = RequestMeta()
        apply_auth_claims_to_meta(meta, claims)
        return meta

    left_meta = meta_for(left.plaintext)
    right_meta = meta_for(right.plaintext)
    assert left_meta.cache_scope == "team"
    assert right_meta.cache_scope == "team"
    assert left_meta.team_id == right_meta.team_id == team.team_id
    same = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="llama3.2:3b",
        meta=left_meta,
    )
    also = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="llama3.2:3b",
        meta=right_meta,
    )
    assert cache_key(same) == cache_key(also)

    payload = introspect_token(left.plaintext, master_key="master", store=store)
    assert payload["cache_scope"] == "team"


def test_unauthenticated_dev_mode_stays_global():
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, resolve_auth("open", master_key=None, store=None))
    assert meta.cache_scope == "global"
    plain = InternalRequest(messages=[Message(role="user", content="hi")], model="m")
    open_req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="m",
        meta=meta,
    )
    assert cache_key(plain) == cache_key(open_req)


def test_invalid_cache_scope_rejected(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    with pytest.raises(ValueError, match="cache_scope"):
        store.create_team("eng", cache_scope="workspace")


def test_cli_list_surfaces_cache_scope(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    created = runner.invoke(
        cli_app, ["keys", "create", "isolated", "--cache-scope", "key"]
    )
    assert created.exit_code == 0, created.output
    assert "cache_scope: key" in created.output
    listed = runner.invoke(cli_app, ["keys", "list"])
    assert listed.exit_code == 0, listed.output
    assert "scope" in listed.output.splitlines()[0].split()
    assert "key" in listed.output
