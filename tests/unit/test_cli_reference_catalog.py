"""CLI reference lists every top-level Typer command (#681)."""

from __future__ import annotations

from pathlib import Path

from typer.main import get_command

from daari.cli.app import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MD = REPO_ROOT / "docs/developer/reference/cli.md"


def test_cli_reference_lists_all_top_level_commands() -> None:
    text = CLI_MD.read_text(encoding="utf-8")
    top = sorted(get_command(app).commands.keys())
    missing = [name for name in top if f"`{name}`" not in text]
    assert not missing, f"cli.md missing top-level commands: {missing}"


def test_cli_reference_learn_matches_typer_and_route_preview() -> None:
    text = CLI_MD.read_text(encoding="utf-8")
    learn = sorted(get_command(app).commands["learn"].commands.keys())
    for name in learn:
        assert f"`{name}`" in text or name in text, f"learn subcommand missing: {name}"
    for stale in ("aggregates", "outcome", "mlx-lm"):
        assert stale not in text, f"stale learn command still documented: {stale}"
    assert "`preview`" in text
    assert "`route`" in text
