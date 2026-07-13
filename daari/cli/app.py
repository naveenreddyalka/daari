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
from daari.setup.tunnel import (
    parse_cloudflared_tunnel_url,
    wait_for_tunnel_health,
)
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


def _emit_or_write(text: str, out: str | None) -> None:
    if out is None:
        typer.echo(text)
        return
    Path(out).expanduser().write_text(text, encoding="utf-8")
    typer.echo(f"Wrote {out}")


@app.command()
def feedback(
    trace_id: str = typer.Argument(..., help="Trace id from daari_meta.trace_id"),
    accept: bool = typer.Option(False, "--accept", help="Mark the response as good"),
    reject: bool = typer.Option(False, "--reject", help="Mark the response as bad"),
    host: str | None = typer.Option(None, help="Daemon host"),
    port: int | None = typer.Option(None, help="Daemon port"),
) -> None:
    """Attach accept/reject feedback to a response (Phase D personal learning)."""
    if accept == reject:
        typer.echo("Pass exactly one of --accept or --reject.", err=True)
        raise typer.Exit(code=2)
    signal = "accept" if accept else "reject"
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    url = f"http://{bind_host}:{bind_port}/v1/daari/feedback"
    try:
        import httpx

        response = httpx.post(url, json={"trace_id": trace_id, "signal": signal}, timeout=5.0)
    except Exception as exc:
        typer.echo(f"Could not reach daari at {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if response.status_code == 404:
        typer.echo(f"No outcome recorded for trace {trace_id}.", err=True)
        raise typer.Exit(code=1)
    response.raise_for_status()
    typer.echo(f"Recorded {signal} for trace {trace_id}.")


@app.command()
def trace(
    trace_id: str | None = typer.Argument(None, help="Trace id; omit to list recent traces"),
    limit: int = typer.Option(10, help="How many recent traces to list"),
    host: str | None = typer.Option(None, help="Daemon host"),
    port: int | None = typer.Option(None, help="Daemon port"),
    output_format: str = typer.Option("text", "--format", help="Output format: text | markdown"),
    out: str | None = typer.Option(None, "--out", help="Write output to a file (client-shareable)"),
) -> None:
    """Show what daari did for a request (client-facing decision trace)."""
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    base = f"http://{bind_host}:{bind_port}/v1/daari/traces"
    url = f"{base}/{trace_id}" if trace_id else f"{base}?limit={limit}"
    try:
        import httpx

        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        typer.echo(f"Could not reach daari at {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if trace_id is None:
        typer.echo(f"{'trace_id':<18} {'tier':<6} {'category':<12} ts")
        for item in payload.get("traces", []):
            typer.echo(
                f"{item['trace_id']:<18} {str(item.get('tier')):<6}"
                f" {str(item.get('category')):<12} {item.get('ts', '')}"
            )
        return

    if output_format == "markdown" or out is not None:
        from daari.observability.render import trace_markdown

        _emit_or_write(trace_markdown(payload), out)
        return

    typer.echo(f"trace {payload['trace_id']}  tier={payload.get('tier')}  category={payload.get('category')}")
    for step in payload.get("steps", []):
        detail = step.get("detail") or {}
        detail_text = "  ".join(f"{key}={value}" for key, value in detail.items())
        typer.echo(f"  +{step['elapsed_ms']:>5}ms  {step['step']:<14} {detail_text}")


@app.command()
def report(
    days: int = typer.Option(7, help="Number of days to include"),
    host: str | None = typer.Option(None, help="Daemon host"),
    port: int | None = typer.Option(None, help="Daemon port"),
    output_format: str = typer.Option("text", "--format", help="Output format: text | markdown"),
    out: str | None = typer.Option(None, "--out", help="Write output to a file (client-shareable)"),
    by_client: bool = typer.Option(False, "--by-client", help="Break usage down per client id"),
) -> None:
    """Show persisted usage and estimated frontier savings."""
    settings = get_settings()
    bind_host = host or settings.server.host
    bind_port = port or settings.server.port
    url = f"http://{bind_host}:{bind_port}/v1/daari/report?days={days}"
    try:
        import httpx

        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        typer.echo(f"Could not reach daari at {url}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if output_format == "markdown" or out is not None:
        from daari.observability.render import report_markdown

        _emit_or_write(report_markdown(payload, days=days), out)
        return

    if not payload.get("enabled", False):
        typer.echo("Usage ledger is disabled (settings: usage.enabled).")
        return
    totals = payload.get("totals", {})
    typer.echo(f"daari usage report (last {days} days)")
    typer.echo("")
    typer.echo(f"{'day':<12} {'requests':>9} {'cache hits':>11} {'prompt ch':>10} {'compl ch':>9}")
    for entry in payload.get("days", []):
        typer.echo(
            f"{entry['day']:<12} {entry['requests']:>9} {entry['cache_hits']:>11}"
            f" {entry['prompt_chars']:>10} {entry['completion_chars']:>9}"
        )
    typer.echo("")
    typer.echo(f"total requests:    {totals.get('requests', 0)}")
    typer.echo(f"cache hits:        {totals.get('cache_hits', 0)}")
    typer.echo(f"local requests:    {totals.get('local_requests', 0)}")
    typer.echo(f"frontier requests: {totals.get('frontier_requests', 0)}")
    typer.echo(f"estimated saved:   ${totals.get('estimated_saved_usd', 0.0):.4f}")

    frontier = payload.get("frontier") or {}
    if frontier.get("daily_budget_usd") or frontier.get("monthly_budget_usd"):
        typer.echo("")
        typer.echo(
            f"frontier budget:   state={frontier.get('budget_state', 'ok')}"
            f" today=${frontier.get('today_spend_usd', 0.0):.4f}"
            f"/{frontier.get('daily_budget_usd', 0.0) or '∞'}"
            f" month=${frontier.get('month_spend_usd', 0.0):.4f}"
            f"/{frontier.get('monthly_budget_usd', 0.0) or '∞'}"
        )

    if by_client:
        clients = payload.get("clients") or []
        typer.echo("")
        if not clients:
            typer.echo("No per-client usage recorded yet.")
        else:
            typer.echo(
                f"{'client':<14} {'requests':>9} {'cache hits':>11} "
                f"{'frontier':>9} {'saved $':>9}"
            )
            for entry in clients:
                typer.echo(
                    f"{entry['client_id']:<14} {entry['requests']:>9} "
                    f"{entry['cache_hits']:>11} {entry['frontier_requests']:>9} "
                    f"{entry['estimated_saved_usd']:>9.4f}"
                )

    trust = payload.get("cache_trust") or {}
    false_hits = trust.get("false_hit_rates") or {}
    if false_hits:
        typer.echo("")
        typer.echo("cache trust (shadow-sampled L1 false-hit rate):")
        for category in sorted(false_hits):
            row = false_hits[category]
            typer.echo(
                f"  {category:<14} {row['false_hit_rate'] * 100:>5.1f}%"
                f" ({row['disagreements']}/{row['samples']} sampled hits)"
            )


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
def profile(
    show: bool = typer.Option(False, "--show", help="Print the stored profile without re-benchmarking"),
    models: str | None = typer.Option(
        None, help="Comma-separated models to benchmark (default: configured L3/L4/L5)"
    ),
) -> None:
    """Benchmark local models on this hardware (tokens/sec, latency, load)."""
    import asyncio as _asyncio

    from daari.router.model_profile import ModelProfileStore, benchmark_models

    store = ModelProfileStore()
    if show:
        data = store.load()
        if not data:
            typer.echo("No profile stored yet. Run `daari profile` to benchmark.")
            return
        typer.echo(f"{'model':<24} {'latency ms':>10} {'load ms':>9} {'tok/s':>7}")
        for model in sorted(data):
            entry = data[model]
            tps = entry.get("tokens_per_second")
            typer.echo(
                f"{model:<24} {entry.get('latency_ms', 0):>10.0f} "
                f"{entry.get('load_ms', 0):>9.0f} {tps if tps is not None else '-':>7}"
            )
        return

    settings = get_settings()
    if models:
        target_models = [m.strip() for m in models.split(",") if m.strip()]
    else:
        target_models = list(
            dict.fromkeys([settings.models.l3, settings.models.l4, settings.models.l5])
        )
    typer.echo(f"Benchmarking {len(target_models)} model(s) — one short generation each...")
    results = _asyncio.run(
        benchmark_models(settings.ollama.base_url.rstrip("/"), target_models)
    )
    if not results:
        typer.echo("No models could be benchmarked. Is Ollama running?", err=True)
        raise typer.Exit(code=1)
    merged = {**store.load(), **results}
    store.save(merged)
    for model, entry in results.items():
        tps = entry.get("tokens_per_second")
        typer.echo(
            f"{model}: {entry['latency_ms']:.0f} ms wall, "
            f"load {entry['load_ms']:.0f} ms, {tps if tps is not None else '-'} tok/s"
        )
    typer.echo(f"Saved to {store.path}")


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
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Non-interactive: pull the L4 model automatically when missing.",
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
            if not wait_for_tunnel_health(tunnel_url):
                typer.echo(f"Tunnel URL discovered but health probe failed: {tunnel_url}/health", err=True)
                if tunnel_process.poll() is None:
                    tunnel_process.terminate()
                raise typer.Exit(code=1)
            resolved_base_url = _normalize_openai_base_url(tunnel_url)
            typer.echo(f"Tunnel ready: {resolved_base_url}")

    apply_cursor_setup(dry_run=dry_run, force=force, base_url=resolved_base_url, yes=yes)

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


cache_app = typer.Typer(help="Manage response caches.")
app.add_typer(cache_app, name="cache")


@cache_app.command("prune")
def cache_prune() -> None:
    """Remove expired L0/L1 entries (requires cache.*.ttl_seconds > 0)."""
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import OllamaEmbedder, SemanticCache

    settings = get_settings()
    l0 = ExactCache(
        str(settings.l0_cache_path),
        enabled=settings.cache.l0.enabled,
        ttl_seconds=settings.cache.l0.ttl_seconds,
    )
    l1 = SemanticCache(
        str(settings.l1_cache_path),
        OllamaEmbedder(settings.ollama.base_url, settings.cache.l1.embedding_model),
        enabled=settings.cache.l1.enabled,
        ttl_seconds=settings.cache.l1.ttl_seconds,
    )
    l0_removed = l0.prune()
    l1_removed = l1.prune()
    l0_note = "" if settings.cache.l0.ttl_seconds > 0 else " (ttl disabled — nothing expires)"
    l1_note = "" if settings.cache.l1.ttl_seconds > 0 else " (ttl disabled — nothing expires)"
    typer.echo(f"L0: removed {l0_removed} expired entries{l0_note}")
    typer.echo(f"L1: removed {l1_removed} expired entries{l1_note}")


learn_app = typer.Typer(help="Personal learning loop: outcome stats and recommendations.")
app.add_typer(learn_app, name="learn")


def _feedback_store():
    from daari.learning.feedback import FeedbackStore

    settings = get_settings()
    return FeedbackStore(
        settings.feedback_store_path,
        enabled=settings.learning.enabled,
        max_rows=settings.learning.max_rows,
    )


@learn_app.command("stats")
def learn_stats(days: int = typer.Option(7, help="Evidence window in days")) -> None:
    """Per-category × tier outcome evidence (escalations, accepts/rejects)."""
    store = _feedback_store()
    stats = store.stats(days=days)
    if not stats:
        typer.echo("No outcomes recorded yet. Route some requests, then rerun.")
    else:
        header = (
            f"{'category':<14} {'tier':<5} {'outcomes':>8} {'escal%':>7} "
            f"{'accepts':>7} {'rejects':>7} {'conf':>6} {'lat ms':>8}"
        )
        typer.echo(header)
        for category in sorted(stats):
            for tier in sorted(stats[category]):
                row = stats[category][tier]
                conf = f"{row['avg_confidence']:.2f}" if row["avg_confidence"] is not None else "-"
                lat = f"{row['avg_latency_ms']:.0f}" if row["avg_latency_ms"] is not None else "-"
                typer.echo(
                    f"{category:<14} {tier:<5} {row['outcomes']:>8} "
                    f"{row['escalation_rate'] * 100:>6.1f}% {row['accepts']:>7} "
                    f"{row['rejects']:>7} {conf:>6} {lat:>8}"
                )
    shadow = store.shadow_stats(days=days)
    if shadow:
        typer.echo("")
        typer.echo("Cache trust (shadow-sampled L1 hits):")
        typer.echo(f"{'category':<14} {'samples':>8} {'disagree':>9} {'false-hit%':>11}")
        for category in sorted(shadow):
            row = shadow[category]
            typer.echo(
                f"{category:<14} {row['samples']:>8} {row['disagreements']:>9} "
                f"{row['false_hit_rate'] * 100:>10.1f}%"
            )


def _example_store():
    from daari.learning.examples import ExampleStore

    settings = get_settings()
    return ExampleStore(
        settings.example_store_path,
        max_rows=settings.learning.examples_max_rows,
    )


@learn_app.command("examples")
def learn_examples(
    limit: int = typer.Option(20, help="How many recent examples to list"),
    clear: bool = typer.Option(False, "--clear", help="Delete all captured examples"),
) -> None:
    """List (or wipe) captured training examples (D2a, opt-in)."""
    store = _example_store()
    if clear:
        removed = store.clear()
        typer.echo(f"Removed {removed} captured examples.")
        return
    rows = store.examples(limit=limit)
    settings = get_settings()
    if not rows:
        hint = (
            ""
            if settings.learning.capture_examples
            else " (capture is off — set learning.capture_examples: true)"
        )
        typer.echo(f"No training examples captured{hint}.")
        return
    total = store.count()
    accepted = store.count(only_accepted=True)
    typer.echo(f"{total} examples captured, {accepted} accepted\n")
    typer.echo(f"{'trace_id':<18} {'tier':<5} {'category':<13} {'accepted':<9} completion")
    for row in rows:
        preview = (row["completion"][:47] + "...") if len(row["completion"]) > 50 else row["completion"]
        preview = preview.replace("\n", " ")
        accepted_mark = "yes" if row["accepted"] else "-"
        typer.echo(
            f"{(row['trace_id'] or '-'):<18} {row['tier']:<5} "
            f"{(row['category'] or '-'):<13} {accepted_mark:<9} {preview}"
        )


@learn_app.command("export-dataset")
def learn_export_dataset(
    out: str = typer.Option(..., "--out", help="Directory for train.jsonl/valid.jsonl"),
    only_accepted: bool = typer.Option(
        False, "--only-accepted", help="Export only explicitly accepted examples"
    ),
    split: float = typer.Option(0.9, help="Train fraction (rest goes to valid)"),
    min_examples: int = typer.Option(8, help="Refuse to export below this many examples"),
) -> None:
    """Export captured examples as an mlx-lm chat dataset (D2b)."""
    from daari.learning.dataset import DatasetError, export_dataset

    try:
        counts = export_dataset(
            _example_store(),
            out,
            only_accepted=only_accepted,
            split=split,
            min_examples=min_examples,
        )
    except DatasetError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote {counts['train']} train / {counts['valid']} valid examples to {out}")


@learn_app.command("train-router")
def learn_train_router(
    min_samples: int = typer.Option(
        None, help="Minimum labeled examples required (default: learning.router_min_samples)"
    ),
    out: str | None = typer.Option(None, "--out", help="Model output path"),
) -> None:
    """Train the personal routing classifier from captured examples."""
    import asyncio as _asyncio

    from daari.cache.semantic import OllamaEmbedder
    from daari.learning.router_model import RouterTrainingError, train_router

    settings = get_settings()
    store = _example_store()
    embedder = OllamaEmbedder(
        base_url=settings.ollama.base_url.rstrip("/"),
        model=settings.cache.l1.embedding_model,
        cache_size=settings.cache.l1.embed_cache_size,
    )
    floor = min_samples if min_samples is not None else settings.learning.router_min_samples
    out_path = out or settings.learning.router_model_path
    try:
        result = _asyncio.run(
            train_router(store, embedder, out_path=out_path, min_samples=floor)
        )
    except RouterTrainingError as exc:
        typer.echo(f"Cannot train: {exc}", err=True)
        typer.echo(
            "Enable learning.capture_examples and route more requests first.", err=True
        )
        raise typer.Exit(code=1) from exc
    typer.echo(f"Trained on {result['samples']} examples:")
    for category, count in sorted(result["categories"].items()):
        typer.echo(f"  {category:<14} {count}")
    typer.echo(f"Saved to {result['path']}")
    typer.echo("Enable with routing.learned_router: true in settings.")


@learn_app.command("finetune")
def learn_finetune(
    model: str | None = typer.Option(None, help="MLX model to fine-tune"),
    iters: int = typer.Option(100, help="Training iterations"),
    only_accepted: bool = typer.Option(
        False, "--only-accepted", help="Train only on explicitly accepted examples"
    ),
    min_examples: int = typer.Option(8, help="Refuse to train below this many examples"),
    runs_root: str | None = typer.Option(
        None, "--runs-root", help="Run directory root (default ~/.daari/training/runs)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the training command without running it"
    ),
) -> None:
    """LoRA fine-tune the local model on captured examples via mlx-lm (D2c)."""
    from daari.learning.dataset import DatasetError
    from daari.learning.finetune import (
        DEFAULT_MODEL,
        DEFAULT_RUNS_ROOT,
        FinetuneError,
        plan_finetune,
        run_finetune,
    )

    try:
        plan = plan_finetune(
            _example_store(),
            runs_root=runs_root or DEFAULT_RUNS_ROOT,
            model=model or DEFAULT_MODEL,
            iters=iters,
            only_accepted=only_accepted,
            min_examples=min_examples,
        )
    except DatasetError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Run dir: {plan.run_dir}")
    typer.echo(f"Dataset: {plan.counts['train']} train / {plan.counts['valid']} valid examples")
    typer.echo(f"Command: {' '.join(plan.command)}")
    if dry_run:
        typer.echo("Dry run — nothing executed. Re-run without --dry-run to train.")
        return
    try:
        run_finetune(plan)
    except FinetuneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Adapters written to {plan.run_dir / 'adapters'}")


@learn_app.command("recommend")
def learn_recommend(
    days: int = typer.Option(7, help="Evidence window in days"),
    min_samples: int = typer.Option(20, help="Minimum outcomes per category to recommend"),
) -> None:
    """Emit a routing.category_policies block derived from outcome evidence."""
    from daari.learning.recommend import recommend_policies, recommendation_yaml

    stats = _feedback_store().stats(days=days)
    recommendations = recommend_policies(stats, min_samples=min_samples)
    typer.echo(recommendation_yaml(recommendations), nl=False)


if __name__ == "__main__":
    app()
