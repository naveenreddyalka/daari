from __future__ import annotations

import secrets
from pathlib import Path

import typer
import yaml

from daari.clients.registry import default_registry
from daari.config.settings import Settings, get_settings
from daari.setup.models import l4_model_present, pull_ollama_model


def ensure_server_api_key(
    cfg: Settings, *, config_path: Path | None = None
) -> tuple[str, bool]:
    """Return the gateway API key, generating and persisting one when unset.

    Used by tunnel setup (issue #86): a public HTTPS endpoint must not expose
    an unauthenticated gateway.
    """
    key = cfg.server.api_key.strip()
    if key:
        return key, False

    key = secrets.token_urlsafe(24)
    path = config_path or Path.home() / ".daari" / "config.yaml"
    current: dict = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            current = loaded
    server = current.setdefault("server", {})
    if not isinstance(server, dict):
        server = {}
        current["server"] = server
    server["api_key"] = key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(current, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    cfg.server.api_key = key
    return key, True


def _print_setup_plan(plan) -> None:
    label = plan.client_id.capitalize()
    typer.echo(f"{label} detected: {'yes' if plan.detected else 'no'}")
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


def apply_setup_recipe(
    recipe_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
    fail_on_missing: bool = True,
    base_url: str | None = None,
) -> None:
    cfg = settings or get_settings()
    registry = default_registry()
    recipe = registry.get(recipe_id)
    if recipe is None:
        typer.echo(f"{recipe_id.capitalize()} setup recipe not found.", err=True)
        raise typer.Exit(code=1)

    resolved_base_url = base_url or f"http://{cfg.server.host}:{cfg.server.port}/v1"
    resolved_api_key = cfg.server.api_key.strip() or "daari-local"
    plan = recipe.dry_run(base_url=resolved_base_url, api_key=resolved_api_key, model_name="daari")
    if not dry_run:
        plan.notes = [note for note in plan.notes if "Dry-run only" not in note]
    _print_setup_plan(plan)

    if dry_run:
        typer.echo("\nDry-run complete — no files modified.")
        return

    result = recipe.apply(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        model_name="daari",
        force=force,
    )
    typer.echo(f"\n{result.message}")
    if not result.changed:
        if fail_on_missing and ("not detected" in result.message or "not found" in result.message):
            raise typer.Exit(code=1)
        return

    typer.echo("Files changed:")
    for path in result.files_changed:
        typer.echo(f"  - {path}")
    if result.backup_dir is not None:
        typer.echo(f"Backup: {result.backup_dir}")
        typer.echo(f"Undo with: daari setup --undo {recipe_id}")
    typer.echo("\nNext: daari serve")


def ensure_cursor_l4_model(settings: Settings, *, assume_yes: bool = False) -> None:
    """Cursor's long Ask context routes to L4; offer to pull it if missing (issue #4)."""
    l4 = settings.models.l4
    present = l4_model_present(settings.ollama.base_url, l4)
    if present is None:
        typer.echo(
            f"\nNote: Ollama unreachable — could not verify the L4 model. Cursor long "
            f"prompts route to L4; pull it later with: ollama pull {l4}"
        )
        return
    if present:
        typer.echo(f"\nL4 model {l4} is available — long Cursor prompts will use it.")
        return
    typer.echo(
        f"\nCursor long prompts route to L4 ({l4}), which is not pulled yet "
        "(they would fall back to L3 with a retry delay)."
    )
    if assume_yes or typer.confirm(f"Pull {l4} now?", default=True):
        typer.echo(f"Pulling {l4} (this may take a few minutes)...")
        if pull_ollama_model(l4):
            typer.echo(f"Pulled {l4}.")
        else:
            typer.echo(f"Pull failed — run manually: ollama pull {l4}", err=True)
    else:
        typer.echo(f"Skipped. Later: ollama pull {l4} (until then L4 requests fall back to L3).")


def apply_cursor_setup(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
    base_url: str | None = None,
    yes: bool = False,
    secure: bool = False,
) -> None:
    cfg = settings or get_settings()
    if secure and not dry_run:
        key, generated = ensure_server_api_key(cfg)
        if generated:
            typer.echo(
                "Generated a gateway API key (server.api_key in ~/.daari/config.yaml) — "
                "the public tunnel now requires it. Restart the daemon to enforce: "
                "launchctl kickstart -k gui/$(id -u)/com.daari.serve"
            )
        else:
            typer.echo("Gateway API key already configured — Cursor will send it.")
    apply_setup_recipe("cursor", dry_run=dry_run, force=force, settings=cfg, base_url=base_url)
    if not dry_run:
        ensure_cursor_l4_model(cfg, assume_yes=yes)


def apply_intellij_setup(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> None:
    apply_setup_recipe("intellij", dry_run=dry_run, force=force, settings=settings)


def apply_vscode_setup(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> None:
    apply_setup_recipe("vscode", dry_run=dry_run, force=force, settings=settings)


def apply_claude_code_setup(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> None:
    apply_setup_recipe("claude-code", dry_run=dry_run, force=force, settings=settings)


def apply_all_setups(
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    registry = default_registry()
    for recipe_id in registry.list_ids():
        typer.echo(f"\n== {recipe_id} ==")
        apply_setup_recipe(
            recipe_id,
            dry_run=dry_run,
            force=force,
            settings=cfg,
            fail_on_missing=False,
        )
