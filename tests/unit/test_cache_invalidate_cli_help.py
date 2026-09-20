"""CLI help for `daari cache invalidate` documents --token (#826)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app


def test_cache_invalidate_help_documents_token() -> None:
    result = CliRunner().invoke(
        cli_app,
        ["cache", "invalidate", "--help"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"},
    )
    assert result.exit_code == 0
    text = (result.stdout + result.stderr).lower()
    assert "--token" in text
    assert "bearer" in text or "sso" in text or "master" in text
