"""CLI help for `daari stats` mentions backend_summary (#675)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_stats_help_mentions_backend_summary() -> None:
    result = CliRunner().invoke(cli_app, ["stats", "--help"])
    assert result.exit_code == 0
    assert "backend_summary" in result.output
