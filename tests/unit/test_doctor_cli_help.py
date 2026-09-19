"""CLI help for `daari doctor` mentions --suggest-models (#683)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_doctor_help_mentions_suggest_models() -> None:
    result = CliRunner().invoke(cli_app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--suggest-models" in result.output
