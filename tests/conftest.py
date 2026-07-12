"""Shared pytest fixtures and markers."""

from __future__ import annotations

import pytest

from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings


class NoopEmbedder:
    async def embed(self, text: str) -> list[float] | None:
        return None


@pytest.fixture
def semantic_cache_disabled(tmp_path):
    return SemanticCache(
        path=str(tmp_path / "l1"),
        embedder=NoopEmbedder(),
        enabled=False,
    )


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
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
            "usage": {"path": str(tmp_path / "usage" / "ledger.sqlite3")},
            "trace": {"path": str(tmp_path / "traces" / "traces.sqlite3")},
            "learning": {"path": str(tmp_path / "feedback" / "feedback.sqlite3")},
        }
    )


META_HEADERS = {"X-Daari-Meta": "true"}

# Confidence heuristic skips escalation when content length > 10 chars.
MOCK_MODEL_CONTENT = "mock model response with enough length"


def mock_all_ollama_executors(monkeypatch, router, fake_execute) -> None:
    seen: set[int] = set()
    for attr in ("ollama_l3", "ollama_l4", "ollama_l5", "ollama"):
        executor = getattr(router, attr, None)
        if executor is None or id(executor) in seen:
            continue
        seen.add(id(executor))
        monkeypatch.setattr(executor, "execute", fake_execute)
