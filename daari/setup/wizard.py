from __future__ import annotations

import typer

from daari.clients.registry import default_registry
from daari.config.settings import Settings
from daari.setup.doctor import doctor_exit_code, run_doctor
from daari.setup.models import setup_models_interactive


def run_setup_wizard(settings: Settings | None = None) -> None:
    cfg = settings or Settings.load()
    registry = default_registry()
    cursor = registry.get("cursor")

    typer.echo("\n  daari setup — configure your local stack\n")
    typer.echo("  Detected on this machine:")

    ollama_ok = False
    try:
        from daari.setup.models import fetch_ollama_models

        models = fetch_ollama_models(cfg.ollama.base_url)
        ollama_ok = True
        preview = ", ".join(models[:3])
        suffix = "…" if len(models) > 3 else ""
        typer.echo(f"    ✓ Ollama ({len(models)} models: {preview}{suffix})")
    except Exception:
        typer.echo("    ✗ Ollama (not reachable)")

    cursor_detected = cursor.detect() if cursor else False
    typer.echo(f"    {'✓' if cursor_detected else '✗'} Cursor")

    typer.echo("\n  What do you want to set up?")
    typer.echo("    1. Cursor — point AI chat at daari (OpenAI-compat)")
    typer.echo("    2. Local model — choose default model for L3 tier")
    typer.echo("    3. Run health check — daari doctor")
    typer.echo("    4. Skip for now")

    choice = typer.prompt("Enter choice", default="1").strip()

    if choice == "1":
        if not cursor_detected:
            typer.echo("Cursor not detected. Install Cursor or open it once, then re-run.", err=True)
            raise typer.Exit(code=1)
        from daari.cli.setup_actions import apply_cursor_setup

        if typer.confirm(
            f"Configure Cursor to use http://{cfg.server.host}:{cfg.server.port}/v1?",
            default=True,
        ):
            apply_cursor_setup(settings=cfg, dry_run=False, force=False)
        else:
            typer.echo("Skipped Cursor setup.")
    elif choice == "2":
        if not ollama_ok:
            typer.echo("Ollama is not reachable — start Ollama first.", err=True)
            raise typer.Exit(code=1)
        setup_models_interactive(cfg)
    elif choice == "3":
        results = run_doctor(cfg)
        for result in results:
            mark = "✓" if result.ok else "✗"
            suffix = " (optional)" if result.optional else ""
            typer.echo(f"  {mark} {result.name}{suffix}: {result.detail}")
        code = doctor_exit_code(results)
        if code != 0:
            raise typer.Exit(code=code)
    elif choice == "4":
        typer.echo("Nothing to do.")
    else:
        typer.echo("Invalid choice.", err=True)
        raise typer.Exit(code=1)
