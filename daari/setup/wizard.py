from __future__ import annotations

import os

import typer

from daari.clients.registry import default_registry
from daari.config.settings import Settings
from daari.setup.doctor import doctor_exit_code, run_doctor
from daari.setup.models import setup_models_interactive
from daari.setup.openai_compat import setup_frontier_key_hint, setup_openai_compat


def run_setup_wizard(settings: Settings | None = None) -> None:
    cfg = settings or Settings.load()
    registry = default_registry()
    cursor = registry.get("cursor")
    intellij = registry.get("intellij")
    vscode = registry.get("vscode")
    claude_code = registry.get("claude-code")

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
    vscode_detected = vscode.detect() if vscode else False
    typer.echo(f"    {'✓' if vscode_detected else '✗'} VS Code")
    intellij_detected = intellij.detect() if intellij else False
    typer.echo(f"    {'✓' if intellij_detected else '✗'} IntelliJ")
    claude_code_detected = claude_code.detect() if claude_code else False
    typer.echo(f"    {'✓' if claude_code_detected else '✗'} Claude Code")
    has_frontier_key = bool(cfg.resolve_frontier_api_key())
    frontier_mark = "✓" if has_frontier_key else "!"
    frontier_hint = "configured" if has_frontier_key else "not set (local-only unless provided)"
    typer.echo(f"    {frontier_mark} Frontier API key ({frontier_hint})")

    typer.echo("\n  What do you want to set up?")
    typer.echo("    1. Cursor — point AI chat at daari (OpenAI-compat)")
    typer.echo("    2. VS Code — write OpenAI-compatible settings marker")
    typer.echo("    3. Claude Code — write OPENAI_* env helper files")
    typer.echo("    4. Local models — choose defaults for L3/L4 and routing preference")
    typer.echo("    5. OpenAI SDK env helper — export OPENAI_* for daari")
    typer.echo("    6. Frontier key helper (optional) — env template/profile hint")
    typer.echo("    7. Run health check — daari doctor")
    typer.echo("    8. Skip for now")

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
        if not vscode_detected:
            typer.echo("VS Code not detected. Install VS Code or open it once, then re-run.", err=True)
            raise typer.Exit(code=1)
        from daari.cli.setup_actions import apply_vscode_setup

        if typer.confirm(
            f"Configure VS Code to use http://{cfg.server.host}:{cfg.server.port}/v1?",
            default=True,
        ):
            apply_vscode_setup(settings=cfg, dry_run=False, force=False)
        else:
            typer.echo("Skipped VS Code setup.")
    elif choice == "3":
        from daari.cli.setup_actions import apply_claude_code_setup

        if typer.confirm("Write claude-code OPENAI_* helper files in ~/.claude?", default=True):
            apply_claude_code_setup(settings=cfg, dry_run=False, force=False)
        else:
            typer.echo("Skipped claude-code setup.")
    elif choice == "4":
        if not ollama_ok:
            typer.echo("Ollama is not reachable — start Ollama first.", err=True)
            raise typer.Exit(code=1)
        setup_models_interactive(cfg, tier="l3")
        if typer.confirm("Configure L4 model as well?", default=True):
            setup_models_interactive(cfg, tier="l4")
    elif choice == "5":
        setup_openai_compat(cfg, write_env_example=True)
    elif choice == "6":
        shell_from_env = (os.environ.get("SHELL", "").split("/")[-1] or "zsh").lower()
        shell = shell_from_env if shell_from_env in {"zsh", "bash", "fish"} else "zsh"
        write_profile = typer.confirm("Append frontier key hint to your shell profile?", default=False)
        setup_frontier_key_hint(
            cfg,
            shell=shell,
            write_profile_snippet=write_profile,
            write_env_example=True,
        )
    elif choice == "7":
        results = run_doctor(cfg)
        for result in results:
            mark = "✓" if result.ok else "✗"
            suffix = " (optional)" if result.optional else ""
            typer.echo(f"  {mark} {result.name}{suffix}: {result.detail}")
        code = doctor_exit_code(results)
        if code != 0:
            raise typer.Exit(code=code)
    elif choice == "8":
        typer.echo("Nothing to do.")
    else:
        typer.echo("Invalid choice.", err=True)
        raise typer.Exit(code=1)
