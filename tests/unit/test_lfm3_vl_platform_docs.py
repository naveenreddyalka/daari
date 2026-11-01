"""CLI/docs pins for LFM3-VL Ollama 0.40.13 platform GA (#2040)."""

from __future__ import annotations

from pathlib import Path

import typer.main
from typer.testing import CliRunner

from daari.cli.app import app

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = ROOT / "docs/developer/guides/backends/ollama.md"
runner = CliRunner()


def test_ollama_guide_lfm3_vl_platform_ga() -> None:
    text = OLLAMA.read_text(encoding="utf-8")
    vl = text.split("**LFM3-VL**", 1)[1].split("**LFM3-Omni**", 1)[0]
    assert "0.40.13" in vl
    assert "Linux" in vl
    assert "Windows" in vl
    assert "macOS" in vl or "Apple" in vl
    assert "coming soon" not in vl.lower()
    assert "Apple-first" not in vl


def test_setup_models_lfm3_vl_help_platform_ga() -> None:
    result = runner.invoke(app, ["setup", "models", "--help"])
    assert result.exit_code == 0
    # Typer wraps long Option help; flatten whitespace for the pin.
    help_text = " ".join(result.stdout.split())
    assert "--lfm3-vl" in help_text
    assert "0.40.13" in help_text
    assert "Apple-first" not in help_text
    assert "coming soon" not in help_text.lower()
    # The --lfm3-vl option help itself names the GA platforms.
    click_cmd = typer.main.get_command(app)
    setup = click_cmd.get_command(None, "setup")
    models = setup.get_command(None, "models")
    opt = next(p for p in models.params if "--lfm3-vl" in (p.opts or []))
    assert "0.40.13" in (opt.help or "")
    assert "Linux" in (opt.help or "")
    assert "Windows" in (opt.help or "")
    assert "Apple" in (opt.help or "")
    assert "coming soon" not in (opt.help or "").lower()
    assert "Apple-first" not in (opt.help or "")
