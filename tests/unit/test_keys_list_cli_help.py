"""CLI help for `daari keys list` documents --status and --idle-days (#1572)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_keys_list_help_documents_status_and_idle_days() -> None:
    result = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"}).invoke(
        cli_app, ["keys", "list", "--help"]
    )
    assert result.exit_code == 0
    text = (result.stdout + result.stderr).lower()
    for needle in ("--status", "--idle-days"):
        assert needle in text, f"expected {needle!r} in keys list --help"
