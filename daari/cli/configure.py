"""One-command client onboarding: `daari configure <client>` (#445)."""

from __future__ import annotations

import typer

from daari.clients.registry import default_registry
from daari.cli.setup_actions import _print_setup_plan
from daari.config.settings import Settings, get_settings

# Documented first-wave clients for `daari configure` (#445).
CONFIGURE_CLIENTS = ("claude-code", "vscode", "claude-desktop")


def supported_clients() -> list[str]:
    registry = default_registry()
    ordered = [cid for cid in CONFIGURE_CLIENTS if registry.get(cid) is not None]
    for cid in registry.list_ids():
        if cid not in ordered:
            ordered.append(cid)
    return ordered


def _verification_hint(client_id: str, *, base_url: str, api_key: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    if client_id == "claude-code":
        return (
            f'Verify: curl -sS -H "x-api-key: {api_key}" '
            f'-H "anthropic-version: 2023-06-01" {root}/v1/messages/health'
        )
    if client_id == "claude-desktop":
        return (
            f'Verify: curl -sS -H "x-api-key: {api_key}" '
            f"{root}/v1/models"
        )
    return f'Verify: curl -sS -H "Authorization: Bearer {api_key}" {root}/v1/models'


def resolve_configure_api_key(
    cfg: Settings,
    *,
    dry_run: bool,
) -> tuple[str, str | None]:
    """API key written into client config.

    Uses ``server.api_key`` when gateway auth is configured; otherwise the
    open-local placeholder ``daari-local``.
    """
    master = cfg.server.api_key.strip()
    if master:
        return master, None
    return "daari-local", None


def configure_client(
    client_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    settings: Settings | None = None,
    base_url: str | None = None,
) -> None:
    """Write client settings for the local gateway (#445)."""
    cfg = settings or get_settings()
    registry = default_registry()
    known = supported_clients()
    recipe = registry.get(client_id)
    if recipe is None:
        typer.echo(
            f"Unknown client {client_id!r}. Supported: {', '.join(known)}",
            err=True,
        )
        raise typer.Exit(code=1)

    resolved_base = base_url or f"http://{cfg.server.host}:{cfg.server.port}/v1"
    api_key, key_note = resolve_configure_api_key(cfg, dry_run=dry_run)
    if key_note:
        typer.echo(key_note)

    plan = recipe.dry_run(
        base_url=resolved_base,
        api_key=api_key if not api_key.startswith("<") else "daari-local",
        model_name="daari",
    )
    if dry_run:
        _print_setup_plan(plan)
        typer.echo("\nDry-run complete — no files modified.")
        typer.echo(
            _verification_hint(
                client_id,
                base_url=resolved_base,
                api_key=api_key if not api_key.startswith("<") else "daari-local",
            )
        )
        return

    result = recipe.apply(
        base_url=resolved_base,
        api_key=api_key,
        model_name="daari",
        force=force,
    )
    typer.echo(result.message)
    if not result.changed:
        # Idempotent re-run: already configured (or client missing).
        if "already configured" in result.message.lower():
            typer.echo(_verification_hint(client_id, base_url=resolved_base, api_key=api_key))
            return
        if "not detected" in result.message.lower() or "not found" in result.message.lower():
            raise typer.Exit(code=1)
        typer.echo(_verification_hint(client_id, base_url=resolved_base, api_key=api_key))
        return

    typer.echo("Files changed:")
    for path in result.files_changed:
        typer.echo(f"  - {path}")
    if result.backup_dir is not None:
        typer.echo(f"Backup: {result.backup_dir}")
        typer.echo(f"Undo with: daari setup --undo {client_id}")
    typer.echo(_verification_hint(client_id, base_url=resolved_base, api_key=api_key))
