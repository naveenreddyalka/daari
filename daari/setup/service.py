from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from daari.config.settings import Settings

UNIT_NAME = "daari.service"
PLIST_LABEL = "com.daari.gateway"


class UnsupportedPlatformError(RuntimeError):
    """Native Windows (and unknown platforms) have no user service template."""


@dataclass(frozen=True)
class ServiceSpec:
    kind: str
    path: Path
    body: str
    working_directory: str
    log_path: Path


def default_home() -> Path:
    return Path.home()


def default_platform() -> str:
    return sys.platform


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
    return ServiceSpec(
        kind=kind,
        path=path,
        body=body,
        working_directory=str(_workdir(home)),
        log_path=_log_path(home),
    )


def uninstall_service(*, home: Path | None = None, platform: str | None = None) -> bool:
    home = home or default_home()
    platform = platform or default_platform()
    _kind, path = _paths(home, platform)
    if not path.is_file():
        return False
    path.unlink()
    return True


def service_status(*, home: Path | None = None, platform: str | None = None) -> str:
    home = home or default_home()
    platform = platform or default_platform()
    _kind, path = _paths(home, platform)
    return "installed" if path.is_file() else "missing"
