from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import httpx

from daari.config.settings import Settings


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    optional: bool = False


def run_doctor(
    settings: Settings | None = None,
    *,
    httpx_client: httpx.Client | None = None,
) -> list[CheckResult]:
    """Run health checks. Returns list of results (required + optional)."""
    results: list[CheckResult] = []
    cfg = settings or Settings.load()

    results.append(_check_python())
    results.append(_check_config(cfg))
    results.extend(_check_ollama(cfg, httpx_client))
    results.append(_check_frontier(cfg))
    results.append(_check_daemon(cfg, httpx_client))

    return results


def doctor_exit_code(results: list[CheckResult]) -> int:
    for result in results:
        if not result.optional and not result.ok:
            return 1
    return 0


def _check_python() -> CheckResult:
    version = sys.version_info
    ok = version >= (3, 12)
    detail = f"{version.major}.{version.minor}.{version.micro}"
    if not ok:
        detail += " (requires Python 3.12+)"
    return CheckResult(name="python", ok=ok, detail=detail)


def _check_config(settings: Settings) -> CheckResult:
    try:
        from pathlib import Path

        _ = settings.server.port
        user_path = Path.home() / ".daari" / "config.yaml"
        exists = user_path.is_file()
        detail = f"readable (user config {'present' if exists else 'using defaults'})"
        return CheckResult(name="config", ok=True, detail=detail)
    except Exception as exc:
        return CheckResult(name="config", ok=False, detail=str(exc))


def _check_ollama(
    settings: Settings,
    client: httpx.Client | None,
) -> list[CheckResult]:
    base = settings.ollama.base_url.rstrip("/")
    l3_model = settings.models.l3
    l4_model = settings.models.l4
    own_client = client is None
    http = client or httpx.Client(timeout=5.0)
    try:
        response = http.get(f"{base}/api/tags")
        if response.status_code != 200:
            return [
                CheckResult(
                    name="ollama",
                    ok=False,
                    detail=f"unreachable at {base} (HTTP {response.status_code})",
                ),
                CheckResult(
                    name="model",
                    ok=False,
                    detail=f"{l3_model} not checked (Ollama unreachable)",
                ),
                CheckResult(
                    name="model_l4",
                    ok=False,
                    detail=f"{l4_model} not checked (Ollama unreachable)",
                    optional=True,
                ),
            ]
        data: dict[str, Any] = response.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        l3_present = any(name == l3_model or name.startswith(f"{l3_model}:") for name in models)
        l4_present = any(name == l4_model or name.startswith(f"{l4_model}:") for name in models)
        return [
            CheckResult(name="ollama", ok=True, detail=f"reachable at {base}"),
            CheckResult(
                name="model",
                ok=l3_present,
                detail=f"{l3_model} {'found' if l3_present else 'missing — run: ollama pull ' + l3_model}",
            ),
            CheckResult(
                name="model_l4",
                ok=l4_present,
                detail=(
                    f"{l4_model} {'found' if l4_present else 'missing — run: ollama pull ' + l4_model + ' (L4 falls back to L3)'}"
                ),
                optional=True,
            ),
        ]
    except Exception as exc:
        return [
            CheckResult(name="ollama", ok=False, detail=f"unreachable at {base}: {exc}"),
            CheckResult(name="model", ok=False, detail=f"{l3_model} not checked (Ollama unreachable)"),
            CheckResult(
                name="model_l4",
                ok=False,
                detail=f"{l4_model} not checked (Ollama unreachable)",
                optional=True,
            ),
        ]
    finally:
        if own_client:
            http.close()


def _check_frontier(settings: Settings) -> CheckResult:
    frontier = settings.frontier
    if not frontier.enabled:
        return CheckResult(
            name="frontier",
            ok=True,
            detail="disabled (set frontier.enabled: true to enable L6 escalation)",
            optional=True,
        )
    key = settings.resolve_frontier_api_key()
    if key:
        return CheckResult(
            name="frontier",
            ok=True,
            detail=f"enabled ({frontier.provider}/{frontier.model}), API key present",
            optional=True,
        )
    return CheckResult(
        name="frontier",
        ok=False,
        detail=(
            "enabled but no API key — set DAARI_FRONTIER_API_KEY or OPENAI_API_KEY "
            "for L6 escalation"
        ),
        optional=True,
    )


def _check_daemon(
    settings: Settings,
    client: httpx.Client | None,
) -> CheckResult:
    host = settings.server.host
    port = settings.server.port
    url = f"http://{host}:{port}/v1/daari/stats"
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    try:
        response = http.get(url)
        if response.status_code == 200:
            total = response.json().get("total_requests", 0)
            return CheckResult(
                name="daemon",
                ok=True,
                detail=f"running at http://{host}:{port} ({total} requests served)",
                optional=True,
            )
        return CheckResult(
            name="daemon",
            ok=False,
            detail=f"not responding at http://{host}:{port} (HTTP {response.status_code})",
            optional=True,
        )
    except Exception:
        return CheckResult(
            name="daemon",
            ok=False,
            detail=f"not running (start with: daari serve)",
            optional=True,
        )
    finally:
        if own_client:
            http.close()
