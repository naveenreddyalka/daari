"""CLI/docs pins for LFM3-VL Ollama 0.40.13 platform GA (#2040)."""

from __future__ import annotations

from pathlib import Path

import typer.main

from daari.cli.app import app

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = ROOT / "docs/developer/guides/backends/ollama.md"


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
    """Pin --lfm3-vl Option.help (not rendered stdout — Rich wrap/ANSI vary in CI)."""
    click_cmd = typer.main.get_command(app)
    setup = click_cmd.get_command(None, "setup")
    models = setup.get_command(None, "models")
    opt = next(p for p in models.params if "--lfm3-vl" in (p.opts or []))
    help_text = opt.help or ""
    assert "0.40.13" in help_text
    assert "Linux" in help_text
    assert "Windows" in help_text
    assert "Apple" in help_text
    assert "coming soon" not in help_text.lower()
    assert "Apple-first" not in help_text
