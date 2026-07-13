"""Hardware-aware model profiling and warm-model tracking (Trust PRD Train 3).

``daari profile`` benchmarks each installed local model once on the user's
actual hardware and stores tokens/sec, wall latency, and load time locally.
The router consults the stored profile to enforce latency budgets, and a
small TTL-cached ``/api/ps`` tracker lets tier selection prefer models that
are already loaded in Ollama (avoiding multi-second cold-load stalls).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_PROFILE_PATH = "~/.daari/profile/models.json"
_BENCH_PROMPT = "Reply with exactly one short sentence: what is 2+2?"


class ModelProfileStore:
    def __init__(self, path: str | Path = DEFAULT_PROFILE_PATH) -> None:
        self.path = Path(path).expanduser()

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, profiles: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, indent=2) + "\n")

    def latency_ms_for(self, model: str) -> float | None:
        entry = self.load().get(model)
        if not isinstance(entry, dict):
            return None
        latency = entry.get("latency_ms")
        return float(latency) if isinstance(latency, (int, float)) else None


async def benchmark_model(
    base_url: str,
    model: str,
    *,
    timeout: float = 120.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any] | None:
    """One short generation; Ollama's own timings give tokens/sec + load."""
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
        ) as client:
            response = await client.post(
                "/api/generate",
                json={"model": model, "prompt": _BENCH_PROMPT, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    wall_ms = (time.perf_counter() - started) * 1000
    eval_count = data.get("eval_count") or 0
    eval_duration_ns = data.get("eval_duration") or 0
    load_duration_ns = data.get("load_duration") or 0
    tokens_per_second = (
        eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else None
    )
    return {
        "latency_ms": round(wall_ms, 1),
        "load_ms": round(load_duration_ns / 1e6, 1),
        "tokens_per_second": round(tokens_per_second, 2) if tokens_per_second else None,
        "eval_tokens": eval_count,
        "measured_at": time.time(),
    }


async def benchmark_models(
    base_url: str,
    models: list[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for model in models:
        entry = await benchmark_model(base_url, model, transport=transport)
        if entry is not None:
            results[model] = entry
    return results


class WarmModelTracker:
    """TTL-cached view of which models Ollama currently has loaded."""

    def __init__(
        self,
        base_url: str,
        *,
        ttl_seconds: float = 5.0,
        timeout: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.ttl_seconds = ttl_seconds
        self.timeout = timeout
        self._transport = transport
        self._clock = clock or time.monotonic
        self._warm: set[str] = set()
        self._fetched_at: float | None = None

    def get(self) -> set[str]:
        """Last known warm set — never blocks."""
        return set(self._warm)

    async def refresh(self) -> set[str]:
        now = self._clock()
        if self._fetched_at is not None and now - self._fetched_at < self.ttl_seconds:
            return self.get()
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.get("/api/ps")
                response.raise_for_status()
                data = response.json()
            models = data.get("models") or []
            self._warm = {
                entry.get("name") or entry.get("model")
                for entry in models
                if isinstance(entry, dict) and (entry.get("name") or entry.get("model"))
            }
        except (httpx.HTTPError, ValueError):
            self._warm = set()
        self._fetched_at = now
        return self.get()
