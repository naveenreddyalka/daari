from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_MD = ROOT / "docs" / "developer" / "get-started" / "install.md"
WINDOWS_MD = ROOT / "docs" / "developer" / "get-started" / "install-windows.md"
INSTALL_PS1 = ROOT / "scripts" / "install.ps1"


def test_windows_doc_exists_and_is_honest():
    assert WINDOWS_MD.is_file()
    text = WINDOWS_MD.read_text(encoding="utf-8").lower()
    assert "wsl" in text
    assert "daari onboard" in text
    assert "native-windows ollama is one-click" not in text
    assert "not a supported first-run" in text or "not supported" in text


def test_install_md_links_windows_doc():
    text = INSTALL_MD.read_text(encoding="utf-8")
    assert "install-windows.md" in text
    assert "Option E" in text or "Windows" in text


def test_install_ps1_uses_wsl_and_onboard():
    assert INSTALL_PS1.is_file()
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "wsl" in text.lower()
    assert "daari onboard --yes" in text
    assert "pip install daari" in text
    assert "does not install a native Windows daemon" in text
    lowered = text.lower()
    assert "one-click native" not in lowered
    assert "ollama for windows" not in lowered
