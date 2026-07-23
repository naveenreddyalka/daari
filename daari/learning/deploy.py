"""Serve fine-tuned adapters from a D2c run (Phase D roadmap: deploy).

Bridges `daari learn finetune` output to the local executors:

- backend "mlx": mlx_lm.server loads the LoRA adapter directly with
  --adapter-path — no fuse step. The plan carries the serve command plus
  the config.yaml snippet mapping a daari tier to the MLX backend.
- backend "ollama": fuse the adapter into the base weights, export GGUF,
  and `ollama create` a named model a tier can point at.

Same two-step shape as finetune.py: plan_deploy shows exactly what would
run, run_deploy executes it and records status in deploy.json.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TUNED_NAME = "daari-tuned"
GGUF_FILENAME = "ggml-model-f16.gguf"
MLX_SERVER_PORT = 11440

BACKENDS = ("ollama", "mlx")


class DeployError(RuntimeError):
    pass


@dataclass
class DeployPlan:
    run_dir: Path
    backend: str
    base_model: str
    adapter_path: Path
    model_name: str
    commands: list[list[str]]
    config_snippet: str


def _mlx_lm_available() -> bool:
    return importlib.util.find_spec("mlx_lm") is not None


def _read_run(run_dir: Path) -> dict[str, Any]:
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise DeployError(f"{run_dir} has no run.json — is this a `learn finetune` run dir?")
    payload = json.loads(run_json.read_text(encoding="utf-8"))
    if payload.get("status") != "completed":
        raise DeployError(
            f"run status is {payload.get('status')!r}; only completed runs can be deployed"
        )
    return payload


def _write_deploy_json(plan: DeployPlan, status: str) -> None:
    payload = {
        "backend": plan.backend,
        "base_model": plan.base_model,
        "model_name": plan.model_name,
        "commands": plan.commands,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (plan.run_dir / "deploy.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plan_deploy(
    run_dir: str | Path,
    *,
    backend: str = "mlx",
    model_name: str = DEFAULT_TUNED_NAME,
    tier: str = "L3",
) -> DeployPlan:
    if backend not in BACKENDS:
        raise DeployError(f"unknown backend {backend!r} (expected one of {BACKENDS})")
    run_dir = Path(run_dir).expanduser()
    run = _read_run(run_dir)
    base_model = run["model"]
    adapter_path = run_dir / "adapters"
    if not adapter_path.exists():
        raise DeployError(f"no adapters at {adapter_path} — did the fine-tune complete?")

    if backend == "mlx":
        commands = [
            [
                "python",
                "-m",
                "mlx_lm",
                "server",
                "--model",
                base_model,
                "--adapter-path",
                str(adapter_path),
                "--port",
                str(MLX_SERVER_PORT),
            ]
        ]
        config_snippet = (
            "mlx:\n"
            "  enabled: true\n"
            f"  base_url: http://127.0.0.1:{MLX_SERVER_PORT}\n"
            "  models:\n"
            f"    {tier}: {base_model}\n"
        )
    else:
        fused_dir = run_dir / "fused"
        modelfile = run_dir / "Modelfile"
        modelfile.write_text(f"FROM {fused_dir / GGUF_FILENAME}\n", encoding="utf-8")
        commands = [
            [
                "python",
                "-m",
                "mlx_lm",
                "fuse",
                "--model",
                base_model,
                "--adapter-path",
                str(adapter_path),
                "--save-path",
                str(fused_dir),
                "--export-gguf",
            ],
            ["ollama", "create", model_name, "-f", str(modelfile)],
        ]
        config_snippet = f"models:\n  {tier.lower()}: {model_name}\n"

    plan = DeployPlan(
        run_dir=run_dir,
        backend=backend,
        base_model=base_model,
        adapter_path=adapter_path,
        model_name=model_name,
        commands=commands,
        config_snippet=config_snippet,
    )
    _write_deploy_json(plan, "planned")
    return plan


def run_deploy(plan: DeployPlan) -> None:
    """Execute the plan. Only the ollama backend has one-shot steps; the MLX
    server is long-running, so that backend stays plan-and-print."""
    if plan.backend == "mlx":
        raise DeployError(
            "the MLX server is long-running — start it yourself:\n  "
            + " ".join(plan.commands[0])
            + "\nthen add the printed config snippet to ~/.daari/config.yaml"
        )
    if not _mlx_lm_available():
        raise DeployError(
            "mlx-lm is not installed — run `pip install mlx-lm` (Apple Silicon) and retry"
        )
    if shutil.which("ollama") is None:
        raise DeployError("ollama binary not found on PATH")
    _write_deploy_json(plan, "running")
    for command in plan.commands:
        result = subprocess.run(command)
        if result.returncode != 0:
            _write_deploy_json(plan, "failed")
            raise DeployError(
                f"`{' '.join(command[:3])}` failed with exit code {result.returncode}"
            )
    _write_deploy_json(plan, "completed")
