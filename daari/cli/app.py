from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import typer
import uvicorn

from daari.cli.setup_actions import apply_all_setups, apply_cursor_setup, apply_intellij_setup
from daari.config.settings import get_settings
from daari.server.app import create_app
from daari.setup.context import clear_context_caches
from daari.setup.doctor import doctor_exit_code, run_doctor
from daari.setup.models import setup_models_interactive
from daari.setup.openai_compat import setup_frontier_key_hint, setup_openai_compat
from daari.setup.wizard import run_setup_wizard

app = typer.Typer(
    name="daari",
    help="Local-first execution router — cache before cloud.",
    no_args_is_help=True,
)

setup_app = typer.Typer(help="Configure client integrations.")
context_app = typer.Typer(help="Manage daari caches and context.")
app.add_typer(setup_app, name="setup")
app.add_typer(context_app, name="context")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
    no_frontier: bool = typer.Option(False, "--no-frontier", help="Disable L6 escalation."),
) -> None:
    """Start the daari HTTP daemon."""
    settings = get_settings().model_copy(deep=True)
    if no_frontier:
        settings.frontier.enabled = False
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    typer.echo(f"daari serving on http://{bind_host}:{bind_port}/v1")
    app_instance = create_app(settings)
    uvicorn.run(
        app_instance,
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


@app.command("install")
def install(
    run_doctor: bool = typer.Option(True, "--run-doctor/--no-run-doctor", help="Run doctor at end."),
    pull_l4: bool = typer.Option(False, "--pull-l4", help="Also pull optional L4 model."),
    pull_l5: bool = typer.Option(False, "--pull-l5", help="Also pull optional L5 model."),
) -> None:
    """Typer wrapper for install.sh parity."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "install.sh"
    if not script.is_file():
        typer.echo(f"install script not found at {script}", err=True)
        raise typer.Exit(code=1)

    env = dict(
        **{
            "RUN_DOCTOR": "1" if run_doctor else "0",
            "PULL_L4": "1" if pull_l4 else "0",
            "PULL_L5": "1" if pull_l5 else "0",
        }
    )
    merged_env = {**os.environ, **env}
    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=str(repo_root),
        env=merged_env,
        check=False,
    )
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


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


@setup_app.command("intellij")
def setup_intellij(
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
    """Configure IntelliJ helpers for daari OpenAI-compatible setup."""
    apply_intellij_setup(dry_run=dry_run, force=force)


@setup_app.command("all")
def setup_all(
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
    """Detect installed clients and apply all relevant setup recipes."""
    apply_all_setups(dry_run=dry_run, force=force)


@setup_app.command("models")
def setup_models(
    tier: str = typer.Option("l3", "--tier", help="Model tier to configure (l3|l4)."),
    model: str | None = typer.Option(None, "--model", help="Model name (non-interactive)."),
    list_models: bool = typer.Option(False, "--list", help="Show current tier map."),
) -> None:
    """Pick an Ollama model for a daari tier."""
    setup_models_interactive(get_settings(), tier=tier, model=model, list_only=list_models)


@setup_app.command("openai-compat")
def setup_openai_compat_command(
    write_env_example: bool = typer.Option(
        True,
        "--write-env-example/--no-write-env-example",
        help="Write ~/.daari/.env.example with OPENAI_* defaults.",
    ),
) -> None:
    """Print env vars for generic OpenAI-compatible SDKs."""
    setup_openai_compat(get_settings(), write_env_example=write_env_example)


@setup_app.command("frontier-key")
def setup_frontier_key(
    shell: str = typer.Option("zsh", "--shell", help="Shell profile to target: zsh|bash|fish"),
    write_profile_snippet: bool = typer.Option(
        False,
        "--write-profile-snippet",
        help="Append commented export hint to your shell profile.",
    ),
    write_env_example: bool = typer.Option(
        True,
        "--write-env-example/--no-write-env-example",
        help="Write ~/.daari/.env.example with frontier key placeholder.",
    ),
) -> None:
    """Optional helper for frontier API key hints (no secret storage)."""
    if shell not in {"zsh", "bash", "fish"}:
        typer.echo("Invalid shell. Expected one of: zsh, bash, fish.", err=True)
        raise typer.Exit(code=1)
    setup_frontier_key_hint(
        get_settings(),
        shell=shell,
        write_profile_snippet=write_profile_snippet,
        write_env_example=write_env_example,
    )


@context_app.command("clear")
def context_clear(
    l0: bool = typer.Option(True, "--l0/--no-l0", help="Clear L0 exact cache."),
    l1: bool = typer.Option(True, "--l1/--no-l1", help="Clear L1 semantic cache."),
    ccs: bool = typer.Option(True, "--ccs/--no-ccs", help="Clear command context store (CCS)."),
) -> None:
    """Clear local caches: L0, L1, and CCS."""
    if not any((l0, l1, ccs)):
        typer.echo("Nothing selected; choose at least one cache to clear.", err=True)
        raise typer.Exit(code=1)
    cleared = clear_context_caches(get_settings(), clear_l0=l0, clear_l1=l1, clear_ccs=ccs)
    for row in cleared:
        if row.error:
            action = f"skipped ({row.error})"
        else:
            action = "cleared" if row.existed else "already empty"
        typer.echo(f"{row.name}: {action} ({row.path})")


if __name__ == "__main__":
    app()
