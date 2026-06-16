from __future__ import annotations

import json

import typer
import uvicorn

from daari.clients.registry import default_registry
from daari.config.settings import Settings, get_settings
from daari.setup.doctor import doctor_exit_code, run_doctor

app = typer.Typer(
    name="daari",
    help="Local-first execution router — cache before cloud.",
    no_args_is_help=True,
)

setup_app = typer.Typer(help="Configure client integrations.")
app.add_typer(setup_app, name="setup")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
) -> None:
    """Start the daari HTTP daemon."""
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    typer.echo(f"daari serving on http://{bind_host}:{bind_port}/v1")
    uvicorn.run(
        "daari.server.app:create_app",
        factory=True,
        host=bind_host,
        port=bind_port,
        log_level="info",
    )


@app.command()
def stats(
    host: str | None = typer.Option(None, help="Daemon host"),
    port: int | None = typer.Option(None, help="Daemon port"),
) -> None:
    """Show tier counters from the running daemon."""
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    url = f"http://{bind_host}:{bind_port}/v1/daari/stats"
    try:
        import httpx

        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        typer.echo(json.dumps(response.json(), indent=2))
    except Exception as exc:
        typer.echo(f"Could not reach daari at {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def doctor() -> None:
    """Verify Python, config, Ollama, model, and optional daemon."""
    settings = get_settings()
    results = run_doctor(settings)
    for result in results:
        mark = "✓" if result.ok else "✗"
        suffix = " (optional)" if result.optional else ""
        typer.echo(f"  {mark} {result.name}{suffix}: {result.detail}")
    code = doctor_exit_code(results)
    if code != 0:
        raise typer.Exit(code=code)


@setup_app.command("cursor")
def setup_cursor(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show planned changes without writing files.",
    ),
) -> None:
    """Configure Cursor to use the daari OpenAI-compat gateway."""
    settings = get_settings()
    registry = default_registry()
    recipe = registry.get("cursor")
    if recipe is None:
        typer.echo("Cursor setup recipe not found.", err=True)
        raise typer.Exit(code=1)

    base_url = f"http://{settings.server.host}:{settings.server.port}/v1"
    plan = recipe.dry_run(base_url=base_url, api_key="daari-local", model_name="daari")

    typer.echo(f"Cursor detected: {'yes' if plan.detected else 'no'}")
    typer.echo("Settings paths:")
    for path in plan.settings_paths:
        typer.echo(f"  - {path}")

    if plan.changes:
        typer.echo("\nPlanned changes:")
        for change in plan.changes:
            typer.echo(f"  [{change.action}] {change.path}")
            typer.echo(f"    {change.detail}")

    if plan.notes:
        typer.echo("\nNotes:")
        for note in plan.notes:
            typer.echo(f"  - {note}")

    if dry_run:
        typer.echo("\nDry-run complete — no files modified.")
        return

    typer.echo(
        "\nAutomated patching not implemented yet. Use --dry-run to preview, "
        "or follow docs/setup/cursor.md for manual setup.",
        err=True,
    )
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
