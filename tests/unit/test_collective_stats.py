"""Phase D3: opt-in anonymized collective stats (review-first export)."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

import daari
from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.learning.collective import (
    build_collective_stats,
    payload_is_clean,
    upload_collective_stats,
)
from daari.learning.feedback import FeedbackStore


@pytest.fixture
def store(tmp_path) -> FeedbackStore:
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    for i in range(4):
        store.record_outcome(
            trace_id=f"t{i}",
            category="code_gen",
            complexity="standard",
            tier="L3",
            confidence=0.9,
            escalated=i == 0,
            latency_ms=400 + i,
        )
    store.record_shadow(category="code_gen", similarity=0.7, agreed=False)
    store.record_shadow(category="code_gen", similarity=0.99, agreed=True)
    return store


def test_payload_shape_and_aggregates(store):
    settings = Settings()
    payload = build_collective_stats(settings, store, days=7)
    assert payload["schema"] == 1
    assert payload["daari_version"] == daari.__version__
    assert payload["models"]["l3"] == settings.models.l3
    code_gen = payload["categories"]["code_gen"]["L3"]
    assert code_gen["outcomes"] == 4
    assert code_gen["escalated"] == 1
    assert payload["cache_trust"]["code_gen"]["samples"] == 2
    assert payload["cache_trust"]["code_gen"]["false_hit_rate"] == 0.5


def test_payload_never_contains_sensitive_keys(store):
    payload = build_collective_stats(Settings(), store, days=7)
    assert payload_is_clean(payload)
    flat = json.dumps(payload)
    for banned in ("prompt", "client_id", "trace_id", "messages"):
        assert f'"{banned}"' not in flat


def test_payload_clean_guard_catches_leaks():
    assert payload_is_clean({"ok": [{"nested": 1}]})
    assert not payload_is_clean({"ok": {"prompt": "secret"}})
    assert not payload_is_clean([{"trace_id": "t1"}])


class TestUpload:
    def test_disabled_refuses(self, store):
        settings = Settings()
        payload = build_collective_stats(settings, store)
        with pytest.raises(RuntimeError, match="disabled"):
            upload_collective_stats(payload, settings)

    def test_enabled_without_url_refuses(self, store):
        settings = Settings()
        settings.learning.collective_enabled = True
        payload = build_collective_stats(settings, store)
        with pytest.raises(RuntimeError, match="no learning.collective_url"):
            upload_collective_stats(payload, settings)

    def test_opted_in_posts_with_token(self, store):
        settings = Settings()
        settings.learning.collective_enabled = True
        settings.learning.collective_url = "http://collect.test/v1/stats"
        settings.learning.collective_token = "tok"
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(202)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        payload = build_collective_stats(settings, store)
        status = upload_collective_stats(payload, settings, client=client)
        assert status == 202
        assert seen["auth"] == "Bearer tok"
        assert seen["body"]["schema"] == 1

    def test_dirty_payload_refused(self, store):
        settings = Settings()
        settings.learning.collective_enabled = True
        settings.learning.collective_url = "http://collect.test/v1/stats"
        payload = build_collective_stats(settings, store)
        payload["oops"] = {"prompt": "leaked text"}
        with pytest.raises(RuntimeError, match="sensitive-key guard"):
            upload_collective_stats(payload, settings, client=httpx.Client())


class TestCLI:
    def test_export_prints_reviewable_json(self, store, tmp_path, monkeypatch):
        monkeypatch.setattr("daari.cli.app._feedback_store", lambda: store)
        out_file = tmp_path / "stats.json"
        runner = CliRunner()
        result = runner.invoke(
            cli_app, ["learn", "export-stats", "--out", str(out_file)]
        )
        assert result.exit_code == 0
        written = json.loads(out_file.read_text())
        assert written["schema"] == 1
        assert "code_gen" in written["categories"]

    def test_upload_flag_refused_when_disabled(self, store, monkeypatch):
        monkeypatch.setattr("daari.cli.app._feedback_store", lambda: store)
        runner = CliRunner()
        result = runner.invoke(cli_app, ["learn", "export-stats", "--upload"])
        assert result.exit_code == 1
        assert "Upload refused" in result.output

    def test_defaults_off(self):
        settings = Settings()
        assert settings.learning.collective_enabled is False
        assert settings.learning.collective_url == ""
