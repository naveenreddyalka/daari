"""Learned routing (Trust PRD Train 4).

A tiny centroid classifier over embeddings of the user's own past prompts
(from the example store) replaces the keyword-heuristic ``categorize()``
when it is confident — RouteLLM-style learned routing, but personal and
fully on-device with no new dependencies. Below the sample floor it never
guesses: the heuristic stays in charge.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from daari.cache.semantic import cosine_similarity

DEFAULT_MODEL_PATH = "~/.daari/learning/router-model.json"
DEFAULT_MIN_SAMPLES = 200
DEFAULT_CONFIDENCE_FLOOR = 0.6


class RouterTrainingError(RuntimeError):
    pass


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"])
    return ""


async def train_router(
    example_store: Any,
    embedder: Any,
    *,
    out_path: str | Path = DEFAULT_MODEL_PATH,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    limit: int = 10_000,
) -> dict[str, Any]:
    """Fit per-category embedding centroids from captured examples."""
    rows = example_store.examples(limit=limit)
    labeled: list[tuple[str, str]] = []
    for row in rows:
        text = _last_user_text(row.get("messages") or [])
        category = row.get("category")
        if text.strip() and category:
            labeled.append((category, text))
    if len(labeled) < min_samples:
        raise RouterTrainingError(
            f"need at least {min_samples} labeled examples, have {len(labeled)}"
        )

    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for category, text in labeled:
        vector = await embedder.embed(text)
        if vector is None:
            continue
        if category not in sums:
            sums[category] = [0.0] * len(vector)
            counts[category] = 0
        if len(vector) != len(sums[category]):
            continue
        sums[category] = [a + b for a, b in zip(sums[category], vector, strict=True)]
        counts[category] += 1

    if not counts or sum(counts.values()) < min_samples:
        raise RouterTrainingError("too few embeddable examples to train")

    model = {
        "version": 1,
        "trained_at": time.time(),
        "samples": sum(counts.values()),
        "categories": {
            category: {
                "centroid": [value / counts[category] for value in sums[category]],
                "count": counts[category],
            }
            for category in sums
        },
    }
    path = Path(out_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model) + "\n")
    return {
        "samples": model["samples"],
        "categories": {c: counts[c] for c in counts},
        "path": str(path),
    }


class LearnedRouter:
    def __init__(
        self,
        path: str | Path = DEFAULT_MODEL_PATH,
        *,
        confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
        min_samples: int = DEFAULT_MIN_SAMPLES,
    ) -> None:
        self.path = Path(path).expanduser()
        self.confidence_floor = confidence_floor
        self.min_samples = min_samples
        self._model: dict[str, Any] | None = None
        self._loaded_mtime: float | None = None

    def _load(self) -> dict[str, Any] | None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        if self._model is not None and self._loaded_mtime == mtime:
            return self._model
        try:
            model = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(model, dict) or not model.get("categories"):
            return None
        self._model = model
        self._loaded_mtime = mtime
        return model

    @property
    def available(self) -> bool:
        model = self._load()
        return model is not None and model.get("samples", 0) >= self.min_samples

    def predict(self, embedding: list[float]) -> tuple[str, float] | None:
        """(category, confidence) or None when the model must not guess."""
        model = self._load()
        if model is None or model.get("samples", 0) < self.min_samples:
            return None
        best: tuple[str, float] | None = None
        second = 0.0
        for category, entry in model["categories"].items():
            centroid = entry.get("centroid")
            if not isinstance(centroid, list):
                continue
            score = cosine_similarity(embedding, centroid)
            if best is None or score > best[1]:
                if best is not None:
                    second = max(second, best[1])
                best = (category, score)
            else:
                second = max(second, score)
        if best is None:
            return None
        # Two gates: absolute similarity must clear the floor, and the margin
        # over the runner-up must be real — ambiguous prompts stay heuristic.
        margin = best[1] - second
        if best[1] < self.confidence_floor or margin < 0.05:
            return None
        return best[0], round(best[1], 4)
