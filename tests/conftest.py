"""Shared pytest fixtures and markers."""

from __future__ import annotations

import pytest

from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings


class NoopEmbedder:
    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        return None


@pytest.fixture(autouse=True)
def isolate_daari_home(tmp_path_factory, monkeypatch):
    """Point `~` at a scratch directory for every test.

    Most defaults live under `~/.daari`, which on a developer machine is also
    where a running `daari serve` keeps its command-context store, L1 cache and
    feedback database. Sharing those made results depend on what the daemon had
    cached — a test could pass alone and fail in a full run for reasons no test
    controlled. Pinning paths in the `settings` fixture is not enough, because
    tests that build their own Settings still pick up the defaults.

    The scratch home lives outside `tmp_path` so tests that assert on the exact
    contents of `tmp_path` keep working.
    """
    home = tmp_path_factory.mktemp("daari-home")
    monkeypatch.setenv("HOME", str(home))
    return home


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
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                # shadow_sample_rate ships at 0.05: one in twenty L1 hits spawns a
                # background re-execution to audit the cached answer. Harmless in
                # production, but it makes any assertion about how many times an
                # executor ran fail one run in twenty. Tests that exercise shadow
                # sampling set the rate themselves.
                "l1": {
                    "enabled": False,
                    "path": str(tmp_path / "l1"),
                    "shadow_sample_rate": 0.0,
                },
            },
            "usage": {"path": str(tmp_path / "usage" / "ledger.sqlite3")},
            "trace": {"path": str(tmp_path / "traces" / "traces.sqlite3")},
            "learning": {
                "path": str(tmp_path / "feedback" / "feedback.sqlite3"),
                "examples_path": str(tmp_path / "training" / "examples.sqlite3"),
                "router_model_path": str(tmp_path / "learning" / "router-model.json"),
            },
            # These three default to ~/.daari and must be pinned too. A locally
            # running `daari serve` writes the command-context store, so sharing
            # it let the daemon's cache decide which tier answered a test.
            "context": {"path": str(tmp_path / "context" / "commands")},
            "server": {
                "host": "127.0.0.1",
                "port": 11435,
                "virtual_keys": {"path": str(tmp_path / "auth" / "virtual-keys.sqlite3")},
            },
            "enterprise": {"audit_path": str(tmp_path / "audit" / "audit.sqlite3")},
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
