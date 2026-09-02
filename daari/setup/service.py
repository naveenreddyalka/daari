from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from daari.config.settings import Settings

UNIT_NAME = "daari.service"
PLIST_LABEL = "com.daari.gateway"

ServiceRunner = Callable[[Sequence[str]], int]


class UnsupportedPlatformError(RuntimeError):
    """Native Windows (and unknown platforms) have no user service template."""


class ServiceCommandError(RuntimeError):
    """systemctl / launchctl returned a non-zero exit code."""


class ServiceNotInstalledError(RuntimeError):
    """No unit/plist written by `daari service install` exists for this user."""


@dataclass(frozen=True)
class ServiceSpec:
    kind: str
    path: Path
    body: str
    working_directory: str
    log_path: Path
    commands: tuple[tuple[str, ...], ...] = ()


def default_runner(command: Sequence[str]) -> int:
    return subprocess.run(list(command), check=False).returncode


def _run_all(
    commands: Sequence[Sequence[str]], runner: ServiceRunner | None
) -> tuple[tuple[str, ...], ...]:
    run = runner or (lambda command: default_runner(command))
    executed: list[tuple[str, ...]] = []
    for command in commands:
        code = run(command)
        executed.append(tuple(command))
        if code != 0:
            raise ServiceCommandError(f"`{' '.join(command)}` failed with exit code {code}")
    return tuple(executed)


def default_home() -> Path:
    return Path.home()


def default_platform() -> str:
    return sys.platform


def default_uid() -> int:
    getuid = getattr(os, "getuid", None)
    return getuid() if getuid else 0


def restart_hint() -> str:
    """What to tell users who must bounce the daemon after a config change."""
    return "daari service restart"


def default_daari_bin() -> Path:
    sibling = Path(sys.executable).resolve().parent / "daari"
    if sibling.is_file():
        return sibling
    found = shutil.which("daari")
    if found:
        return Path(found)
    return Path("daari")


def _workdir(home: Path) -> Path:
    return home / ".daari"


def _log_path(home: Path) -> Path:
    return _workdir(home) / "serve.log"


def render_systemd_unit(
    *,
    home: Path,
    daari_bin: Path,
    host: str,
    port: int,
) -> str:
    workdir = _workdir(home)
    log = _log_path(home)
    exec_start = f"{daari_bin} serve --host {host} --port {port}"
    return (
        "[Unit]\n"
        "Description=daari local-first execution router\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={workdir}\n"
        f"ExecStart={exec_start}\n"
        f"StandardOutput=append:{log}\n"
        f"StandardError=append:{log}\n"
        "Restart=on-failure\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def render_launchd_plist(
    *,
    home: Path,
    daari_bin: Path,
    host: str,
    port: int,
) -> str:
    workdir = _workdir(home)
    log = _log_path(home)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{PLIST_LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        f"    <string>{daari_bin}</string>\n"
        "    <string>serve</string>\n"
        "    <string>--host</string>\n"
        f"    <string>{host}</string>\n"
        "    <string>--port</string>\n"
        f"    <string>{port}</string>\n"
        "  </array>\n"
        "  <key>WorkingDirectory</key>\n"
        f"  <string>{workdir}</string>\n"
        "  <key>StandardOutPath</key>\n"
        f"  <string>{log}</string>\n"
        "  <key>StandardErrorPath</key>\n"
        f"  <string>{log}</string>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>KeepAlive</key>\n"
        "  <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _paths(home: Path, platform: str) -> tuple[str, Path]:
    if platform.startswith("linux"):
        return "systemd", home / ".config" / "systemd" / "user" / UNIT_NAME
    if platform == "darwin":
        return "launchd", home / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
    raise UnsupportedPlatformError(
        "Native Windows is not supported. Use WSL2 — see "
        "docs/developer/get-started/install-windows.md (issue #261)."
    )


def install_service(
    settings: Settings,
    *,
    home: Path | None = None,
    platform: str | None = None,
    daari_bin: Path | None = None,
    now: bool = False,
    runner: ServiceRunner | None = None,
) -> ServiceSpec:
    home = home or default_home()
    platform = platform or default_platform()
    daari_bin = daari_bin or default_daari_bin()
    kind, path = _paths(home, platform)
    if kind == "systemd":
        body = render_systemd_unit(
            home=home,
            daari_bin=daari_bin,
            host=settings.server.host,
            port=settings.server.port,
        )
    else:
        body = render_launchd_plist(
            home=home,
            daari_bin=daari_bin,
            host=settings.server.host,
            port=settings.server.port,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    _workdir(home).mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    commands = _run_all(_activate_commands(kind, path), runner) if now else ()
    return ServiceSpec(
        kind=kind,
        path=path,
        body=body,
        working_directory=str(_workdir(home)),
        log_path=_log_path(home),
        commands=commands,
    )


def _activate_commands(kind: str, path: Path) -> tuple[tuple[str, ...], ...]:
    if kind == "systemd":
        return (
            ("systemctl", "--user", "daemon-reload"),
            ("systemctl", "--user", "enable", "--now", UNIT_NAME),
        )
    return (("launchctl", "load", "-w", str(path)),)


def _deactivate_commands(kind: str, path: Path) -> tuple[tuple[str, ...], ...]:
    if kind == "systemd":
        return (("systemctl", "--user", "disable", "--now", UNIT_NAME),)
    return (("launchctl", "unload", "-w", str(path)),)


def _restart_commands(kind: str, uid: int) -> tuple[tuple[str, ...], ...]:
    if kind == "systemd":
        return (("systemctl", "--user", "restart", UNIT_NAME),)
    # `kickstart -k` kills and relaunches the job in the user's GUI domain; the
    # label is the one render_launchd_plist() wrote, not the dev watchdog's.
    return (("launchctl", "kickstart", "-k", f"gui/{uid}/{PLIST_LABEL}"),)


def restart_service(
    *,
    home: Path | None = None,
    platform: str | None = None,
    runner: ServiceRunner | None = None,
    uid: int | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Restart the user service; the daemon reads config once, so this applies edits."""
    home = home or default_home()
    platform = platform or default_platform()
    kind, path = _paths(home, platform)
    if not path.is_file():
        raise ServiceNotInstalledError(
            f"No daari user service at {path}. Install it first: daari service install --now"
        )
    uid = default_uid() if uid is None else uid
    return _run_all(_restart_commands(kind, uid), runner)


def uninstall_service(
    *,
    home: Path | None = None,
    platform: str | None = None,
    now: bool = False,
    runner: ServiceRunner | None = None,
) -> bool:
    home = home or default_home()
    platform = platform or default_platform()
    kind, path = _paths(home, platform)
    if not path.is_file():
        return False
    if now:
        _run_all(_deactivate_commands(kind, path), runner)
    path.unlink()
    return True


def service_status(*, home: Path | None = None, platform: str | None = None) -> str:
    home = home or default_home()
    platform = platform or default_platform()
    _kind, path = _paths(home, platform)
    return "installed" if path.is_file() else "missing"
