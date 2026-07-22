"""Per-project profiles: .daari.yaml + X-Daari-Project header (issue #91)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.project import (
    ProjectProfile,
    apply_profile_to_meta,
    find_project_file,
    load_project_profile,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, RequestMeta
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS

LONG_PROMPT = "please explain this " + "word " * 300  # >250 words -> L4 without a cap


# --- loader unit tests -------------------------------------------------------


def test_find_walks_up_to_repo_root(tmp_path):
    (tmp_path / ".daari.yaml").write_text("routing: {}\n")
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    assert find_project_file(nested) == tmp_path / ".daari.yaml"


def test_find_returns_none_without_file(tmp_path):
    assert find_project_file(tmp_path) is None


def test_load_parses_safe_subset(tmp_path):
    (tmp_path / ".daari.yaml").write_text(
        "routing:\n"
        "  max_tier_for_chat: l3\n"
        "  no_frontier: true\n"
        "  latency_budget_ms: 2500\n"
        "client_id: my-repo\n"
    )
    profile = load_project_profile(tmp_path)
    assert profile == ProjectProfile(
        tier_cap="L3",
        no_frontier=True,
        latency_budget_ms=2500,
        client_id="my-repo",
        source=str(tmp_path / ".daari.yaml"),
    )


def test_load_ignores_invalid_values(tmp_path):
    (tmp_path / ".daari.yaml").write_text(
        "routing:\n"
        "  max_tier_for_chat: L9\n"
        "  no_frontier: sometimes\n"
        "  latency_budget_ms: -5\n"
        "client_id: 42\n"
    )
    profile = load_project_profile(tmp_path)
    assert profile is not None
    assert profile.tier_cap is None
    assert profile.no_frontier is False
    assert profile.latency_budget_ms is None
    assert profile.client_id is None


def test_load_tolerates_malformed_yaml(tmp_path):
    (tmp_path / ".daari.yaml").write_text("routing: [unclosed\n")
    profile = load_project_profile(tmp_path)
    assert profile is not None
    assert profile.tier_cap is None


def test_load_tolerates_bad_path():
    assert load_project_profile("/definitely/not/a/real/path") is None
    assert load_project_profile("") is None
    assert load_project_profile(None) is None


def test_apply_fills_only_unset_fields():
    profile = ProjectProfile(
        tier_cap="L3", no_frontier=True, latency_budget_ms=2000, client_id="repo"
    )
    meta = RequestMeta(tier_cap="L5", client_id="header-client")
    apply_profile_to_meta(meta, profile)
    assert meta.tier_cap == "L5", "explicit header cap must win"
    assert meta.client_id == "header-client"
    assert meta.no_frontier is True
    assert meta.latency_budget_ms == 2000


def test_apply_with_none_profile_is_noop():
    meta = RequestMeta()
    apply_profile_to_meta(meta, None)
    assert meta.tier_cap is None and meta.no_frontier is False


# --- gateway integration -----------------------------------------------------


@pytest.fixture
def gateway(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _mock_tier_echo(monkeypatch, router) -> None:
    for attr, tier in (("ollama_l3", "L3"), ("ollama_l4", "L4"), ("ollama_l5", "L5")):
        executor = getattr(router, attr, None)
        if executor is None:
            continue

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(
                    tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        monkeypatch.setattr(executor, "execute", fake_execute)


@pytest.mark.asyncio
async def test_project_header_applies_tier_cap(gateway, monkeypatch, tmp_path):
    _mock_tier_echo(monkeypatch, gateway.state.ctx.router)
    repo = tmp_path / "capped-repo"
    repo.mkdir()
    (repo / ".daari.yaml").write_text("routing:\n  max_tier_for_chat: L3\n")

    payload = {"model": "daari", "messages": [{"role": "user", "content": LONG_PROMPT}]}
    transport = ASGITransport(app=gateway)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uncapped = await client.post("/v1/chat/completions", json=payload, headers=META_HEADERS)
        capped = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": LONG_PROMPT + " capped"}],
            },
            headers={**META_HEADERS, "X-Daari-Project": str(repo / "src")},
        )

    assert uncapped.json()["daari_meta"]["tier"] == "L4"
    assert capped.json()["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_explicit_header_beats_project_profile(gateway, monkeypatch, tmp_path):
    _mock_tier_echo(monkeypatch, gateway.state.ctx.router)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".daari.yaml").write_text("routing:\n  max_tier_for_chat: L3\n")

    payload = {"model": "daari", "messages": [{"role": "user", "content": LONG_PROMPT}]}
    transport = ASGITransport(app=gateway)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={**META_HEADERS, "X-Daari-Project": str(repo), "X-Daari-Tier-Cap": "L4"},
        )

    assert response.json()["daari_meta"]["tier"] == "L4"


@pytest.mark.asyncio
async def test_missing_profile_never_breaks_request(gateway, monkeypatch):
    _mock_tier_echo(monkeypatch, gateway.state.ctx.router)
    payload = {"model": "daari", "messages": [{"role": "user", "content": "hello profile"}]}
    transport = ASGITransport(app=gateway)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={**META_HEADERS, "X-Daari-Project": "/nope/never/exists"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_anthropic_gateway_applies_profile(gateway, monkeypatch, tmp_path):
    _mock_tier_echo(monkeypatch, gateway.state.ctx.router)
    repo = tmp_path / "claude-repo"
    repo.mkdir()
    (repo / ".daari.yaml").write_text("routing:\n  max_tier_for_chat: L3\nclient_id: claude-repo\n")

    seen: dict[str, object] = {}
    original = gateway.state.ctx.router.route

    async def spy_route(request: InternalRequest):
        seen["tier_cap"] = request.meta.tier_cap
        seen["client_id"] = request.meta.client_id
        return await original(request)

    monkeypatch.setattr(gateway.state.ctx.router, "route", spy_route)

    transport = ASGITransport(app=gateway)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi from claude"}],
            },
            headers={"X-Daari-Project": str(repo)},
        )

    assert response.status_code == 200
    assert seen["tier_cap"] == "L3"
    assert seen["client_id"] == "claude-repo"


# --- CLI ----------------------------------------------------------------------


def test_project_init_writes_template(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli_app, ["project", "init", str(tmp_path)])
    assert result.exit_code == 0
    content = (tmp_path / ".daari.yaml").read_text()
    assert "max_tier_for_chat" in content


def test_project_init_refuses_overwrite(tmp_path):
    (tmp_path / ".daari.yaml").write_text("client_id: keep\n")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["project", "init", str(tmp_path)])
    assert result.exit_code == 1
    assert (tmp_path / ".daari.yaml").read_text() == "client_id: keep\n"
    forced = runner.invoke(cli_app, ["project", "init", str(tmp_path), "--force"])
    assert forced.exit_code == 0


def test_project_show_reports_profile(tmp_path):
    (tmp_path / ".daari.yaml").write_text("routing:\n  no_frontier: true\n")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["project", "show", str(tmp_path)])
    assert result.exit_code == 0
    assert "no_frontier: True" in result.output
