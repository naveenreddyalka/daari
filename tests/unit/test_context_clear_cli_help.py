"""CLI help for `daari context clear` documents L0/L1/CCS (#700)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_context_clear_help_documents_cache_stores() -> None:
    result = CliRunner().invoke(cli_app, ["context", "clear", "--help"])
    assert result.exit_code == 0
    text = result.output.lower()
    for needle in ("l0", "l1", "ccs"):
        assert needle in text, f"expected {needle!r} in context clear --help"
