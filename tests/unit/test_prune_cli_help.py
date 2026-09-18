"""CLI help for `daari prune` documents retention stores (#692)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_prune_help_documents_retention_stores() -> None:
    result = CliRunner().invoke(cli_app, ["prune", "--help"])
    assert result.exit_code == 0
    text = result.output.lower()
    for needle in ("traces", "ledger", "audit", "shadow", "tasks"):
        assert needle in text, f"expected {needle!r} in prune --help"
