from __future__ import annotations

import json

import typer
import uvicorn

from daari.cli.setup_actions import apply_cursor_setup
from daari.config.settings import get_settings
from daari.setup.doctor import doctor_exit_code, run_doctor
from daari.setup.models import setup_models_interactive
from daari.setup.wizard import run_setup_wizard

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


@setup_app.callback(invoke_without_command=True)
def setup_main(
    ctx: typer.Context,
    undo: str | None = typer.Option(
        None,
        "--undo",
        metavar="TOOL",
        help="Restore the latest backup for a setup tool.",
    ),
) -> None:
    """Interactive setup wizard, or undo a previous setup."""
    if undo:
        from daari.clients.registry import default_registry

        registry = default_registry()
        recipe = registry.get(undo)
        if recipe is None:
            typer.echo(f"Unknown setup tool: {undo}", err=True)
            raise typer.Exit(code=1)
        try:
            result = recipe.undo()
        except FileNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"Restored backup from {result.backup_dir}")
        for path in result.files_restored:
            typer.echo(f"  - {path}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        run_setup_wizard()


@setup_app.command("cursor")
def setup_cursor(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show planned changes without writing files.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-apply even when already configured.",
    ),
) -> None:
    """Configure Cursor to use the daari OpenAI-compat gateway."""
    apply_cursor_setup(dry_run=dry_run, force=force)


@setup_app.command("models")
def setup_models(
    tier: str = typer.Option("l3", "--tier", help="Model tier to configure."),
    model: str | None = typer.Option(None, "--model", help="Model name (non-interactive)."),
    list_models: bool = typer.Option(False, "--list", help="Show current tier map."),
) -> None:
    """Pick an Ollama model for a daari tier."""
    setup_models_interactive(get_settings(), tier=tier, model=model, list_only=list_models)


if __name__ == "__main__":
    app()
