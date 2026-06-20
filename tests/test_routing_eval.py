"""Routing eval GP-01–GP-20 from evals/routing/prompts.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app

EVALS_PATH = Path(__file__).resolve().parent.parent / "evals" / "routing" / "prompts.jsonl"


def load_routing_evals() -> list[dict]:
    rows: list[dict] = []
    with EVALS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@pytest.fixture
def eval_settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
        }
    )


@pytest.fixture
def eval_app(eval_settings):
    application = create_app(eval_settings)
    application.state.ctx = AppContext.from_settings(eval_settings)
    return application


@pytest.mark.asyncio
async def test_routing_eval_gp01_gp20(eval_app, monkeypatch):
    """Run GP-01–GP-20 in order; assert current tier expectations."""

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        last = request.messages[-1].content or ""
        return InternalResponse(
            content=f"mock:{last[:40]}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    monkeypatch.setattr(eval_app.state.ctx.router.ollama, "execute", fake_execute)

    evals = load_routing_evals()
    assert len(evals) == 20
    assert [row["id"] for row in evals] == [f"GP-{i:02d}" for i in range(1, 21)]

    transport = ASGITransport(app=eval_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for row in evals:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "llama3.2:3b",
                    "messages": [{"role": "user", "content": row["prompt"]}],
                },
            )
            assert response.status_code == 200, f"{row['id']} returned {response.status_code}"
            tier = response.json()["daari_meta"]["tier"]
            expected = row.get("expected_tier_v1") or row["expected_tier_mvp"]
            allowed = [value.strip() for value in str(expected).split("/")]
            if "L6" in allowed:
                allowed.extend(["L3", "L4"])
            if "L5" in allowed:
                allowed.extend(["L3", "L4"])
            if "Lt" in allowed:
                allowed.append("CCS")
            assert tier in allowed, f"{row['id']}: expected one of {allowed}, got {tier}"


@pytest.mark.asyncio
async def test_gp01_repeat_hits_l0(eval_app, monkeypatch):
    """MVP criteria: repeating GP-01 prompt hits L0."""

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="mock",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    monkeypatch.setattr(eval_app.state.ctx.router.ollama, "execute", fake_execute)
    gp01 = load_routing_evals()[0]
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": gp01["prompt"]}],
    }

    transport = ASGITransport(app=eval_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)
        assert first.json()["daari_meta"]["tier"] == "L3"
        assert second.json()["daari_meta"]["tier"] == "L0"
        assert second.json()["daari_meta"]["cache_hit"] is True
