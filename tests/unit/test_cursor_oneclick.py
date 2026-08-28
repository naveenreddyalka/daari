from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings
from daari.setup.daemon import ensure_local_daemon


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
        }
    )


class TestEnsureLocalDaemon:
    def test_skips_spawn_when_healthy(self, tmp_path):
        spawned: list[str] = []
        assert (
            ensure_local_daemon(
                _settings(tmp_path),
                health_fn=lambda: True,
                spawn_fn=lambda: spawned.append("serve"),
            )
            is True
        )
        assert spawned == []

    def test_spawns_and_waits_when_unhealthy(self, tmp_path):
        spawned: list[str] = []
        assert (
            ensure_local_daemon(
                _settings(tmp_path),
                health_fn=lambda: bool(spawned),
                spawn_fn=lambda: spawned.append("serve"),
            )
            is True
        )
        assert spawned == ["serve"]

    def test_returns_false_when_still_unhealthy(self, tmp_path):
        assert (
            ensure_local_daemon(
                _settings(tmp_path),
                health_fn=lambda: False,
                spawn_fn=lambda: None,
                wait_seconds=0.01,
                poll_interval=0.01,
            )
            is False
        )


class TestSetupCursorDaemonize:
    def test_missing_cloudflared_prints_install_hint(self, tmp_path, monkeypatch):
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: _settings(tmp_path))
        monkeypatch.setattr("daari.cli.app.ensure_local_daemon", lambda *_a, **_k: True)
        monkeypatch.setattr("daari.cli.app.shutil.which", lambda _name: None)

        result = CliRunner().invoke(
            app, ["setup", "cursor", "--tunnel", "--yes", "--daemonize"]
        )
        assert result.exit_code == 1
        assert "brew install cloudflared" in result.output

    def test_daemonize_starts_daemon_and_returns_without_waiting(
        self, tmp_path, monkeypatch
    ):
        calls = {"ensure": 0, "waited": 0}

        def fake_ensure(*_a, **_k):
            calls["ensure"] += 1
            return True

        process = MagicMock()
        process.pid = 4242
        process.poll.return_value = None

        def fake_wait(*_a, **_k):
            calls["waited"] += 1
            raise AssertionError("daemonize must not block on the tunnel")

        process.wait.side_effect = fake_wait

        captured: dict = {}

        def fake_apply(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("daari.cli.app.get_settings", lambda: _settings(tmp_path))
        monkeypatch.setattr("daari.cli.app.ensure_local_daemon", fake_ensure)
        monkeypatch.setattr("daari.cli.app.shutil.which", lambda _name: "/usr/bin/cloudflared")
        monkeypatch.setattr(
            "daari.cli.app._start_cloudflared_tunnel",
            lambda **_k: (process, "https://abc.trycloudflare.com"),
        )
        monkeypatch.setattr("daari.cli.app.wait_for_tunnel_health", lambda _url: True)
        monkeypatch.setattr("daari.cli.app.apply_cursor_setup", fake_apply)

        result = CliRunner().invoke(
            app, ["setup", "cursor", "--tunnel", "--yes", "--daemonize"]
        )
        assert result.exit_code == 0, result.output
        assert calls["ensure"] == 1
        assert calls["waited"] == 0
        assert "https://abc.trycloudflare.com/v1" in result.stdout
        assert captured["yes"] is True
        assert captured["secure"] is True
        assert captured["base_url"] == "https://abc.trycloudflare.com/v1"


def test_tunnel_sh_setup_cursor_delegates():
    text = (Path(__file__).resolve().parents[2] / "scripts" / "tunnel.sh").read_text(
        encoding="utf-8"
    )
    assert "daari setup cursor --tunnel --yes --daemonize" in text
