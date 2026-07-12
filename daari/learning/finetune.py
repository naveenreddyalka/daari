"""LoRA fine-tune runner wrapping mlx-lm (Phase D2c).

Two-step design so the CLI can show exactly what would run:
`plan_finetune` exports the dataset into a timestamped run directory and
writes run.json; `run_finetune` executes the planned command. mlx-lm is
an optional dependency — daari never requires it, and a missing install
is a clean error with the pip hint.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daari.learning.dataset import export_dataset

DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
DEFAULT_ITERS = 100
DEFAULT_RUNS_ROOT = Path.home() / ".daari" / "training" / "runs"


class FinetuneError(RuntimeError):
    pass


@dataclass
class FinetunePlan:
    run_dir: Path
    model: str
    iters: int
    counts: dict[str, int]
    command: list[str]


def _mlx_lm_available() -> bool:
    return importlib.util.find_spec("mlx_lm") is not None


def _write_run_json(plan: FinetunePlan, status: str) -> None:
    payload: dict[str, Any] = {
        "model": plan.model,
        "iters": plan.iters,
        "counts": plan.counts,
        "command": plan.command,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (plan.run_dir / "run.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plan_finetune(
    store: Any,
    *,
    runs_root: str | Path = DEFAULT_RUNS_ROOT,
    model: str = DEFAULT_MODEL,
    iters: int = DEFAULT_ITERS,
    only_accepted: bool = False,
    min_examples: int = 8,
) -> FinetunePlan:
    """Export the dataset into a run dir and build the mlx_lm command."""
    run_dir = Path(runs_root).expanduser() / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S"
    )
    data_dir = run_dir / "data"
    counts = export_dataset(
        store, data_dir, only_accepted=only_accepted, min_examples=min_examples
    )
    command = [
        "python",
        "-m",
        "mlx_lm",
        "lora",
        "--train",
        "--model",
        model,
        "--data",
        str(data_dir),
        "--iters",
        str(iters),
        "--adapter-path",
        str(run_dir / "adapters"),
    ]
    plan = FinetunePlan(
        run_dir=run_dir, model=model, iters=iters, counts=counts, command=command
    )
    _write_run_json(plan, "planned")
    return plan


def run_finetune(plan: FinetunePlan) -> None:
    if not _mlx_lm_available():
        raise FinetuneError(
            "mlx-lm is not installed — run `pip install mlx-lm` (Apple Silicon)"
            " and retry, or use --dry-run to inspect the command"
        )
    _write_run_json(plan, "running")
    result = subprocess.run(plan.command)
    if result.returncode != 0:
        _write_run_json(plan, "failed")
        raise FinetuneError(f"mlx_lm lora failed with exit code {result.returncode}")
    _write_run_json(plan, "completed")
