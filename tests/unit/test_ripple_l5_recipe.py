"""Ripple Preview L5 agentic-coding recipe (Ollama ≥ 0.40.16) (#2217)."""

from __future__ import annotations

import httpx
import typer.main
import yaml

from daari.cli.app import app
from daari.config.settings import Settings
from daari.router.capabilities import catalog_from_settings, known_model_capabilities
from daari.setup.doctor import _ollama_ripple_warning
from daari.setup.models import (
    RIPPLE_MODEL,
    RIPPLE_OLLAMA_FLOOR,
    RIPPLE_RECIPE_NOTE,
    apply_ripple_l5_recipe,
)


def test_ripple_l5_recipe_dry_run_does_not_write(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models:\n  l5: llama3.1:70b\n", encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")
    plan = apply_ripple_l5_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is True
    assert plan.tier == "l5"
    assert plan.model == RIPPLE_MODEL
    assert config_path.read_text(encoding="utf-8") == before


def test_ripple_l5_recipe_dry_run_unchanged_when_already_set(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"models:\n  l5: {RIPPLE_MODEL}\n", encoding="utf-8")
    plan = apply_ripple_l5_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is False
    assert plan.model == RIPPLE_MODEL


def test_ripple_l5_recipe_apply_sets_l5(tmp_path):
    config_path = tmp_path / "config.yaml"
    result = apply_ripple_l5_recipe(config_path=config_path, dry_run=False)
    assert result.changed is True
    assert result.model == RIPPLE_MODEL
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["models"]["l5"] == RIPPLE_MODEL


def test_ripple_recipe_note_04016_floor():
    assert RIPPLE_OLLAMA_FLOOR == (0, 40, 16)
    assert "0.40.16" in RIPPLE_RECIPE_NOTE
    assert RIPPLE_MODEL in RIPPLE_RECIPE_NOTE
    assert "65B" in RIPPLE_RECIPE_NOTE
    assert "Preview" in RIPPLE_RECIPE_NOTE or "preview" in RIPPLE_RECIPE_NOTE


def test_ripple_capability_card_tools_for_agentic_coding():
    caps = known_model_capabilities(RIPPLE_MODEL)
    assert "tools" in caps
    assert "json" in caps
    assert known_model_capabilities(f"{RIPPLE_MODEL}:latest") == caps


def test_ripple_catalog_as_local_l5():
    catalog = catalog_from_settings(Settings.model_validate({"models": {"l5": RIPPLE_MODEL}}))
    caps = catalog.for_model(RIPPLE_MODEL)
    assert "tools" in caps
    assert "json" in caps


def _version_client(version: str | None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/version"):
            if version is None:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"version": version})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ripple_doctor_tip_when_ollama_below_floor():
    tip = _ollama_ripple_warning(
        _version_client("0.40.15"),
        "http://ollama.test",
        l4_model="llama3.1:8b",
        l5_model=RIPPLE_MODEL,
    )
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_ripple"
    assert "0.40.16" in tip.detail
    assert RIPPLE_MODEL in tip.detail


def test_ripple_doctor_quiet_when_ollama_meets_floor():
    assert (
        _ollama_ripple_warning(
            _version_client("0.40.16"),
            "http://ollama.test",
            l4_model="llama3.1:8b",
            l5_model=RIPPLE_MODEL,
        )
        is None
    )


def test_ripple_doctor_tip_when_l4_is_ripple():
    tip = _ollama_ripple_warning(
        _version_client("0.40.10"),
        "http://ollama.test",
        l4_model=RIPPLE_MODEL,
        l5_model="llama3.1:70b",
    )
    assert tip is not None
    assert RIPPLE_MODEL in tip.detail


def test_ripple_cli_option_documents_floor():
    click_cmd = typer.main.get_command(app)
    setup = click_cmd.get_command(None, "setup")
    models = setup.get_command(None, "models")
    opt = next(p for p in models.params if "--ripple" in (p.opts or []))
    help_text = opt.help or ""
    assert "0.40.16" in help_text
    assert RIPPLE_MODEL in help_text
