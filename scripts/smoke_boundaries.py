#!/usr/bin/env python3
"""Live/smoke verification for product boundaries (issue #145 / F6) — pass 3/3.

In-process ASGI (no Ollama required):
1) block mode: out-of-scope → tier=boundary, model never called
2) in-scope → model path
3) warn mode: out-of-scope still answers with daari_meta.boundary
4) config PATCH rebuilds engine mid-flight

Usage:
  python scripts/smoke_boundaries.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from daari.config.settings import Settings
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from daari.router.router import AppContext
    from daari.server.app import create_app

    settings = Settings()
    settings.observability.config_editor = True
    settings.boundaries.enabled = True
    settings.boundaries.mode = "block"
    settings.boundaries.product_name = "CK Assist"
    settings.boundaries.product_description = "Credit scores and cards only."
    settings.boundaries.allow_topics = ["credit score", "credit card"]
    settings.boundaries.deny_topics = ["python", "wedding"]
    settings.boundaries.refuse_message = "I only help with credit questions."
    settings.boundaries.clear_out_threshold = 0.7
    settings.boundaries.clear_in_threshold = 0.7
    settings.boundaries.stages_b1 = False  # B0 only for smoke determinism

    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    calls = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content="model-ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    for ex in (ctx.router.ollama, ctx.router.ollama_l3, ctx.router.ollama_l4, ctx.router.ollama_l5):
        ex.execute = fake_execute  # type: ignore[method-assign]
    app.state.ctx = ctx

    headers = {"X-Daari-Meta": "true"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://smoke") as http:
        before = calls["n"]
        out = await http.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Write a Python scraper"}],
            },
            headers=headers,
        )
        assert calls["n"] == before, "blocked request must not call the model"

        inn = await http.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [
                    {"role": "user", "content": "Why did my credit score drop?"}
                ],
            },
            headers=headers,
        )

        # Switch to warn via config editor and re-hit an out-of-scope prompt
        patched = await http.patch(
            "/v1/daari/config",
            json={"boundaries": {"mode": "warn"}},
        )
        warn = await http.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Plan my wedding"}],
            },
            headers=headers,
        )

    out_body = out.json()
    in_body = inn.json()
    warn_body = warn.json()
    print(f"out_tier={out_body.get('daari_meta', {}).get('tier')}")
    print(f"out_boundary={out_body.get('daari_meta', {}).get('boundary')}")
    print(f"in_tier={in_body.get('daari_meta', {}).get('tier')}")
    print(f"in_boundary={in_body.get('daari_meta', {}).get('boundary')}")
    print(f"patch_mode={patched.json().get('boundaries', {}).get('mode')}")
    print(f"warn_tier={warn_body.get('daari_meta', {}).get('tier')}")
    print(f"warn_boundary={warn_body.get('daari_meta', {}).get('boundary')}")
    print(f"model_calls={calls['n']}")

    ok = (
        out.status_code == 200
        and out_body.get("daari_meta", {}).get("tier") == "boundary"
        and out_body.get("daari_meta", {}).get("boundary", {}).get("label") == "out"
        and inn.status_code == 200
        and in_body.get("daari_meta", {}).get("tier") in ("L3", "L4", "L5")
        and "model-ok" in in_body["choices"][0]["message"]["content"]
        and patched.status_code == 200
        and patched.json().get("boundaries", {}).get("mode") == "warn"
        and warn.status_code == 200
        and warn_body.get("daari_meta", {}).get("boundary", {}).get("label") == "out"
        and warn_body.get("daari_meta", {}).get("tier") in ("L3", "L4", "L5")
        and "model-ok" in warn_body["choices"][0]["message"]["content"]
        and calls["n"] >= 2
    )
    print("PASS smoke_boundaries" if ok else "FAIL smoke_boundaries")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
