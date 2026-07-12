"""Export captured examples as an mlx-lm chat dataset (Phase D2b).

Each JSONL line is {"messages": [...prompt turns..., assistant completion]}
— the chat format `mlx_lm lora --data DIR` consumes (train.jsonl +
valid.jsonl). The train/valid split hashes trace_id so re-exports are
stable and an example never migrates between splits.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DatasetError(RuntimeError):
    pass


def _split_bucket(example: dict[str, Any]) -> float:
    key = example.get("trace_id") or json.dumps(example["messages"], sort_keys=True)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def export_dataset(
    store: Any,
    out_dir: str | Path,
    *,
    only_accepted: bool = False,
    split: float = 0.9,
    min_examples: int = 8,
    limit: int = 100_000,
) -> dict[str, int]:
    """Write train.jsonl/valid.jsonl; returns {"train": n, "valid": m}."""
    examples = store.examples(limit=limit, only_accepted=only_accepted)
    if len(examples) < min_examples:
        source = "accepted examples" if only_accepted else "examples"
        raise DatasetError(
            f"need at least {min_examples} {source} to export, found {len(examples)}"
            " — keep learning.capture_examples on and accept good answers"
        )

    train_rows: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    # Oldest-first so the file order is chronological.
    for example in reversed(examples):
        row = {
            "messages": [
                *example["messages"],
                {"role": "assistant", "content": example["completion"]},
            ]
        }
        bucket = valid_rows if _split_bucket(example) >= split else train_rows
        bucket.append(row)

    # mlx_lm requires a non-empty valid set; borrow from train when the
    # hash split leaves it empty.
    if not valid_rows and train_rows:
        valid_rows.append(train_rows.pop())

    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train_rows), ("valid.jsonl", valid_rows)):
        with (out / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"train": len(train_rows), "valid": len(valid_rows)}
