"""SEP-2640 skills/list + skill:// resources over POST /mcp (#1965)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp import INVALID_PARAMS
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _rpc(client: AsyncClient, method: str, params: dict | None = None, *, rpc_id: int = 1):
    body: dict = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=META_HEADERS)


def _seed_skills(tmp_path, monkeypatch):
    skills = tmp_path / ".daari" / "skills"
    skills.mkdir(parents=True)
    (skills / "flat-policy.md").write_text(
        "---\ndescription: Prefer local models\n---\n# Flat policy\nAlways prefer local.\n",
        encoding="utf-8",
    )
    pack = skills / "aaif-pack"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        "# AAIF pack\nPackage skill body.\n",
        encoding="utf-8",
    )
    nested = pack / "nested"
    nested.mkdir()
    (nested / "SKILL.md").write_text("Deep ignored.\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.mark.asyncio
async def test_skills_list_and_resources_include_flat_and_aaif(settings, tmp_path, monkeypatch):
    _seed_skills(tmp_path, monkeypatch)
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await _rpc(client, "skills/list")
        resources = await _rpc(client, "resources/list", rpc_id=2)
        got_flat = await _rpc(client, "skills/get", {"name": "flat-policy"}, rpc_id=3)
        read_aaif = await _rpc(
            client, "resources/read", {"uri": "skill://aaif-pack"}, rpc_id=4
        )
        missing = await _rpc(client, "skills/get", {"name": "nope"}, rpc_id=5)
        bad_uri = await _rpc(
            client, "resources/read", {"uri": "skill://missing"}, rpc_id=6
        )

    assert listed.status_code == 200
    skills = {s["id"]: s for s in listed.json()["result"]["skills"]}
    assert set(skills) == {"flat-policy", "aaif-pack"}
    assert skills["flat-policy"]["description"] == "Prefer local models"
    assert skills["flat-policy"]["uri"] == "skill://flat-policy"
    assert skills["aaif-pack"]["description"] == "AAIF pack"
    assert skills["aaif-pack"]["uri"] == "skill://aaif-pack"

    assert resources.status_code == 200
    uris = {r["uri"] for r in resources.json()["result"]["resources"]}
    assert uris == {"skill://flat-policy", "skill://aaif-pack"}
    assert all(r["mimeType"] == "text/markdown" for r in resources.json()["result"]["resources"])

    flat_body = got_flat.json()["result"]["skill"]["text"]
    assert "Always prefer local." in flat_body
    assert read_aaif.json()["result"]["contents"][0]["text"].startswith("# AAIF pack")

    assert missing.json()["error"]["code"] == INVALID_PARAMS
    assert "Unknown skill" in missing.json()["error"]["message"]
    assert bad_uri.json()["error"]["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_resources_list_empty_without_skills_dir(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resources = await _rpc(client, "resources/list")
        skills = await _rpc(client, "skills/list", rpc_id=2)
    assert resources.json()["result"]["resources"] == []
    assert skills.json()["result"]["skills"] == []
