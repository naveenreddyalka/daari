"""lfm3-audio speech-only recipe (#2071)."""

from __future__ import annotations

import yaml

from daari.setup.models import (
    LFM3_AUDIO_MODEL,
    LFM3_AUDIO_RECIPE_NOTE,
    apply_lfm3_audio_speech_recipe,
)


def test_lfm3_audio_recipe_dry_run_does_not_write(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ollama:\n  base_url: http://127.0.0.1:11434\n"
        "models:\n  l3: llama3.2:3b\n  l4: llama3.1:8b\n",
        encoding="utf-8",
    )
    before = config_path.read_text(encoding="utf-8")
    plan = apply_lfm3_audio_speech_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is True
    assert plan.model == LFM3_AUDIO_MODEL
    assert config_path.read_text(encoding="utf-8") == before


def test_lfm3_audio_recipe_wires_speech_without_l4_or_caps(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ollama:\n  base_url: http://ollama.test:11434\n"
        "models:\n  l3: llama3.2:3b\n  l4: llama3.1:8b\n",
        encoding="utf-8",
    )
    result = apply_lfm3_audio_speech_recipe(config_path=config_path, dry_run=False)
    assert result.changed is True
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["tts"]["base_url"] == "http://ollama.test:11434/v1"
    assert loaded["tts"]["model"] == LFM3_AUDIO_MODEL
    assert loaded["asr"]["base_url"] == "http://ollama.test:11434/v1"
    assert loaded["asr"]["model"] == LFM3_AUDIO_MODEL
    assert loaded["models"]["l4"] == "llama3.1:8b"
    caps = (loaded.get("models") or {}).get("capabilities") or {}
    assert LFM3_AUDIO_MODEL not in caps


def test_lfm3_audio_recipe_idempotent_reapply(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ollama:\n  base_url: http://127.0.0.1:11434\nmodels:\n  l3: llama3.2:3b\n",
        encoding="utf-8",
    )
    first = apply_lfm3_audio_speech_recipe(config_path=config_path, dry_run=False)
    assert first.changed is True
    after_first = config_path.read_text(encoding="utf-8")
    second = apply_lfm3_audio_speech_recipe(config_path=config_path, dry_run=False)
    assert second.changed is False
    assert config_path.read_text(encoding="utf-8") == after_first


def test_lfm3_audio_recipe_note_speech_only_not_chat_tier():
    note = LFM3_AUDIO_RECIPE_NOTE.lower()
    assert "speech" in note or "tts" in note
    assert "not" in note and ("l4" in note or "chat" in note)
    assert f"ollama pull {LFM3_AUDIO_MODEL}" in LFM3_AUDIO_RECIPE_NOTE
    assert "0.40.12" in LFM3_AUDIO_RECIPE_NOTE
