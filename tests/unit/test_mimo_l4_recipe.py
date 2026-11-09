"""MiMo V2.6 L4 code/agent recipe (Ollama ≥ 0.40.15) (#2147)."""

from __future__ import annotations

import httpx
import yaml
from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings
from daari.router.capabilities import catalog_from_settings, known_model_capabilities
from daari.setup.doctor import _check_mimo_unused
from daari.setup.models import (
    MIMO_MODEL,
    MIMO_OLLAMA_FLOOR,
    MIMO_RECIPE_NOTE,
    apply_mimo_l4_recipe,
)


def _tags_client(names: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(
                200, json={"models": [{"name": n} for n in names]}
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mimo_l4_recipe_dry_run_does_not_write(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models:\n  l3: llama3.2:3b\n  l4: llama3.1:8b\n", encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")
    plan = apply_mimo_l4_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is True
    assert plan.tier == "l4"
    assert plan.model == MIMO_MODEL
    assert config_path.read_text(encoding="utf-8") == before


def test_mimo_l4_recipe_dry_run_unchanged_when_already_set(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"models:\n  l4: {MIMO_MODEL}\n", encoding="utf-8")
    plan = apply_mimo_l4_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is False
    assert plan.model == MIMO_MODEL


def test_mimo_l4_recipe_apply_sets_l4(tmp_path):
    config_path = tmp_path / "config.yaml"
    result = apply_mimo_l4_recipe(config_path=config_path, dry_run=False)
    assert result.changed is True
    assert result.model == MIMO_MODEL
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["models"]["l4"] == MIMO_MODEL


def test_mimo_recipe_note_04015_floor():
    assert MIMO_OLLAMA_FLOOR == (0, 40, 15)
    assert "0.40.15" in MIMO_RECIPE_NOTE
    assert MIMO_MODEL in MIMO_RECIPE_NOTE


def test_mimo_capability_card_tools_for_code_agent():
    caps = known_model_capabilities(MIMO_MODEL)
    assert "tools" in caps
    assert "json" in caps
    assert known_model_capabilities(f"{MIMO_MODEL}:latest") == caps


def test_mimo_catalog_as_local_l4():
    catalog = catalog_from_settings(Settings.model_validate({"models": {"l4": MIMO_MODEL}}))
    caps = catalog.for_model(MIMO_MODEL)
    assert "tools" in caps
    assert "json" in caps


def test_mimo_unused_tip_when_host_has_tag_but_l4_elsewhere():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_mimo_unused(settings, _tags_client([MIMO_MODEL, "llama3.1:8b"]))
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_mimo_unused"
    assert MIMO_MODEL in tip.detail
    assert "0.40.15" in tip.detail
    assert "daari setup models --mimo" in tip.detail


def test_mimo_unused_tip_quiet_when_l4_already_mimo():
    settings = Settings.model_validate(
        {
            "models": {"l4": MIMO_MODEL},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_mimo_unused(settings, _tags_client([MIMO_MODEL])) is None


def test_mimo_cli_option_documents_floor():
    runner = CliRunner()
    result = runner.invoke(app, ["setup", "models", "--help"])
    assert result.exit_code == 0
    assert "--mimo" in result.stdout
    assert "0.40.15" in result.stdout
    assert MIMO_MODEL in result.stdout
