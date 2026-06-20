from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from daari.clients.cursor.recipe import CursorSetupRecipe
from daari.clients.registry import default_registry
from daari.config.settings import Settings
from daari.setup.doctor import doctor_exit_code, run_doctor


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
        }
    )


class TestDoctor:
    def test_all_required_pass(self, settings):
        mock = MagicMock(spec=httpx.Client)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {"total_requests": 3}
        mock.get.side_effect = [tags_response, stats_response]

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["python"].ok is True
        assert by_name["config"].ok is True
        assert by_name["ollama"].ok is True
        assert by_name["model"].ok is True
        assert by_name["daemon"].ok is True
        assert doctor_exit_code(results) == 0

    def test_ollama_down_fails_required(self, settings):
        mock = MagicMock(spec=httpx.Client)
        mock.get.side_effect = httpx.ConnectError("connection refused")

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["ollama"].ok is False
        assert by_name["model"].ok is False
        assert doctor_exit_code(results) == 1

    def test_daemon_down_does_not_fail_exit(self, settings):
        mock = MagicMock(spec=httpx.Client)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}

        def get_side_effect(url):
            if url.endswith("/api/tags"):
                return tags_response
            raise httpx.ConnectError("daemon not running")

        mock.get.side_effect = get_side_effect

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["ollama"].ok is True
        assert by_name["model"].ok is True
        assert by_name["daemon"].ok is False
        assert by_name["daemon"].optional is True
        assert doctor_exit_code(results) == 0

    def test_model_missing_fails(self, settings):
        mock = MagicMock(spec=httpx.Client)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": [{"name": "other:7b"}]}
        mock.get.return_value = tags_response

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["model"].ok is False
        assert doctor_exit_code(results) == 1

    def test_frontier_disabled_ok(self, settings):
        mock = MagicMock(spec=httpx.Client)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {"total_requests": 0}
        mock.get.side_effect = [tags_response, stats_response]

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["frontier"].ok is True
        assert "disabled" in by_name["frontier"].detail

    def test_frontier_enabled_without_key_warns(self, settings, monkeypatch):
        settings = Settings.model_validate(
            {
                **settings.model_dump(),
                "frontier": {"enabled": True, "model": "gpt-4o-mini"},
            }
        )
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DAARI_FRONTIER_API_KEY", raising=False)

        mock = MagicMock(spec=httpx.Client)
        tags_response = MagicMock()
        tags_response.status_code = 200
        tags_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        stats_response = MagicMock()
        stats_response.status_code = 200
        stats_response.json.return_value = {"total_requests": 0}
        mock.get.side_effect = [tags_response, stats_response]

        results = run_doctor(settings, httpx_client=mock)
        by_name = {r.name: r for r in results}

        assert by_name["frontier"].ok is False
        assert by_name["frontier"].optional is True
        assert doctor_exit_code(results) == 0


class TestCursorSetupDryRun:
    def test_dry_run_returns_plan(self):
        recipe = CursorSetupRecipe()
        plan = recipe.dry_run()
        assert plan.client_id == "cursor"
        assert isinstance(plan.settings_paths, list)
        assert any("Cursor" in p for p in plan.settings_paths)

    def test_registry_has_cursor(self):
        registry = default_registry()
        assert "cursor" in registry.list_ids()
