from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import typer
import uvicorn
import httpx
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from daari.cli.setup_actions import (
    apply_all_setups,
    apply_claude_code_setup,
    apply_cursor_setup,
    apply_intellij_setup,
    apply_vscode_setup,
)
from daari.config.settings import Settings, get_settings
from daari.enterprise.client import OrgLearningClient
from daari.enterprise.service import create_org_cache_app
from daari.server.app import create_app
from daari.setup.context import clear_context_caches
from daari.setup.doctor import doctor_exit_code, run_doctor
from daari.setup.models import setup_models_interactive
from daari.setup.openai_compat import setup_frontier_key_hint, setup_openai_compat
from daari.setup.tunnel import parse_cloudflared_tunnel_url
from daari.setup.wizard import run_setup_wizard

app = typer.Typer(
    name="daari",
    help="Local-first execution router — cache before cloud.",
    no_args_is_help=True,
)

setup_app = typer.Typer(help="Configure client integrations.")
context_app = typer.Typer(help="Manage daari caches and context.")
org_cache_app = typer.Typer(help="Run org shared-cache service.")
org_learning_app = typer.Typer(help="Inspect enterprise org-learning aggregates.")
web_ui_app = typer.Typer(help="Serve local daari stats dashboard.")
app.add_typer(setup_app, name="setup")
app.add_typer(context_app, name="context")
app.add_typer(org_cache_app, name="org-cache")
app.add_typer(org_learning_app, name="org-learning")
app.add_typer(web_ui_app, name="web-ui")


def _daemon_is_running(settings: Settings) -> bool:
    url = f"http://{settings.server.host}:{settings.server.port}/health"
    try:
        response = httpx.get(url, timeout=1.0)
    except Exception:
        return False
    return response.status_code == 200


def _daemon_reload_caches(settings: Settings) -> tuple[bool, str]:
    url = f"http://{settings.server.host}:{settings.server.port}/v1/daari/reload-caches"
    try:
        response = httpx.post(url, timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("status") == "ok":
            return True, "in-memory cache handles refreshed"
        return False, "daemon returned unexpected response payload"
    except Exception as exc:
        return False, str(exc)


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def _start_cloudflared_tunnel(
    *,
    target_url: str = "http://127.0.0.1:11435",
    timeout_seconds: float = 45.0,
) -> tuple[subprocess.Popen[str], str]:
    process: subprocess.Popen[str] = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", target_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        raise RuntimeError("cloudflared did not expose a readable output stream.")

    deadline = time.monotonic() + timeout_seconds
    captured_lines: list[str] = []
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line:
            captured_lines.append(line.rstrip())
            tunnel_url = parse_cloudflared_tunnel_url(line)
            if tunnel_url:
                return process, tunnel_url
        elif process.poll() is not None:
            break

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    preview = "\n".join(captured_lines[-5:])
    raise RuntimeError(
        "Could not discover cloudflared tunnel URL. "
        + (f"Last output:\n{preview}" if preview else "No cloudflared output captured.")
    )


def _tunnel_health_ok(tunnel_url: str, timeout: float = 3.0) -> bool:
    try:
        response = httpx.get(f"{tunnel_url.rstrip('/')}/health", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def _wait_for_tunnel_health(tunnel_url: str, timeout_seconds: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _tunnel_health_ok(tunnel_url):
            return True
        time.sleep(0.25)
    return False


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host"),
    port: int | None = typer.Option(None, help="Bind port"),
    no_frontier: bool = typer.Option(False, "--no-frontier", help="Disable L6 escalation."),
    org: str | None = typer.Option(None, "--org", help="Enable enterprise org mode with org ID."),
) -> None:
    """Start the daari HTTP daemon."""
    settings = Settings.load().model_copy(deep=True)
    if no_frontier:
        settings.frontier.enabled = False
    resolved_org = org or os.environ.get("DAARI_ORG_ID")
    if resolved_org:
        settings.enterprise.enabled = True
        settings.enterprise.org_id = resolved_org
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


@org_cache_app.command("serve")
def serve_org_cache(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(11436, help="Bind port"),
    org: str | None = typer.Option(None, "--org", help="Org ID for shared cache namespace."),
    require_token: bool = typer.Option(False, "--require-token", help="Require bearer token auth."),
) -> None:
    """Start the lightweight org shared-cache HTTP service."""
    settings = Settings.load().model_copy(deep=True)
    resolved_org = org or settings.enterprise.resolved_org_id or os.environ.get("DAARI_ORG_ID")
    if not resolved_org:
        typer.echo("org-cache requires an org id (--org or DAARI_ORG_ID).", err=True)
        raise typer.Exit(code=1)
    settings.enterprise.enabled = True
    settings.enterprise.org_id = resolved_org
    if require_token:
        settings.enterprise.shared_cache_require_token = True
    app_instance = create_org_cache_app(settings.enterprise)
    typer.echo(f"daari org-cache serving on http://{host}:{port}/v1/org-cache")
    uvicorn.run(
        app_instance,
        host=host,
        port=port,
        log_level="info",
    )


def _build_org_learning_client(settings: Settings) -> OrgLearningClient:
    url = settings.enterprise.learning_url or settings.enterprise.shared_cache_url
    if not url:
        raise typer.BadParameter(
            "org learning URL is not configured (set org.learning_url or enterprise.learning_url)."
        )
    token = settings.enterprise.learning_token or settings.enterprise.org_token or settings.enterprise.shared_cache_token
    return OrgLearningClient(
        base_url=url,
        token=token,
        timeout_seconds=settings.enterprise.learning_timeout_seconds,
        enabled=True,
    )


@org_learning_app.command("stats")
def org_learning_stats() -> None:
    """Show aggregated org learning stats."""
    settings = Settings.load()
    client = _build_org_learning_client(settings)
    metrics = client.get_stats_sync()
    if metrics is None:
        typer.echo("Could not fetch org learning stats.", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(metrics, indent=2))


@org_learning_app.command("sync")
def org_learning_sync(
    host: str | None = typer.Option(None, help="Daemon host"),
    port: int | None = typer.Option(None, help="Daemon port"),
) -> None:
    """Force the running daemon to refresh org-learning routing profile."""
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    url = f"http://{bind_host}:{bind_port}/v1/org-learning/sync"
    try:
        response = httpx.post(url, timeout=5.0, headers={"Accept": "application/json"})
        response.raise_for_status()
        typer.echo(json.dumps(response.json(), indent=2))
    except Exception as exc:
        typer.echo(f"Could not trigger org-learning sync at {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@org_learning_app.command("export")
def org_learning_export(
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional output path for exported anonymized summary JSON.",
    ),
) -> None:
    """Export anonymized org learning summary."""
    settings = Settings.load()
    client = _build_org_learning_client(settings)
    payload = client.export_sync()
    if payload is None:
        typer.echo("Could not export org learning summary.", err=True)
        raise typer.Exit(code=1)
    serialized = json.dumps(payload, indent=2)
    if output is None:
        typer.echo(serialized)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")
    typer.echo(f"Exported org learning summary to {output}")


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


@web_ui_app.command("serve")
def serve_web_ui(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(11437, help="Bind port"),
    api_base_url: str = typer.Option(
        "http://127.0.0.1:11435",
        "--api-base-url",
        help="Base URL for daari daemon (without /v1).",
    ),
) -> None:
    """Serve static local dashboard for daari stats."""
    ui_root = Path(__file__).resolve().parents[2] / "packages" / "web-ui"
    if not (ui_root / "index.html").is_file():
        typer.echo(f"web-ui bundle missing at {ui_root}", err=True)
        raise typer.Exit(code=1)

    ui_server = FastAPI(title="daari-web-ui", version="0.1.0")
    normalized_api_base = api_base_url.rstrip("/")

    @ui_server.get("/web-ui-config.js")
    async def web_ui_config() -> PlainTextResponse:
        payload = f"window.__DAARI_WEB_UI_CONFIG__ = {{ apiBaseUrl: {json.dumps(normalized_api_base)} }};\n"
        return PlainTextResponse(payload, media_type="application/javascript")

    ui_server.mount("/", StaticFiles(directory=str(ui_root), html=True), name="web-ui")

    typer.echo(f"daari web-ui serving on http://{host}:{port} (api: {normalized_api_base})")
    uvicorn.run(
        ui_server,
        host=host,
        port=port,
        log_level="info",
    )


@app.command()
def doctor(
    tunnel: bool = typer.Option(
        False,
        "--tunnel",
        help="Also verify a public tunnel health endpoint.",
    ),
    tunnel_url: str | None = typer.Option(
        None,
        "--tunnel-url",
        help="Tunnel URL to check (defaults to DAARI_TUNNEL_URL when --tunnel is set).",
    ),
) -> None:
    """Verify Python, config, Ollama, model, and optional daemon."""
    settings = get_settings()
    resolved_tunnel_url = tunnel_url
    if tunnel and not resolved_tunnel_url:
        resolved_tunnel_url = os.environ.get("DAARI_TUNNEL_URL")
        if not resolved_tunnel_url:
            typer.echo(
                "Tunnel check requested but no tunnel URL provided. "
                "Pass --tunnel-url or set DAARI_TUNNEL_URL.",
                err=True,
            )
            raise typer.Exit(code=1)
    results = run_doctor(settings, tunnel_url=resolved_tunnel_url)
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
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="Override OpenAI-compatible base URL (defaults to local daari /v1).",
    ),
    tunnel: bool = typer.Option(
        False,
        "--tunnel",
        help="Use an HTTPS cloudflared tunnel for Cursor E2E (required for Cursor cloud BYOK).",
    ),
) -> None:
    """Configure Cursor to use the daari OpenAI-compat gateway."""
    if tunnel and base_url:
        typer.echo("Use either --tunnel or --base-url, not both.", err=True)
        raise typer.Exit(code=1)

    resolved_base_url = _normalize_openai_base_url(base_url) if base_url else None
    tunnel_process: subprocess.Popen[str] | None = None

    if tunnel:
        tunnel_from_env = os.environ.get("DAARI_TUNNEL_URL")
        if tunnel_from_env:
            resolved_base_url = _normalize_openai_base_url(tunnel_from_env)
            typer.echo(f"Using DAARI_TUNNEL_URL: {resolved_base_url}")
        else:
            if shutil.which("cloudflared") is None:
                typer.echo(
                    "cloudflared is required for --tunnel. Install it with: brew install cloudflared",
                    err=True,
                )
                raise typer.Exit(code=1)
            typer.echo("Starting cloudflared tunnel for http://127.0.0.1:11435 ...")
            try:
                tunnel_process, tunnel_url = _start_cloudflared_tunnel()
            except RuntimeError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1) from exc
            if not _wait_for_tunnel_health(tunnel_url):
                typer.echo(f"Tunnel URL discovered but health probe failed: {tunnel_url}/health", err=True)
                if tunnel_process.poll() is None:
                    tunnel_process.terminate()
                raise typer.Exit(code=1)
            resolved_base_url = _normalize_openai_base_url(tunnel_url)
            typer.echo(f"Tunnel ready: {resolved_base_url}")

    apply_cursor_setup(dry_run=dry_run, force=force, base_url=resolved_base_url)

    if tunnel_process is None:
        return
    if dry_run:
        tunnel_process.terminate()
        return

    typer.echo("\nCursor now points to the HTTPS tunnel URL.")
    typer.echo("Inference remains local in your daari daemon; Cursor's HTTP hop is public.")
    typer.echo("Keep this command running while using Cursor. Press Ctrl+C to stop the tunnel.")

    try:
        exit_code = tunnel_process.wait()
        if exit_code != 0:
            typer.echo(f"cloudflared exited with code {exit_code}", err=True)
            raise typer.Exit(code=exit_code)
    except KeyboardInterrupt:
        typer.echo("\nStopping cloudflared tunnel...")
    finally:
        if tunnel_process.poll() is None:
            tunnel_process.terminate()
            try:
                tunnel_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                tunnel_process.kill()
                tunnel_process.wait(timeout=2)


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


@setup_app.command("vscode")
def setup_vscode(
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
    """Configure VS Code settings for daari OpenAI-compatible setup."""
    apply_vscode_setup(dry_run=dry_run, force=force)


@setup_app.command("claude-code")
def setup_claude_code(
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
    """Write minimal OPENAI_* env helper files for claude-code."""
    apply_claude_code_setup(dry_run=dry_run, force=force)


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
    settings = get_settings()
    daemon_running = _daemon_is_running(settings)
    cleared = clear_context_caches(settings, clear_l0=l0, clear_l1=l1, clear_ccs=ccs)
    for row in cleared:
        if row.error:
            action = f"skipped ({row.error})"
        else:
            action = "cleared" if row.existed else "already empty"
        typer.echo(f"{row.name}: {action} ({row.path})")
    if daemon_running:
        reloaded, detail = _daemon_reload_caches(settings)
        if reloaded:
            typer.echo("Daemon cache handles refreshed via /v1/daari/reload-caches.")
        else:
            typer.echo(f"Cache reload endpoint failed: {detail}")
            typer.echo(
                "Note: daari serve is running. Restart it now to ensure in-memory cache handles are refreshed."
            )


if __name__ == "__main__":
    app()
