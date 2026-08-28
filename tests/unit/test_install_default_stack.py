from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "scripts" / "install.sh"


def test_install_sh_pulls_embed_unless_minimal():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "nomic-embed-text" in text
    assert "MINIMAL" in text
    l3_at = text.index("ollama pull llama3.2:3b")
    embed_at = text.index("ollama pull nomic-embed-text")
    assert embed_at > l3_at
    assert 'MINIMAL' in text and '"1"' in text
