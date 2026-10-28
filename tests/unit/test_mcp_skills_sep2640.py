"""SEP-2640 skills extension over POST /mcp (#1965, #1979)."""

from __future__ import annotations

import hashlib
import re

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp import INVALID_PARAMS
from daari.gateway.mcp_tasks import SKILLS_EXTENSION, initialize_capabilities
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
        "---\nname: aaif-pack\ndescription: AAIF pack\nlicense: Apache-2.0\n---\n"
        "# AAIF pack\nPackage skill body.\n",
        encoding="utf-8",
    )
    (pack / "references").mkdir()
    (pack / "references" / "GUIDE.md").write_text("Guide body.\n", encoding="utf-8")
    nested = pack / "nested"
    nested.mkdir()
    (nested / "SKILL.md").write_text("Deep ignored as skill.\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    return skills


def _sha256_hex(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def test_capabilities_advertise_skills_extension_on_2026_07_28():
    caps = initialize_capabilities("2026-07-28")
    assert SKILLS_EXTENSION in caps.get("extensions", {})
    assert "directoryRead" in caps["extensions"][SKILLS_EXTENSION]
    assert "resources" in caps


def test_capabilities_omit_skills_extension_on_older_protocol():
    caps = initialize_capabilities("2025-03-26")
    assert SKILLS_EXTENSION not in caps.get("extensions", {})


@pytest.mark.asyncio
async def test_initialize_and_discover_advertise_skills(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        init = await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        discover = await _rpc(
            client,
            "server/discover",
            {"protocolVersion": "2026-07-28"},
            rpc_id=2,
        )
    for response in (init, discover):
        caps = response.json()["result"]["capabilities"]
        assert SKILLS_EXTENSION in caps["extensions"]
        assert "directoryRead" in caps["extensions"][SKILLS_EXTENSION]


@pytest.mark.asyncio
async def test_skills_list_manifest_frontmatter_and_digests(settings, tmp_path, monkeypatch):
    skills_dir = _seed_skills(tmp_path, monkeypatch)
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await _rpc(client, "skills/list")
        resources = await _rpc(client, "resources/list", rpc_id=2)

    assert listed.status_code == 200
    result = listed.json()["result"]
    skills = {s["frontmatter"]["name"]: s for s in result["skills"]}
    assert set(skills) == {"flat-policy", "aaif-pack"}

    flat = skills["flat-policy"]
    assert flat["uri"] == "skill://flat-policy/SKILL.md"
    assert flat["frontmatter"]["description"] == "Prefer local models"
    assert flat["frontmatter"]["name"] == "flat-policy"
    flat_bytes = (skills_dir / "flat-policy.md").read_bytes()
    assert flat["resources"] == [
        {
            "uri": "skill://flat-policy/SKILL.md",
            "digest": _sha256_hex(flat_bytes),
            "size": len(flat_bytes),
        }
    ]

    pack = skills["aaif-pack"]
    assert pack["uri"] == "skill://aaif-pack/SKILL.md"
    assert pack["frontmatter"] == {
        "name": "aaif-pack",
        "description": "AAIF pack",
        "license": "Apache-2.0",
    }
    resource_uris = {r["uri"] for r in pack["resources"]}
    assert "skill://aaif-pack/SKILL.md" in resource_uris
    assert "skill://aaif-pack/references/GUIDE.md" in resource_uris
    assert "skill://aaif-pack/nested/SKILL.md" in resource_uris
    for entry in pack["resources"]:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", entry["digest"])
        assert isinstance(entry["size"], int) and entry["size"] > 0
    skill_md = (skills_dir / "aaif-pack" / "SKILL.md").read_bytes()
    skill_entry = next(r for r in pack["resources"] if r["uri"] == "skill://aaif-pack/SKILL.md")
    assert skill_entry["digest"] == _sha256_hex(skill_md)
    assert skill_entry["size"] == len(skill_md)

    assert resources.status_code == 200
    uris = {r["uri"] for r in resources.json()["result"]["resources"]}
    assert "skill://flat-policy/SKILL.md" in uris
    assert "skill://aaif-pack/SKILL.md" in uris
    assert "skill://aaif-pack/references/GUIDE.md" in uris


@pytest.mark.asyncio
async def test_skills_get_by_uri_matches_list_entry(settings, tmp_path, monkeypatch):
    _seed_skills(tmp_path, monkeypatch)
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await _rpc(client, "skills/list")
        got = await _rpc(
            client,
            "skills/get",
            {"uri": "skill://aaif-pack/SKILL.md"},
            rpc_id=2,
        )
        missing = await _rpc(
            client,
            "skills/get",
            {"uri": "skill://missing/SKILL.md"},
            rpc_id=3,
        )

    listed_entry = next(
        s for s in listed.json()["result"]["skills"] if s["uri"] == "skill://aaif-pack/SKILL.md"
    )
    assert got.status_code == 200
    body = got.json()["result"]
    assert body["skill"] == listed_entry
    assert missing.json()["error"]["code"] == INVALID_PARAMS
    assert "Unknown skill" in missing.json()["error"]["message"]


@pytest.mark.asyncio
async def test_resources_read_supporting_files(settings, tmp_path, monkeypatch):
    _seed_skills(tmp_path, monkeypatch)
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        read_skill = await _rpc(
            client, "resources/read", {"uri": "skill://aaif-pack/SKILL.md"}, rpc_id=1
        )
        read_guide = await _rpc(
            client,
            "resources/read",
            {"uri": "skill://aaif-pack/references/GUIDE.md"},
            rpc_id=2,
        )
        read_flat = await _rpc(
            client, "resources/read", {"uri": "skill://flat-policy/SKILL.md"}, rpc_id=3
        )
        bad = await _rpc(
            client, "resources/read", {"uri": "skill://aaif-pack/nope.md"}, rpc_id=4
        )

    assert "Package skill body." in read_skill.json()["result"]["contents"][0]["text"]
    assert read_guide.json()["result"]["contents"][0]["text"] == "Guide body.\n"
    assert "Always prefer local." in read_flat.json()["result"]["contents"][0]["text"]
    assert bad.json()["error"]["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_resources_list_empty_without_skills_dir(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resources = await _rpc(client, "resources/list")
        skills = await _rpc(client, "skills/list", rpc_id=2)
    assert resources.json()["result"]["resources"] == []
    assert skills.json()["result"]["skills"] == []
