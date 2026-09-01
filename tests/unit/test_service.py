from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli.app import app
from daari.config.settings import Settings
from daari.setup.service import (
    PLIST_LABEL,
    UNIT_NAME,
    ServiceCommandError,
    UnsupportedPlatformError,
    install_service,
    render_launchd_plist,
    render_systemd_unit,
    service_status,
    uninstall_service,
)


class RecordingRunner:
    def __init__(self, returncode: int = 0):
        self.calls: list[tuple[str, ...]] = []
        self._returncode = returncode

    def __call__(self, command):
        self.calls.append(tuple(command))
        return self._returncode


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
        }
    )


class TestRender:
    def test_systemd_unit_is_deterministic(self, tmp_path):
        home = tmp_path / "home"
        body = render_systemd_unit(
            home=home,
            daari_bin=Path("/opt/daari/bin/daari"),
            host="127.0.0.1",
            port=11435,
        )
        assert "ExecStart=/opt/daari/bin/daari serve --host 127.0.0.1 --port 11435" in body
        assert f"WorkingDirectory={home / '.daari'}" in body
        assert str(home / ".daari" / "serve.log") in body
        assert "[Install]" in body
        assert (
            render_systemd_unit(
                home=home,
                daari_bin=Path("/opt/daari/bin/daari"),
                host="127.0.0.1",
                port=11435,
            )
            == body
        )

    def test_launchd_plist_is_deterministic(self, tmp_path):
        home = tmp_path / "home"
        body = render_launchd_plist(
            home=home,
            daari_bin=Path("/opt/daari/bin/daari"),
            host="127.0.0.1",
            port=11435,
        )
        assert PLIST_LABEL in body
        assert "/opt/daari/bin/daari" in body
        assert "serve" in body
        assert "--host" in body
        assert "127.0.0.1" in body
        assert "--port" in body
        assert "11435" in body
        assert str(home / ".daari") in body
        assert str(home / ".daari" / "serve.log") in body
        assert (
            render_launchd_plist(
                home=home,
                daari_bin=Path("/opt/daari/bin/daari"),
                host="127.0.0.1",
                port=11435,
            )
            == body
        )


class TestInstallUninstall:
    def test_linux_install_writes_unit_and_uninstall_removes(self, tmp_path, settings):
        home = tmp_path / "home"
        spec = install_service(
            settings,
            home=home,
            platform="linux",
            daari_bin=Path("/opt/daari/bin/daari"),
        )
        assert spec.kind == "systemd"
        assert spec.path == home / ".config" / "systemd" / "user" / UNIT_NAME
        assert spec.path.is_file()
        text = spec.path.read_text(encoding="utf-8")
        assert "ExecStart=/opt/daari/bin/daari serve" in text
        assert spec.working_directory == str(home / ".daari")
        assert spec.log_path == home / ".daari" / "serve.log"
        assert service_status(home=home, platform="linux") == "installed"

        assert uninstall_service(home=home, platform="linux") is True
        assert not spec.path.exists()
        assert service_status(home=home, platform="linux") == "missing"
        assert uninstall_service(home=home, platform="linux") is False

    def test_macos_install_writes_plist(self, tmp_path, settings):
        home = tmp_path / "home"
        spec = install_service(
            settings,
            home=home,
            platform="darwin",
            daari_bin=Path("/opt/daari/bin/daari"),
        )
        assert spec.kind == "launchd"
        assert spec.path == home / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
        assert spec.path.is_file()
        assert PLIST_LABEL in spec.path.read_text(encoding="utf-8")
        assert service_status(home=home, platform="darwin") == "installed"
        uninstall_service(home=home, platform="darwin")
        assert not spec.path.exists()

    def test_windows_is_refused(self, tmp_path, settings):
        with pytest.raises(UnsupportedPlatformError, match="WSL"):
            install_service(
                settings,
                home=tmp_path / "home",
                platform="win32",
                daari_bin=Path("C:/daari.exe"),
            )


class TestActivateNow:
    def test_linux_now_enables_and_starts(self, tmp_path, settings):
        home = tmp_path / "home"
        runner = RecordingRunner()
        spec = install_service(
            settings,
            home=home,
            platform="linux",
            daari_bin=Path("/opt/daari/bin/daari"),
            now=True,
            runner=runner,
        )
        assert spec.path.is_file()
        assert runner.calls == [
            ("systemctl", "--user", "daemon-reload"),
            ("systemctl", "--user", "enable", "--now", UNIT_NAME),
        ]
        assert spec.commands == tuple(runner.calls)

    def test_macos_now_loads_written_path(self, tmp_path, settings):
        home = tmp_path / "home"
        runner = RecordingRunner()
        spec = install_service(
            settings,
            home=home,
            platform="darwin",
            daari_bin=Path("/opt/daari/bin/daari"),
            now=True,
            runner=runner,
        )
        assert runner.calls == [("launchctl", "load", "-w", str(spec.path))]

    def test_without_now_runner_is_untouched(self, tmp_path, settings):
        runner = RecordingRunner()
        spec = install_service(
            settings,
            home=tmp_path / "home",
            platform="linux",
            daari_bin=Path("/opt/daari/bin/daari"),
            runner=runner,
        )
        assert runner.calls == []
        assert spec.commands == ()

    def test_failing_runner_raises(self, tmp_path, settings):
        runner = RecordingRunner(returncode=3)
        with pytest.raises(ServiceCommandError, match="daemon-reload"):
            install_service(
                settings,
                home=tmp_path / "home",
                platform="linux",
                daari_bin=Path("/opt/daari/bin/daari"),
                now=True,
                runner=runner,
            )

    def test_linux_uninstall_now_disables_before_removing(self, tmp_path, settings):
        home = tmp_path / "home"
        spec = install_service(
            settings,
            home=home,
            platform="linux",
            daari_bin=Path("/opt/daari/bin/daari"),
        )
        runner = RecordingRunner()
        assert uninstall_service(home=home, platform="linux", now=True, runner=runner) is True
        assert runner.calls == [("systemctl", "--user", "disable", "--now", UNIT_NAME)]
        assert not spec.path.exists()

    def test_macos_uninstall_now_unloads_path(self, tmp_path, settings):
        home = tmp_path / "home"
        spec = install_service(
            settings,
            home=home,
            platform="darwin",
            daari_bin=Path("/opt/daari/bin/daari"),
        )
        runner = RecordingRunner()
        assert uninstall_service(home=home, platform="darwin", now=True, runner=runner) is True
        assert runner.calls == [("launchctl", "unload", "-w", str(spec.path))]
        assert not spec.path.exists()

    def test_uninstall_now_on_missing_file_is_noop(self, tmp_path):
        runner = RecordingRunner()
        assert (
            uninstall_service(home=tmp_path / "home", platform="linux", now=True, runner=runner)
            is False
        )
        assert runner.calls == []


class TestServiceCli:
    def test_install_status_uninstall(self, tmp_path, settings, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.setup.service.default_home", lambda: home)
        monkeypatch.setattr("daari.setup.service.default_platform", lambda: "linux")
        monkeypatch.setattr(
            "daari.setup.service.default_daari_bin",
            lambda: Path("/opt/daari/bin/daari"),
        )

        runner = CliRunner()
        installed = runner.invoke(app, ["service", "install"])
        assert installed.exit_code == 0, installed.output
        unit = home / ".config" / "systemd" / "user" / UNIT_NAME
        assert unit.is_file()
        assert "daari.service" in installed.stdout

        status = runner.invoke(app, ["service", "status"])
        assert status.exit_code == 0
        assert "installed" in status.stdout

        removed = runner.invoke(app, ["service", "uninstall"])
        assert removed.exit_code == 0
        assert not unit.exists()

    def test_cli_now_activates_and_uninstall_now_deactivates(self, tmp_path, settings, monkeypatch):
        home = tmp_path / "home"
        runner = RecordingRunner()
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.setup.service.default_home", lambda: home)
        monkeypatch.setattr("daari.setup.service.default_platform", lambda: "linux")
        monkeypatch.setattr(
            "daari.setup.service.default_daari_bin",
            lambda: Path("/opt/daari/bin/daari"),
        )
        monkeypatch.setattr("daari.setup.service.default_runner", lambda command: runner(command))

        cli = CliRunner()
        installed = cli.invoke(app, ["service", "install", "--now"])
        assert installed.exit_code == 0, installed.output
        assert ("systemctl", "--user", "enable", "--now", UNIT_NAME) in runner.calls
        assert "enable" in installed.stdout

        removed = cli.invoke(app, ["service", "uninstall", "--now"])
        assert removed.exit_code == 0, removed.output
        assert ("systemctl", "--user", "disable", "--now", UNIT_NAME) in runner.calls
        assert not (home / ".config" / "systemd" / "user" / UNIT_NAME).exists()

    def test_cli_now_failure_exits_nonzero(self, tmp_path, settings, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.setup.service.default_home", lambda: home)
        monkeypatch.setattr("daari.setup.service.default_platform", lambda: "linux")
        monkeypatch.setattr(
            "daari.setup.service.default_daari_bin",
            lambda: Path("/opt/daari/bin/daari"),
        )
        monkeypatch.setattr("daari.setup.service.default_runner", lambda command: 5)

        result = CliRunner().invoke(app, ["service", "install", "--now"])
        assert result.exit_code == 1
        assert "systemctl" in result.output

    def test_windows_cli_points_at_wsl(self, tmp_path, settings, monkeypatch):
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        monkeypatch.setattr("daari.setup.service.default_home", lambda: tmp_path / "home")
        monkeypatch.setattr("daari.setup.service.default_platform", lambda: "win32")

        result = CliRunner().invoke(app, ["service", "install"])
        assert result.exit_code == 1
        assert "WSL" in result.output
