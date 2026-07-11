from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml

from daari.config.settings import Settings


@dataclass
class ModelSetupResult:
    tier: str | None
    model: str | None
    config_path: Path
    changed: bool


def fetch_ollama_models(base_url: str, *, client: httpx.Client | None = None) -> list[str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    own_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        names = [str(item.get("name", "")) for item in data.get("models", [])]
        return sorted(name for name in names if name)
    finally:
        if own_client:
            http.close()


def model_present(model: str, available: list[str]) -> bool:
    return any(name == model or name.startswith(f"{model}:") for name in available)


def l4_model_present(base_url: str, model: str, *, client: httpx.Client | None = None) -> bool | None:
    """True/False if we could check, None when Ollama is unreachable."""
    try:
        available = fetch_ollama_models(base_url, client=client)
    except Exception:
        return None
    return model_present(model, available)


def pull_ollama_model(model: str) -> bool:
    """Run `ollama pull <model>` (streams progress to the terminal)."""
    import subprocess

    try:
        return subprocess.run(["ollama", "pull", model], check=False).returncode == 0
    except OSError:
        return False


def write_models_config(
    model: str | None = None,
    *,
    tier: str = "l3",
    prefer: str | None = None,
    weights: dict[str, dict[str, float]] | None = None,
    config_path: Path | None = None,
) -> ModelSetupResult:
    path = config_path or Path.home() / ".daari" / "config.yaml"
    current: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                current = loaded

    models = current.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        current["models"] = models

    changed = False
    if model is not None:
        previous = models.get(tier)
        changed = previous != model
        models[tier] = model

    routing = current.setdefault("routing", {})
    if not isinstance(routing, dict):
        routing = {}
        current["routing"] = routing
    if prefer is not None:
        prev_prefer = routing.get("prefer")
        changed = changed or prev_prefer != prefer
        routing["prefer"] = prefer

    if weights is not None:
        model_weights = models.setdefault("weights", {})
        if not isinstance(model_weights, dict):
            model_weights = {}
            models["weights"] = model_weights
        changed = changed or model_weights != weights
        models["weights"] = weights

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(current, handle, default_flow_style=False, sort_keys=False)

    return ModelSetupResult(tier=tier if model is not None else None, model=model, config_path=path, changed=changed)


def setup_models_interactive(
    settings: Settings | None = None,
    *,
    tier: str = "l3",
    model: str | None = None,
    list_only: bool = False,
    config_path: Path | None = None,
    httpx_client: httpx.Client | None = None,
) -> ModelSetupResult | None:
    cfg = settings or Settings.load()
    path = config_path or Path.home() / ".daari" / "config.yaml"

    if list_only:
        current = cfg.models.l3 if tier == "l3" else cfg.models.l4 if tier == "l4" else getattr(cfg.models, tier, None)
        typer.echo(f"Tier map ({path}):")
        typer.echo(f"  l3: {cfg.models.l3}")
        typer.echo(f"  l4: {cfg.models.l4}")
        typer.echo(f"  routing.prefer: {cfg.routing.prefer}")
        return None

    if model is not None:
        result = write_models_config(model, tier=tier, config_path=path)
        typer.echo(f"Set models.{tier} = {model} in {path}")
        return result

    try:
        available = fetch_ollama_models(cfg.ollama.base_url, client=httpx_client)
    except Exception as exc:
        typer.echo(f"Could not reach Ollama at {cfg.ollama.base_url}: {exc}", err=True)
        typer.echo("Hint: start Ollama and run `ollama pull llama3.2:3b`", err=True)
        raise typer.Exit(code=1) from exc

    if not available:
        typer.echo("No models found via `ollama list`.", err=True)
        typer.echo("Hint: run `ollama pull llama3.2:3b`", err=True)
        raise typer.Exit(code=1)

    typer.echo("Available Ollama models:")
    for index, name in enumerate(available, start=1):
        typer.echo(f"  {index}. {name}")

    default_index = 1
    current = cfg.models.l3 if tier == "l3" else cfg.models.l4 if tier == "l4" else None
    if current in available:
        default_index = available.index(current) + 1

    choice = typer.prompt(
        f"Pick default model for {tier.upper()} tier",
        default=str(default_index),
    )
    try:
        picked = available[int(choice) - 1]
    except (ValueError, IndexError) as exc:
        typer.echo("Invalid selection.", err=True)
        raise typer.Exit(code=1) from exc

    prefer = typer.prompt("Routing preference (latency|accuracy|balanced)", default=cfg.routing.prefer)
    if prefer not in {"latency", "accuracy", "balanced"}:
        typer.echo("Invalid preference; expected latency, accuracy, or balanced.", err=True)
        raise typer.Exit(code=1)

    existing_weights = cfg.models.weights or {}
    if picked not in existing_weights:
        # Lightweight default so configured models are always scoreable.
        existing_weights[picked] = {"latency": 0.5, "accuracy": 0.5}

    result = write_models_config(
        picked,
        tier=tier,
        prefer=prefer,
        weights=existing_weights,
        config_path=path,
    )
    typer.echo(f"Wrote models.{tier} = {picked} to {path}")
    typer.echo(f"Wrote routing.prefer = {prefer} to {path}")
    return result
