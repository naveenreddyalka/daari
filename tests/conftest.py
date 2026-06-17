"""Shared pytest fixtures and markers."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that need live Ollama (set OLLAMA_HOST to run)",
    )
    config.addinivalue_line(
        "markers",
        "benchmark: optional latency tier comparisons (skip with -m 'not benchmark')",
    )


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
