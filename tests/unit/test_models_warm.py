"""daari models warm + onboard --warm (#843)."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.setup.doctor import _check_warm_models, run_doctor
from daari.setup.models import (
    WarmResult,
    configured_warm_models,
    warm_configured_models,
    warm_ollama_model,
)
from daari.setup.onboard import run_onboard


def test_configured_warm_models_includes_tiers_and_embed():
    settings = Settings.model_validate(
        {
            "models": {"l3": "a", "l4": "b", "l5": "a"},
            "cache": {"l1": {"embedding_model": "embed"}},
        }
    )
    assert configured_warm_models(settings) == ["a", "b", "embed"]


def test_warm_ollama_model_generate_and_embed():
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen.append((request.url.path, body))
        if request.url.path.endswith("/api/generate"):
            return httpx.Response(200, json={"response": "ok"})
        return httpx.Response(200, json={"embedding": [0.1]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        chat = warm_ollama_model("http://ollama", "llama3.2:3b", client=client)
        embed = warm_ollama_model(
            "http://ollama",
            "nomic-embed-text",
            embed_model="nomic-embed-text",
            client=client,
        )
    assert chat.ok and chat.detail == "loaded"
    assert embed.ok
    assert any(
        path.endswith("/api/generate") and (body.get("options") or {}).get("num_predict") == 1
        for path, body in seen
    )
    assert any(
        path.endswith("/api/embeddings") and body.get("prompt") == "daari-warm"
        for path, body in seen
    )


def test_warm_configured_models_reports_failures(settings):
    calls: list[str] = []

    def fake(model: str) -> WarmResult:
        calls.append(model)
        return WarmResult(model=model, ok=model != settings.models.l4, detail="x")

    results = warm_configured_models(settings, warm_fn=fake)
    assert calls == configured_warm_models(settings)
    assert any(not item.ok for item in results)


def test_cli_models_warm_help_and_exit():
    runner = CliRunner()
    help_result = runner.invoke(cli_app, ["models", "warm", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "Load configured" in help_result.output or "Ollama" in help_result.output

    with patch(
        "daari.setup.models.warm_configured_models",
        return_value=[WarmResult("m", False, "no")],
    ):
        failed = runner.invoke(cli_app, ["models", "warm"])
    assert failed.exit_code == 1
    assert "FAIL: m" in failed.output

    with patch(
        "daari.setup.models.warm_configured_models",
        return_value=[WarmResult("m", True, "loaded")],
    ):
        ok = runner.invoke(cli_app, ["models", "warm"])
    assert ok.exit_code == 0
    assert "ok: m" in ok.output


def test_onboard_warm_flag_runs_warm(settings):
    warmed: list[str] = []

    def warm_fn():
        warmed.append("yes")
        return [WarmResult(model="llama3.2:3b", ok=True, detail="loaded")]

    report = run_onboard(
        settings,
        pull=False,
        run_doctor=False,
        warm=True,
        warm_fn=warm_fn,
        fetch_models_fn=lambda: ["llama3.2:3b"],
    )
    assert warmed == ["yes"]
    step = report.step("warm:llama3.2:3b")
    assert step is not None and step.ok


def test_doctor_warm_models_hint_when_daemon_up_and_ps_empty(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _check_warm_models(settings, client, daemon_ok=True)
    assert result.optional is True
    assert result.ok is False
    assert "daari models warm" in result.detail

    skipped = _check_warm_models(settings, None, daemon_ok=False)
    assert skipped.ok is True
    assert "skipped" in skipped.detail


def test_doctor_run_includes_warm_models_check(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_doctor(settings, httpx_client=client)
    assert any(item.name == "warm_models" for item in results)


def test_onboard_cli_exposes_warm_flag():
    from typer.main import get_command

    onboard = get_command(cli_app).commands["onboard"]
    names = {param.name for param in onboard.params}
    assert "warm" in names
    # Also ensure the flag is accepted (help text can wrap oddly in CI).
    result = CliRunner().invoke(cli_app, ["onboard", "--help"])
    assert result.exit_code == 0
    assert "No such option" not in result.output
