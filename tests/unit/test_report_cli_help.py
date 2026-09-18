"""CLI help for `daari report` documents format and breakdown flags (#701)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_report_help_documents_format_and_breakdown_flags() -> None:
    result = CliRunner().invoke(cli_app, ["report", "--help"])
    assert result.exit_code == 0
    text = result.output.lower()
    for needle in ("format", "by-client", "by-team", "by-user"):
        assert needle in text, f"expected {needle!r} in report --help"
