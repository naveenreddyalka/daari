from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml

from daari.config.settings import Settings

# Recursive Flint — optional L4 coding MoE (Ollama ≥ 0.40.9; Linux/Windows/macOS) (#1852 / #1887).
FLINT_MODEL = "flint"
FLINT_OLLAMA_FLOOR = (0, 40, 9)
FLINT_RECIPE_NOTE = (
    "Optional Flint L4 coding recipe (models.l4=flint). Requires Ollama ≥ 0.40.9 "
    "on Linux, Windows, and macOS. Pull with: ollama pull flint"
)

# Nemotron 3.5 Bolt E4B — optional local VLM (Ollama ≥ 0.40.10) (#1893).
NEMOTRON_BOLT_MODEL = "nemotron-3.5-bolt:e4b"
NEMOTRON_BOLT_OLLAMA_FLOOR = (0, 40, 10)
NEMOTRON_BOLT_RECIPE_NOTE = (
    "Optional Nemotron 3.5 Bolt E4B L3 VLM recipe "
    f"(models.l3={NEMOTRON_BOLT_MODEL}). Requires Ollama ≥ 0.40.10. "
    f"Pull with: ollama pull {NEMOTRON_BOLT_MODEL}"
)

# Liquid AI LFM3 — optional 256K local agent L3 (Ollama ≥ 0.40.12; GA on all OS in 0.40.13) (#1984, #2012).
LFM3_MODEL = "lfm3"
LFM3_OLLAMA_FLOOR = (0, 40, 12)
LFM3_RECIPE_NOTE = (
    "Optional LFM3 L3 local-agent recipe "
    f"(models.l3={LFM3_MODEL}, 256K context). Requires Ollama ≥ 0.40.12. "
    "Linux/Windows/macOS with Ollama ≥ 0.40.13 (Apple from 0.40.12). "
    f"Pull with: ollama pull {LFM3_MODEL}"
)

# Liquid AI LFM3-VL — optional multimodal L4 vision (Ollama ≥ 0.40.12; Apple-first) (#2006).
LFM3_VL_MODEL = "lfm3-vl"
LFM3_VL_OLLAMA_FLOOR = (0, 40, 12)
LFM3_VL_RECIPE_NOTE = (
    "Optional LFM3-VL L4 vision recipe "
    f"(models.l4={LFM3_VL_MODEL}). Requires Ollama ≥ 0.40.12. "
    "Apple hardware first in 0.40.12; Linux/Windows support coming soon. "
    f"Pull with: ollama pull {LFM3_VL_MODEL}"
)

# Liquid AI LFM3-Omni — optional local speech (TTS/ASR) via Ollama /v1 (#2037).
# Primary path: wire tts+asr to ollama.base_url/v1 with model=lfm3-omni.
# Optional: also set models.l4=lfm3-omni for native chat audio/vision routing.
LFM3_OMNI_MODEL = "lfm3-omni"
LFM3_OMNI_OLLAMA_FLOOR = (0, 40, 13)
LFM3_OMNI_RECIPE_NOTE = (
    "Optional LFM3-Omni speech recipe (primary): sets tts/asr base_url to "
    f"ollama.base_url/v1 and tts/asr.model={LFM3_OMNI_MODEL} without pulling "
    "weights. Requires Ollama ≥ 0.40.13 on Linux/Windows/macOS. "
    f"Optional chat path: also set models.l4={LFM3_OMNI_MODEL} for native "
    "vision+audio routing. "
    f"Pull with: ollama pull {LFM3_OMNI_MODEL}"
)

# gpt-oss-safeguard — optional local bring-your-own-policy decision guardrail (#2032).
SAFEGUARD_TAG = "gpt-oss-safeguard"
SAFEGUARD_MODEL = "gpt-oss-safeguard:20b"
SAFEGUARD_RULE_NAME = "byo_policy"
SAFEGUARD_SAMPLE_STATEMENT = (
    "Does this content violate the operator's written Trust & Safety policy? "
    "Replace this statement with your policy question/instructions."
)
SAFEGUARD_RECIPE_NOTE = (
    "Optional gpt-oss-safeguard decision-guardrail recipe "
    f"(writes a kind=decision input rule targeting {SAFEGUARD_MODEL}). "
    "VRAM: 20b ≈ 16 GB; 120b needs H100-class hardware. "
    "The rule's statement (question/instructions) carries the operator's "
    "written policy — edit it after apply. "
    f"Pull with: ollama pull {SAFEGUARD_MODEL}"
)


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


@dataclass
class WarmResult:
    model: str
    ok: bool
    detail: str


def configured_warm_models(settings: Settings) -> list[str]:
    """Configured L3–L5 (when set) plus the L1 embed model, de-duplicated."""
    names: list[str] = []
    for attr in ("l3", "l4", "l5"):
        value = getattr(settings.models, attr, None)
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)
    embed = str(getattr(settings.cache.l1, "embedding_model", None) or "").strip()
    if embed and embed not in names:
        names.append(embed)
    return names


def warm_ollama_model(
    base_url: str,
    model: str,
    *,
    embed_model: str | None = None,
    client: httpx.Client | None = None,
    timeout: float = 120.0,
) -> WarmResult:
    """Load one model into Ollama via a short generate or embed noop (#843)."""
    url = base_url.rstrip("/")
    own = client is None
    http = client or httpx.Client(timeout=timeout)
    is_embed = bool(embed_model) and (
        model == embed_model or model.startswith(f"{embed_model}:")
    )
    try:
        if is_embed:
            response = http.post(
                f"{url}/api/embeddings",
                json={"model": model, "prompt": "daari-warm"},
            )
        else:
            response = http.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": "hi",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1},
                },
            )
        if response.status_code >= 400:
            return WarmResult(model=model, ok=False, detail=f"HTTP {response.status_code}")
        return WarmResult(model=model, ok=True, detail="loaded")
    except Exception as exc:  # noqa: BLE001 — report per-model failure
        return WarmResult(model=model, ok=False, detail=str(exc)[:200])
    finally:
        if own:
            http.close()


def warm_configured_models(
    settings: Settings,
    *,
    client: httpx.Client | None = None,
    warm_fn: Any | None = None,
) -> list[WarmResult]:
    """Warm each configured tier + embed model; return per-model results."""
    embed = str(settings.cache.l1.embedding_model or "").strip() or None
    do_warm = warm_fn or (
        lambda model: warm_ollama_model(
            settings.ollama.base_url,
            model,
            embed_model=embed,
            client=client,
        )
    )
    return [do_warm(model) for model in configured_warm_models(settings)]


def apply_flint_l4_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Set ``models.l4`` to Flint without pulling weights (#1852)."""
    path = config_path or Path.home() / ".daari" / "config.yaml"
    if dry_run:
        current_l4: str | None = None
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                models = loaded.get("models") or {}
                if isinstance(models, dict):
                    raw = models.get("l4")
                    current_l4 = str(raw) if raw is not None else None
        changed = current_l4 != FLINT_MODEL
        return ModelSetupResult(
            tier="l4",
            model=FLINT_MODEL,
            config_path=path,
            changed=changed,
        )
    return write_models_config(FLINT_MODEL, tier="l4", config_path=path)


def apply_nemotron_bolt_l3_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Set ``models.l3`` to Nemotron Bolt E4B without pulling weights (#1893)."""
    path = config_path or Path.home() / ".daari" / "config.yaml"
    if dry_run:
        current_l3: str | None = None
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                models = loaded.get("models") or {}
                if isinstance(models, dict):
                    raw = models.get("l3")
                    current_l3 = str(raw) if raw is not None else None
        changed = current_l3 != NEMOTRON_BOLT_MODEL
        return ModelSetupResult(
            tier="l3",
            model=NEMOTRON_BOLT_MODEL,
            config_path=path,
            changed=changed,
        )
    return write_models_config(NEMOTRON_BOLT_MODEL, tier="l3", config_path=path)


def apply_lfm3_l3_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Set ``models.l3`` to LFM3 without pulling weights (#1984)."""
    path = config_path or Path.home() / ".daari" / "config.yaml"
    if dry_run:
        current_l3: str | None = None
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                models = loaded.get("models") or {}
                if isinstance(models, dict):
                    raw = models.get("l3")
                    current_l3 = str(raw) if raw is not None else None
        changed = current_l3 != LFM3_MODEL
        return ModelSetupResult(
            tier="l3",
            model=LFM3_MODEL,
            config_path=path,
            changed=changed,
        )
    return write_models_config(LFM3_MODEL, tier="l3", config_path=path)


def apply_lfm3_vl_l4_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Set ``models.l4`` to LFM3-VL without pulling weights (#2006)."""
    path = config_path or Path.home() / ".daari" / "config.yaml"
    if dry_run:
        current_l4: str | None = None
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                models = loaded.get("models") or {}
                if isinstance(models, dict):
                    raw = models.get("l4")
                    current_l4 = str(raw) if raw is not None else None
        changed = current_l4 != LFM3_VL_MODEL
        return ModelSetupResult(
            tier="l4",
            model=LFM3_VL_MODEL,
            config_path=path,
            changed=changed,
        )
    return write_models_config(LFM3_VL_MODEL, tier="l4", config_path=path)


def _ollama_v1_base(config: dict[str, Any]) -> str:
    ollama = config.get("ollama") if isinstance(config.get("ollama"), dict) else {}
    raw = str((ollama or {}).get("base_url") or "http://127.0.0.1:11434").strip().rstrip("/")
    return f"{raw}/v1"


def _speech_already_omni(config: dict[str, Any]) -> bool:
    tip_url = _ollama_v1_base(config)
    for key in ("tts", "asr"):
        block = config.get(key)
        if not isinstance(block, dict):
            return False
        base = str(block.get("base_url") or "").strip().rstrip("/")
        model = str(block.get("model") or "").strip()
        if base != tip_url.rstrip("/"):
            return False
        if model != LFM3_OMNI_MODEL and not model.startswith(f"{LFM3_OMNI_MODEL}:"):
            return False
    return True


def apply_lfm3_omni_speech_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Wire tts/asr to Ollama ``/v1`` + ``lfm3-omni`` without pulling weights (#2037).

    Primary path is speech (TTS/ASR). Optional chat path (``models.l4``) is
    documented in ``LFM3_OMNI_RECIPE_NOTE`` and left to the operator.
    """
    path = config_path or Path.home() / ".daari" / "config.yaml"
    current: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, dict):
            current = loaded

    already = _speech_already_omni(current)
    if dry_run or already:
        return ModelSetupResult(
            tier=None,
            model=LFM3_OMNI_MODEL,
            config_path=path,
            changed=not already,
        )

    tip_url = _ollama_v1_base(current)
    for key in ("tts", "asr"):
        block = current.get(key)
        if not isinstance(block, dict):
            block = {}
            current[key] = block
        block["base_url"] = tip_url
        block["model"] = LFM3_OMNI_MODEL

    # Declare chat capabilities when operators later set models.l4=lfm3-omni.
    models = current.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        current["models"] = models
    caps = models.setdefault("capabilities", {})
    if not isinstance(caps, dict):
        caps = {}
        models["capabilities"] = caps
    caps[LFM3_OMNI_MODEL] = ["tools", "json", "vision", "audio"]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(current, handle, default_flow_style=False, sort_keys=False)

    return ModelSetupResult(
        tier=None,
        model=LFM3_OMNI_MODEL,
        config_path=path,
        changed=True,
    )


def _safeguard_rule_present(current: dict[str, Any]) -> bool:
    guardrails = current.get("guardrails")
    if not isinstance(guardrails, dict):
        return False
    for key in ("input_rules", "output_rules"):
        rows = guardrails.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("kind") or "").strip().lower() != "decision":
                continue
            model = str(row.get("model") or "").strip()
            if model == SAFEGUARD_MODEL or model.startswith(f"{SAFEGUARD_TAG}:"):
                return True
            if model == SAFEGUARD_TAG:
                return True
    return False


def apply_safeguard_recipe(
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> ModelSetupResult:
    """Write a sample kind=decision guardrail targeting gpt-oss-safeguard (#2032).

    Does not pull weights. The rule's ``statement`` is the operator's written
    policy question/instructions (edit after apply).
    """
    path = config_path or Path.home() / ".daari" / "config.yaml"
    current: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if isinstance(loaded, dict):
            current = loaded

    already = _safeguard_rule_present(current)
    if dry_run or already:
        return ModelSetupResult(
            tier=None,
            model=SAFEGUARD_MODEL,
            config_path=path,
            changed=not already,
        )

    guardrails = current.setdefault("guardrails", {})
    if not isinstance(guardrails, dict):
        guardrails = {}
        current["guardrails"] = guardrails
    guardrails["enabled"] = True
    input_rules = guardrails.get("input_rules")
    if not isinstance(input_rules, list):
        input_rules = []
        guardrails["input_rules"] = input_rules
    input_rules.append(
        {
            "name": SAFEGUARD_RULE_NAME,
            "kind": "decision",
            "statement": SAFEGUARD_SAMPLE_STATEMENT,
            "threshold": 0.7,
            "model": SAFEGUARD_MODEL,
            "action": "block",
            "on_error": "warn",
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(current, handle, default_flow_style=False, sort_keys=False)

    return ModelSetupResult(
        tier=None,
        model=SAFEGUARD_MODEL,
        config_path=path,
        changed=True,
    )


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
    flint: bool = False,
    nemotron_bolt: bool = False,
    lfm3: bool = False,
    lfm3_vl: bool = False,
    lfm3_omni: bool = False,
    safeguard: bool = False,
    dry_run: bool = False,
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

    if flint:
        typer.echo(FLINT_RECIPE_NOTE)
        result = apply_flint_l4_recipe(config_path=path, dry_run=dry_run)
        if dry_run:
            typer.echo(f"Dry-run: would set models.l4 = {FLINT_MODEL} in {path}")
        else:
            typer.echo(f"Set models.l4 = {FLINT_MODEL} in {path}")
        return result

    if nemotron_bolt:
        typer.echo(NEMOTRON_BOLT_RECIPE_NOTE)
        result = apply_nemotron_bolt_l3_recipe(config_path=path, dry_run=dry_run)
        if dry_run:
            typer.echo(f"Dry-run: would set models.l3 = {NEMOTRON_BOLT_MODEL} in {path}")
        else:
            typer.echo(f"Set models.l3 = {NEMOTRON_BOLT_MODEL} in {path}")
        return result

    if lfm3:
        typer.echo(LFM3_RECIPE_NOTE)
        result = apply_lfm3_l3_recipe(config_path=path, dry_run=dry_run)
        if dry_run:
            typer.echo(f"Dry-run: would set models.l3 = {LFM3_MODEL} in {path}")
        else:
            typer.echo(f"Set models.l3 = {LFM3_MODEL} in {path}")
        return result

    if lfm3_vl:
        typer.echo(LFM3_VL_RECIPE_NOTE)
        result = apply_lfm3_vl_l4_recipe(config_path=path, dry_run=dry_run)
        if dry_run:
            typer.echo(f"Dry-run: would set models.l4 = {LFM3_VL_MODEL} in {path}")
        else:
            typer.echo(f"Set models.l4 = {LFM3_VL_MODEL} in {path}")
        return result

    if lfm3_omni:
        typer.echo(LFM3_OMNI_RECIPE_NOTE)
        result = apply_lfm3_omni_speech_recipe(config_path=path, dry_run=dry_run)
        tip = _ollama_v1_base({})
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle) or {}
            if isinstance(loaded, dict):
                tip = _ollama_v1_base(loaded)
        if dry_run:
            typer.echo(
                f"Dry-run: would set tts/asr base_url={tip} "
                f"model={LFM3_OMNI_MODEL} in {path}"
            )
        else:
            typer.echo(
                f"Set tts/asr base_url={tip} model={LFM3_OMNI_MODEL} in {path}"
            )
        return result

    if safeguard:
        typer.echo(SAFEGUARD_RECIPE_NOTE)
        result = apply_safeguard_recipe(config_path=path, dry_run=dry_run)
        if dry_run:
            typer.echo(
                f"Dry-run: would write kind=decision guardrail "
                f"(model={SAFEGUARD_MODEL}) in {path}"
            )
        else:
            typer.echo(
                f"Wrote kind=decision guardrail (model={SAFEGUARD_MODEL}) in {path}"
            )
        return result

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

    if tier == "l3" and picked not in {NEMOTRON_BOLT_MODEL, LFM3_MODEL}:
        typer.echo(NEMOTRON_BOLT_RECIPE_NOTE)
        if typer.confirm(
            f"Apply optional Nemotron Bolt E4B L3 VLM recipe "
            f"(set models.l3={NEMOTRON_BOLT_MODEL})?",
            default=False,
        ):
            result = apply_nemotron_bolt_l3_recipe(config_path=path, dry_run=False)
            typer.echo(f"Set models.l3 = {NEMOTRON_BOLT_MODEL} in {path}")
        else:
            typer.echo(LFM3_RECIPE_NOTE)
            if typer.confirm(
                f"Apply optional LFM3 L3 local-agent recipe "
                f"(set models.l3={LFM3_MODEL})?",
                default=False,
            ):
                result = apply_lfm3_l3_recipe(config_path=path, dry_run=False)
                typer.echo(f"Set models.l3 = {LFM3_MODEL} in {path}")
    if tier == "l4" and picked not in {FLINT_MODEL, LFM3_VL_MODEL}:
        typer.echo(FLINT_RECIPE_NOTE)
        if typer.confirm(
            f"Apply optional Flint L4 coding recipe (set models.l4={FLINT_MODEL})?",
            default=False,
        ):
            result = apply_flint_l4_recipe(config_path=path, dry_run=False)
            typer.echo(f"Set models.l4 = {FLINT_MODEL} in {path}")
        else:
            typer.echo(LFM3_VL_RECIPE_NOTE)
            if typer.confirm(
                f"Apply optional LFM3-VL L4 vision recipe "
                f"(set models.l4={LFM3_VL_MODEL})?",
                default=False,
            ):
                result = apply_lfm3_vl_l4_recipe(config_path=path, dry_run=False)
                typer.echo(f"Set models.l4 = {LFM3_VL_MODEL} in {path}")
    return result
