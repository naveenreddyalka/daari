from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
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
    tunnel_url: str | None = None,
) -> list[CheckResult]:
    """Run health checks. Returns list of results (required + optional)."""
    results: list[CheckResult] = []
    cfg = settings or Settings.load()

    results.append(_check_python())
    results.append(_check_config(cfg))
    results.extend(_check_ollama(cfg, httpx_client))
    results.append(_check_frontier(cfg))
    results.append(_check_org(cfg))
    results.append(_check_org_cache(cfg, httpx_client))
    results.append(_check_daemon(cfg, httpx_client))
    if tunnel_url:
        results.append(_check_tunnel(tunnel_url, httpx_client))

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
    l5_model = settings.models.l5
    embedding_model = settings.cache.l1.embedding_model
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
                CheckResult(
                    name="model_l5",
                    ok=False,
                    detail=f"{l5_model} not checked (Ollama unreachable)",
                    optional=True,
                ),
                CheckResult(
                    name="embedding_model",
                    ok=False,
                    detail=f"{embedding_model} not checked (Ollama unreachable)",
                    optional=True,
                ),
            ]
        data: dict[str, Any] = response.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        l3_present = any(name == l3_model or name.startswith(f"{l3_model}:") for name in models)
        l4_present = any(name == l4_model or name.startswith(f"{l4_model}:") for name in models)
        l5_present = any(name == l5_model or name.startswith(f"{l5_model}:") for name in models)
        embedding_present = any(
            name == embedding_model or name.startswith(f"{embedding_model}:") for name in models
        )
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
            CheckResult(
                name="model_l5",
                ok=l5_present,
                detail=(
                    f"{l5_model} {'found' if l5_present else 'missing — run: ollama pull ' + l5_model + ' (L5 optional large tier)'}"
                ),
                optional=True,
            ),
            CheckResult(
                name="embedding_model",
                ok=embedding_present,
                detail=(
                    f"{embedding_model} "
                    f"{'found' if embedding_present else 'missing — run: ollama pull ' + embedding_model + ' (required for L1 semantic cache)'}"
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
            CheckResult(
                name="model_l5",
                ok=False,
                detail=f"{l5_model} not checked (Ollama unreachable)",
                optional=True,
            ),
            CheckResult(
                name="embedding_model",
                ok=False,
                detail=f"{embedding_model} not checked (Ollama unreachable)",
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


def _check_org(settings: Settings) -> CheckResult:
    org = settings.enterprise
    org_id = org.resolved_org_id
    if not org.enabled and not org_id:
        return CheckResult(
            name="org",
            ok=True,
            detail="disabled",
            optional=True,
        )
    if not org_id:
        return CheckResult(
            name="org",
            ok=False,
            detail="org mode enabled but org_id missing (use --org or DAARI_ORG_ID)",
        )
    if org.shared_cache_path:
        cache_root = Path(org.shared_cache_path).expanduser()
    else:
        cache_root = Path.home() / ".daari" / "org" / org_id / "cache"
    return CheckResult(
        name="org",
        ok=True,
        detail=f"enabled for {org_id} (cache root: {cache_root})",
        optional=True,
    )


def _check_org_cache(
    settings: Settings,
    client: httpx.Client | None,
) -> CheckResult:
    org = settings.enterprise
    if not org.shared_cache_url:
        return CheckResult(
            name="org_cache",
            ok=True,
            detail="disabled (no shared_cache_url configured)",
            optional=True,
        )
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    headers: dict[str, str] = {}
    if org.shared_cache_token:
        headers["Authorization"] = f"Bearer {org.shared_cache_token}"
    url = f"{org.shared_cache_url.rstrip('/')}/v1/org-cache/stats"
    try:
        response = http.get(url, headers=headers)
        if response.status_code == 200:
            entries = response.json().get("entries", "unknown")
            return CheckResult(
                name="org_cache",
                ok=True,
                detail=f"reachable at {org.shared_cache_url} ({entries} entries)",
                optional=True,
            )
        return CheckResult(
            name="org_cache",
            ok=False,
            detail=f"unreachable at {org.shared_cache_url} (HTTP {response.status_code})",
            optional=True,
        )
    except Exception as exc:
        return CheckResult(
            name="org_cache",
            ok=False,
            detail=f"unreachable at {org.shared_cache_url}: {exc}",
            optional=True,
        )
    finally:
        if own_client:
            http.close()


def _check_tunnel(
    tunnel_url: str,
    client: httpx.Client | None,
) -> CheckResult:
    normalized = tunnel_url.rstrip("/")
    if not normalized.startswith(("https://", "http://")):
        normalized = f"https://{normalized}"
    own_client = client is None
    http = client or httpx.Client(timeout=8.0)
    try:
        response = http.get(f"{normalized}/health")
        if response.status_code != 200:
            return CheckResult(
                name="tunnel",
                ok=False,
                detail=f"{normalized}/health returned HTTP {response.status_code}",
            )
        return CheckResult(
            name="tunnel",
            ok=True,
            detail=f"reachable at {normalized}",
        )
    except Exception as exc:
        return CheckResult(
            name="tunnel",
            ok=False,
            detail=f"unreachable at {normalized}: {exc}",
        )
    finally:
        if own_client:
            http.close()
