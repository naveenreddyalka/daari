"""Docs-site reference generator (issue #114)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "gen_reference", REPO_ROOT / "scripts" / "gen_reference.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_reference"] = module
    spec.loader.exec_module(module)
    return module


def test_config_reference_covers_nested_settings():
    module = _load_module()
    text = module.render_config_reference()
    # Spot-check keys across nesting levels; any rename must update the docs.
    for key in ("server.port", "models.l3", "cache.l1.similarity_threshold", "routing.max_tier_for_chat"):
        assert f"`{key}`" in text, f"missing config key {key}"
    assert "DAARI_<SECTION>__<KEY>" in text


def test_config_rows_flatten_defaults():
    module = _load_module()
    rows = {key: (type_text, default) for key, type_text, default, _ in module.iter_config_rows(
        __import__("daari.config.settings", fromlist=["Settings"]).Settings
    )}
    assert rows["server.port"] == ("int", "`11435`")
    assert rows["ollama.base_url"][1] == "`'http://127.0.0.1:11434'`"


def test_api_reference_lists_gateway_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # keep Settings() away from real config
    module = _load_module()
    text = module.render_api_reference()
    for route in ("/v1/chat/completions", "/v1/messages", "/api/chat", "/health", "/ready"):
        assert f"`{route}`" in text, f"missing route {route}"


def test_main_writes_both_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    module = _load_module()
    out = tmp_path / "ref"
    module.main(str(out))
    assert (out / "config.md").exists()
    assert (out / "api.md").exists()
