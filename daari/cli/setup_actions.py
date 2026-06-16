from __future__ import annotations

import typer

from daari.clients.registry import default_registry
from daari.config.settings import Settings, get_settings


def _print_setup_plan(plan) -> None:
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


def apply_cursor_setup(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    registry = default_registry()
    recipe = registry.get("cursor")
    if recipe is None:
        typer.echo("Cursor setup recipe not found.", err=True)
        raise typer.Exit(code=1)

    base_url = f"http://{cfg.server.host}:{cfg.server.port}/v1"
    plan = recipe.dry_run(base_url=base_url, api_key="daari-local", model_name="daari")
    _print_setup_plan(plan)

    if dry_run:
        typer.echo("\nDry-run complete — no files modified.")
        return

    result = recipe.apply(
        base_url=base_url,
        api_key="daari-local",
        model_name="daari",
        force=force,
    )
    typer.echo(f"\n{result.message}")
    if not result.changed:
        if "not detected" in result.message or "not found" in result.message:
            raise typer.Exit(code=1)
        return

    typer.echo("Files changed:")
    for path in result.files_changed:
        typer.echo(f"  - {path}")
    if result.backup_dir is not None:
        typer.echo(f"Backup: {result.backup_dir}")
        typer.echo("Undo with: daari setup --undo cursor")
    typer.echo("\nNext: daari serve")
