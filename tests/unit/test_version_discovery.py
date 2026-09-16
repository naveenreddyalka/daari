"""Package version via CLI and /health (issue #552)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari import __version__
from daari.cli.app import app as cli_app
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def test_cli_version_flag():
    result = CliRunner().invoke(cli_app, ["--version"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == __version__


@pytest.mark.asyncio
async def test_health_includes_version(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == __version__
