from __future__ import annotations

import os
import re
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


def _detect_cursor_configured() -> bool:
    try:
        from daari.clients.cursor.recipe import CursorSetupRecipe

        return CursorSetupRecipe().is_configured()
    except Exception:
        return False


def run_doctor(
    settings: Settings | None = None,
    *,
    httpx_client: httpx.Client | None = None,
    tunnel_url: str | None = None,
    cursor_configured: bool | None = None,
    strict: bool = False,
) -> list[CheckResult]:
    """Run health checks. Returns list of results (required + optional)."""
    results: list[CheckResult] = []
    cfg = settings or Settings.load()
    if cursor_configured is None:
        cursor_configured = _detect_cursor_configured()

    results.append(_check_python())
    results.append(_check_config(cfg))
    results.append(_check_config_keys())
    results.append(_check_master_key_overlap(cfg))
    results.append(_check_secret_refs(cfg))
    results.extend(_check_ollama(cfg, httpx_client, l4_required=cursor_configured))
    results.append(_check_embedding_endpoint(cfg, httpx_client))
    results.append(_check_mlx(cfg, httpx_client))
    results.append(_check_asr(cfg, httpx_client))
    results.append(_check_tts(cfg, httpx_client))
    results.append(_check_request_deadline(cfg))
    results.append(_check_tls_exposure(cfg))
    results.append(_check_local_pool_frontier_fallback(cfg))
    results.append(_check_otlp_logs(cfg))
    results.append(_check_frontier(cfg))
    results.append(_check_l1_diversity(cfg))
    results.append(_check_org(cfg))
    results.append(_check_org_cache(cfg, httpx_client))
    results.append(_check_fleet_artifacts(cfg))
    results.append(_check_fleet_cache(cfg))
    results.append(_check_scoped_cache_fleet(cfg))
    results.append(_check_soft_budget_ratio(cfg))
    results.append(_check_unbounded_rpd(cfg))
    results.append(_check_budget_webhook_secret(cfg))
    results.append(_check_helm_image_tag())
    results.append(_check_redis(cfg))
    results.append(_check_store_migrate(cfg, strict=strict))
    daemon = _check_daemon(cfg, httpx_client)
    results.append(daemon)
    results.append(_check_ready(cfg, httpx_client, daemon_ok=daemon.ok))
    results.append(_check_metrics_auth(cfg, httpx_client, daemon_ok=daemon.ok))
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


def _check_config_keys() -> CheckResult:
    """Mention typos in nested config so a silent policy hole is visible (#710)."""
    from daari.config.settings import Settings, load_user_config
    from daari.config.validate import unknown_config_keys

    keys = unknown_config_keys(load_user_config(None), Settings)
    if not keys:
        return CheckResult(name="config_keys", ok=True, detail="no unknown keys")
    shown = ", ".join(keys[:8])
    extra = f" (+{len(keys) - 8} more)" if len(keys) > 8 else ""
    return CheckResult(
        name="config_keys",
        ok=False,
        optional=True,
        detail=f"unknown keys: {shown}{extra} — run: daari config validate",
    )


def _check_master_key_overlap(settings: Settings) -> CheckResult:
    """Warn when a rotation overlap has more than two master keys (#711)."""
    count = len(settings.server.master_keys())
    if count <= 2:
        return CheckResult(
            name="master_keys",
            ok=True,
            detail=f"{count} active",
            optional=True,
        )
    return CheckResult(
        name="master_keys",
        ok=False,
        detail=(
            f"{count} master keys active — overlap should be temporary; "
            "remove the retired key after clients roll"
        ),
        optional=True,
    )


def _check_secret_refs(settings: Settings) -> CheckResult:
    """Issue #288: every configured secret:// ref must resolve before serve."""
    from daari.security.secret_refs import SecretRefError, iter_secret_refs, resolve_secret_ref

    refs = iter_secret_refs(settings)
    if not refs:
        return CheckResult(
            name="secret_refs",
            ok=True,
            detail="none configured (values may use secret://env-file|exec|keychain|oauth)",
            optional=True,
        )
    failures: list[str] = []
    for path, ref in refs:
        try:
            resolve_secret_ref(ref, register=False)
        except SecretRefError as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        return CheckResult(
            name="secret_refs",
            ok=False,
            detail="; ".join(failures),
        )
    return CheckResult(
        name="secret_refs",
        ok=True,
        detail=f"{len(refs)} ref(s) resolve",
        optional=True,
    )


def _check_ollama(
    settings: Settings,
    client: httpx.Client | None,
    *,
    l4_required: bool = False,
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
        embed_required = settings.cache.l1.enabled
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
                    f"{l4_model} found"
                    if l4_present
                    else (
                        f"{l4_model} missing — run: ollama pull {l4_model} "
                        + (
                            "(required: Cursor is configured and long prompts route to L4)"
                            if l4_required
                            else "(L4 falls back to L3)"
                        )
                    )
                ),
                optional=not l4_required,
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
                optional=not embed_required,
            ),
        ]
    except Exception as exc:
        return [
            CheckResult(name="ollama", ok=False, detail=f"unreachable at {base}: {exc}"),
            CheckResult(
                name="model", ok=False, detail=f"{l3_model} not checked (Ollama unreachable)"
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
    finally:
        if own_client:
            http.close()


def _embedding_vector(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    embedding = payload.get("embedding")
    return isinstance(embedding, list) and bool(embedding)


def _check_embedding_endpoint(
    settings: Settings,
    client: httpx.Client | None,
) -> CheckResult:
    """Live embed call. Skipped when L1 is off; required when L1 is on (#764)."""
    if not settings.cache.l1.enabled:
        return CheckResult(
            name="embedding_endpoint",
            ok=True,
            detail="skipped (cache.l1.enabled is false)",
            optional=True,
        )
    base = settings.ollama.base_url.rstrip("/")
    url = f"{base}/api/embeddings"
    model = settings.cache.l1.embedding_model
    own_client = client is None
    http = client or httpx.Client(timeout=5.0)
    try:
        response = http.post(url, json={"model": model, "prompt": "ok"})
        if response.status_code != 200:
            return CheckResult(
                name="embedding_endpoint",
                ok=False,
                detail=f"embed probe failed at {url} (HTTP {response.status_code})",
            )
        try:
            body = response.json()
        except Exception:
            body = None
        if not _embedding_vector(body):
            return CheckResult(
                name="embedding_endpoint",
                ok=False,
                detail=f"embed probe at {url} returned no vector",
            )
        return CheckResult(
            name="embedding_endpoint",
            ok=True,
            detail=f"embed probe ok at {url}",
        )
    except Exception as exc:
        return CheckResult(
            name="embedding_endpoint",
            ok=False,
            detail=f"embed probe failed at {url}: {exc}",
        )
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


def _check_l1_diversity(settings: Settings) -> CheckResult:
    """Trust PRD T1b: warn when a category serves few unique answers."""
    try:
        from daari.cache.semantic import SemanticCache

        cache = SemanticCache(
            path=str(settings.l1_cache_path),
            embedder=None,  # type: ignore[arg-type] — diversity_stats never embeds
            enabled=settings.cache.l1.enabled,
        )
        stats = cache.diversity_stats()
    except Exception as exc:
        return CheckResult(
            name="l1-diversity", ok=True, detail=f"not checked ({exc})", optional=True
        )
    suspicious = [
        f"{category} ({data['unique_answers']}/{data['entries']} unique)"
        for category, data in stats.items()
        if data["entries"] >= 10 and data["ratio"] < 0.5
    ]
    if suspicious:
        return CheckResult(
            name="l1-diversity",
            ok=False,
            detail=(
                "low answer diversity — possible cache false positives in: "
                + ", ".join(sorted(suspicious))
            ),
            optional=True,
        )
    return CheckResult(
        name="l1-diversity",
        ok=True,
        detail=f"healthy ({len(stats)} categories tracked)",
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
            detail="not running (start with: daari serve)",
            optional=True,
        )
    finally:
        if own_client:
            http.close()


def _check_redis(settings: Settings) -> CheckResult:
    """PING configured Redis when cache.backend=redis (#584)."""
    if getattr(settings.cache, "backend", "disk") != "redis":
        return CheckResult(
            name="redis",
            ok=True,
            detail="disabled (cache.backend!=redis)",
            optional=True,
        )
    redis_url = str(getattr(settings.cache, "redis_url", "") or "").strip()
    timeout = float(getattr(settings.cache, "redis_timeout_seconds", 2.0) or 2.0)
    if not redis_url:
        return CheckResult(
            name="redis",
            ok=False,
            detail="cache.backend=redis but cache.redis_url is empty",
            optional=True,
        )
    try:
        from daari.cache.redis_client import connect_redis

        client = connect_redis(redis_url, timeout_seconds=timeout)
        client.ping()
        return CheckResult(
            name="redis",
            ok=True,
            detail=f"PING ok ({redis_url})",
            optional=True,
        )
    except Exception as exc:
        return CheckResult(
            name="redis",
            ok=False,
            detail=(
                f"unreachable at {redis_url}: {type(exc).__name__}: {exc} — "
                "check redis_url / network, or set cache.backend=disk"
            ),
            optional=True,
        )


def _check_ready(
    settings: Settings,
    client: httpx.Client | None,
    *,
    daemon_ok: bool,
) -> CheckResult:
    """Mirror GET /ready when the daemon answered stats (#584)."""
    if not daemon_ok:
        return CheckResult(
            name="ready",
            ok=True,
            detail="skipped (daemon not running)",
            optional=True,
        )
    host = settings.server.host
    port = settings.server.port
    url = f"http://{host}:{port}/ready"
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    try:
        response = http.get(url)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        status = str(payload.get("status") or "").strip() or f"http_{response.status_code}"
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        checks_detail = ", ".join(f"{k}={v}" for k, v in checks.items()) if checks else ""
        detail = f"status={status}"
        if checks_detail:
            detail += f" ({checks_detail})"
        if status == "ready":
            return CheckResult(name="ready", ok=True, detail=detail, optional=True)
        if status in ("degraded", "not_ready"):
            return CheckResult(
                name="ready",
                ok=False,
                detail=f"{detail} — fix dependencies before traffic; see GET /ready",
                optional=True,
            )
        return CheckResult(
            name="ready",
            ok=False,
            detail=f"{detail} (HTTP {response.status_code})",
            optional=True,
        )
    except Exception as exc:
        return CheckResult(
            name="ready",
            ok=False,
            detail=f"GET /ready failed: {type(exc).__name__}: {exc}",
            optional=True,
        )
    finally:
        if own_client:
            http.close()


def _check_metrics_auth(
    settings: Settings,
    client: httpx.Client | None,
    *,
    daemon_ok: bool,
) -> CheckResult:
    """Warn when unauthenticated GET /metrics is locked by server.api_key (#596)."""
    if not daemon_ok:
        return CheckResult(
            name="metrics_auth",
            ok=True,
            detail="skipped (daemon not running)",
            optional=True,
        )
    if not getattr(settings.observability, "prometheus", True):
        return CheckResult(
            name="metrics_auth",
            ok=True,
            detail="disabled (observability.prometheus=false)",
            optional=True,
        )
    api_key = settings.server.primary_master_key()
    if not api_key:
        return CheckResult(
            name="metrics_auth",
            ok=True,
            detail="open (server.api_key unset — /metrics needs no Bearer)",
            optional=True,
        )
    host = settings.server.host
    port = settings.server.port
    url = f"http://{host}:{port}/metrics"
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    try:
        response = http.get(url)
        if response.status_code == 401:
            return CheckResult(
                name="metrics_auth",
                ok=False,
                detail=(
                    "GET /metrics returned 401 without Authorization — scrapers need "
                    "Bearer <server.api_key> (Helm: serviceMonitor.bearerTokenSecret), "
                    "or set observability.metrics_port for an auth-free scrape listener"
                ),
                optional=True,
            )
        if response.status_code == 200:
            return CheckResult(
                name="metrics_auth",
                ok=True,
                detail="open (unauthenticated GET /metrics returned 200)",
                optional=True,
            )
        return CheckResult(
            name="metrics_auth",
            ok=True,
            detail=f"HTTP {response.status_code} (no 401 lock detected)",
            optional=True,
        )
    except Exception as exc:
        return CheckResult(
            name="metrics_auth",
            ok=False,
            detail=f"GET /metrics failed: {type(exc).__name__}: {exc}",
            optional=True,
        )
    finally:
        if own_client:
            http.close()


def _check_fleet_artifacts(settings: Settings) -> CheckResult:
    """Warn when fleet signals collide with per-pod SQLite artifacts (#476, #478)."""
    raw = os.environ.get("DAARI_FLEET_REPLICAS", "1").strip() or "1"
    try:
        replicas = int(raw)
    except ValueError:
        return CheckResult(
            name="fleet_artifacts",
            ok=False,
            detail=f"DAARI_FLEET_REPLICAS={raw!r} is not an integer",
            optional=True,
        )

    sqlite_artifacts: list[str] = []
    if settings.batches.backend == "sqlite":
        sqlite_artifacts.append("batches.backend=sqlite")
    if settings.files.backend == "sqlite":
        sqlite_artifacts.append("files.backend=sqlite")
    if settings.responses.backend == "sqlite":
        sqlite_artifacts.append("responses.backend=sqlite")
    if settings.observability.backend == "sqlite":
        sqlite_artifacts.append("observability.backend=sqlite")
    audit_backend = getattr(settings.enterprise, "audit_backend", "sqlite") or "sqlite"
    if audit_backend == "sqlite":
        sqlite_artifacts.append("enterprise.audit_backend=sqlite")
    vk_backend = getattr(settings.server.virtual_keys, "backend", "sqlite") or "sqlite"
    if vk_backend == "sqlite":
        sqlite_artifacts.append("server.virtual_keys.backend=sqlite")

    signals: list[str] = []
    if replicas > 1:
        signals.append(f"DAARI_FLEET_REPLICAS={replicas}")
    if settings.cache.backend == "redis":
        signals.append("cache.backend=redis")
    if settings.observability.backend == "postgres":
        signals.append("observability.backend=postgres")

    # Artifacts that must be shared across a fleet.
    needs_shared = [
        part
        for part in sqlite_artifacts
        if part.startswith(("batches.", "files.", "responses.", "server.virtual_keys."))
    ]
    if settings.observability.backend == "sqlite" and signals:
        # Ledger split only matters when some other fleet signal is already on.
        needs_shared.append("observability.backend=sqlite")
    if audit_backend == "sqlite" and signals:
        needs_shared.append("enterprise.audit_backend=sqlite")

    if needs_shared and signals:
        return CheckResult(
            name="fleet_artifacts",
            ok=False,
            detail=(
                f"fleet signals ({', '.join(signals)}) with per-pod SQLite "
                f"({', '.join(needs_shared)}) — GET /v1/batches|files|responses "
                "can 404 across replicas, SSO-minted keys 401 on other pods, and "
                "audit export is incomplete; set batches.backend=postgres, "
                "files.backend=postgres, responses.backend=postgres, "
                "server.virtual_keys.backend=postgres, "
                "observability.backend=postgres, and "
                "enterprise.audit_backend=postgres (with observability.postgres_url), "
                "or keep a single replica"
            ),
            optional=True,
        )

    if not sqlite_artifacts and replicas > 1:
        detail = f"fleet_replicas={replicas}; artifact backends ok"
    elif signals and not needs_shared:
        detail = f"fleet signals ok ({', '.join(signals)}); shared backends configured"
    else:
        detail = f"fleet_replicas={replicas} (single-node SQLite defaults are fine)"
    return CheckResult(name="fleet_artifacts", ok=True, detail=detail, optional=True)


def _check_fleet_cache(settings: Settings) -> CheckResult:
    """Warn when multi-replica fleet runs without shared Redis L0/session (#510)."""
    raw = os.environ.get("DAARI_FLEET_REPLICAS", "1").strip() or "1"
    try:
        replicas = int(raw)
    except ValueError:
        return CheckResult(
            name="fleet_cache",
            ok=False,
            detail=f"DAARI_FLEET_REPLICAS={raw!r} is not an integer",
            optional=True,
        )

    multi = replicas > 1
    cache_backend = (settings.cache.backend or "disk").strip().lower()
    affinity = bool(getattr(settings.routing, "session_affinity", False))
    if not multi:
        return CheckResult(
            name="fleet_cache",
            ok=True,
            detail=f"fleet_replicas={replicas} (in-process L0/session fine)",
            optional=True,
        )

    problems: list[str] = []
    if cache_backend != "redis":
        problems.append(f"cache.backend={cache_backend} (L0 + singleflight are per-pod)")
    if affinity and cache_backend != "redis":
        problems.append(
            "routing.session_affinity=true without cache.backend=redis (pins stay per-process)"
        )
    if problems:
        return CheckResult(
            name="fleet_cache",
            ok=False,
            detail=(
                f"DAARI_FLEET_REPLICAS={replicas} with "
                + "; ".join(problems)
                + " — set cache.backend=redis so L0/session/singleflight "
                "share across replicas, or keep a single replica"
            ),
            optional=True,
        )
    return CheckResult(
        name="fleet_cache",
        ok=True,
        detail=f"fleet_replicas={replicas}; cache.backend=redis",
        optional=True,
    )


def _check_scoped_cache_fleet(settings: Settings) -> CheckResult:
    """Warn when tenant cache_scope meets disk cache on a multi-replica fleet (#891)."""
    raw = os.environ.get("DAARI_FLEET_REPLICAS", "1").strip() or "1"
    try:
        replicas = int(raw)
    except ValueError:
        return CheckResult(
            name="scoped_cache_fleet",
            ok=False,
            detail=f"DAARI_FLEET_REPLICAS={raw!r} is not an integer",
            optional=True,
        )

    cache_backend = (settings.cache.backend or "disk").strip().lower()
    if replicas <= 1:
        return CheckResult(
            name="scoped_cache_fleet",
            ok=True,
            detail=f"fleet_replicas={replicas} (scoped cache fine on single node)",
            optional=True,
        )
    if cache_backend == "redis":
        return CheckResult(
            name="scoped_cache_fleet",
            ok=True,
            detail=f"fleet_replicas={replicas}; cache.backend=redis",
            optional=True,
        )
    if not getattr(settings.server.virtual_keys, "enabled", False):
        return CheckResult(
            name="scoped_cache_fleet",
            ok=True,
            detail="virtual keys disabled (no tenant cache_scope)",
            optional=True,
        )

    try:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        store = virtual_key_store_from_settings(settings)
    except Exception as exc:
        return CheckResult(
            name="scoped_cache_fleet",
            ok=True,
            detail=f"virtual-key store unread ({exc})",
            optional=True,
        )

    scoped: list[str] = []
    for key in store.list():
        scope = (getattr(key, "cache_scope", None) or "global").strip().lower()
        if scope != "global":
            scoped.append(f"key {key.name}={scope}")
    try:
        teams = store.list_teams() if hasattr(store, "list_teams") else []
    except Exception:
        teams = []
    for team in teams:
        scope = (getattr(team, "cache_scope", None) or "global").strip().lower()
        if scope != "global":
            scoped.append(f"team {team.name}={scope}")

    if not scoped:
        return CheckResult(
            name="scoped_cache_fleet",
            ok=True,
            detail=f"fleet_replicas={replicas}; all cache_scope=global",
            optional=True,
        )

    shown = ", ".join(scoped[:6])
    extra = f" (+{len(scoped) - 6} more)" if len(scoped) > 6 else ""
    return CheckResult(
        name="scoped_cache_fleet",
        ok=False,
        detail=(
            f"DAARI_FLEET_REPLICAS={replicas} with cache.backend={cache_backend} "
            f"and non-global cache_scope ({shown}{extra}) — tenant L0/L1 stays "
            "per-pod; set cache.backend=redis so scoped keys share across replicas, "
            "or keep a single replica"
        ),
        optional=True,
    )


def _has_request_quota_windows(settings: Settings) -> bool:
    """True when any key/team budget window carries a request cap."""
    if not getattr(settings.server.virtual_keys, "enabled", False):
        return False
    try:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        store = virtual_key_store_from_settings(settings)
    except Exception:
        return False
    for key in store.list():
        for window in key.budget_windows:
            if int(getattr(window, "max_requests", 0) or 0) > 0:
                return True
        if int(getattr(key, "rpm", 0) or 0) > 0 or int(getattr(key, "tpm", 0) or 0) > 0:
            return True
    try:
        teams = getattr(store, "list_teams", None)
        if callable(teams):
            for team in teams():
                for window in getattr(team, "budget_windows", ()) or ():
                    if int(getattr(window, "max_requests", 0) or 0) > 0:
                        return True
    except Exception:
        pass
    return False


def _unbounded_rpd_names(settings: Settings) -> list[str]:
    """Keys and teams that can hold rpm all day because rpd is unset (#732)."""
    if not getattr(settings.server.virtual_keys, "enabled", False):
        return []
    try:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        store = virtual_key_store_from_settings(settings)
    except Exception:
        return []
    names: list[str] = []
    for key in store.list():
        if int(getattr(key, "rpm", 0) or 0) > 0 and int(getattr(key, "rpd", 0) or 0) == 0:
            names.append(f"key {key.name}")
    try:
        teams = store.list_teams() if hasattr(store, "list_teams") else []
    except Exception:
        teams = []
    for team in teams:
        if int(getattr(team, "rpm", 0) or 0) > 0 and int(getattr(team, "rpd", 0) or 0) == 0:
            names.append(f"team {team.name}")
    return names


def _check_unbounded_rpd(settings: Settings) -> CheckResult:
    """Warn when rpm is set and the UTC-day request cap is unlimited."""
    names = _unbounded_rpd_names(settings)
    if not names:
        return CheckResult(
            name="rpd",
            ok=True,
            detail="no key or team has rpm with rpd unlimited",
            optional=True,
        )
    shown = ", ".join(names[:8])
    extra = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
    return CheckResult(
        name="rpd",
        ok=False,
        detail=f"rpm set and rpd unlimited (0) on {shown}{extra}",
        optional=True,
    )


def _has_usd_budget_windows(settings: Settings) -> bool:
    """True when any key/team budget window carries a USD cap (#637)."""
    if not getattr(settings.server.virtual_keys, "enabled", False):
        return False
    try:
        from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings

        store = virtual_key_store_from_settings(settings)
    except Exception:
        return False
    for key in store.list():
        for window in key.budget_windows:
            if float(getattr(window, "max_usd", 0) or 0) > 0:
                return True
    try:
        teams = getattr(store, "list_teams", None)
        if callable(teams):
            for team in teams():
                for window in getattr(team, "budget_windows", ()) or ():
                    if float(getattr(window, "max_usd", 0) or 0) > 0:
                        return True
    except Exception:
        pass
    return False


def _check_soft_budget_ratio(settings: Settings) -> CheckResult:
    """Warn when soft_budget_ratio=0 disables soft bands while hard caps remain (#530)."""
    ratio = float(getattr(settings.frontier, "soft_budget_ratio", 0.8) or 0.0)
    rl = settings.rate_limit
    rate_caps = (
        int(getattr(rl, "rpm", 0) or 0) > 0
        or int(getattr(rl, "tpm", 0) or 0) > 0
        or int(getattr(rl, "model_rpm", 0) or 0) > 0
        or int(getattr(rl, "model_tpm", 0) or 0) > 0
    )
    quota_caps = _has_request_quota_windows(settings)
    usd_caps = _has_usd_budget_windows(settings)
    if ratio > 0:
        return CheckResult(
            name="soft_budget_ratio",
            ok=True,
            detail=f"frontier.soft_budget_ratio={ratio}",
            optional=True,
        )
    if not rate_caps and not quota_caps and not usd_caps:
        return CheckResult(
            name="soft_budget_ratio",
            ok=True,
            detail="soft_budget_ratio=0 and no request-quota/RPM/USD caps configured",
            optional=True,
        )
    reasons: list[str] = []
    if rate_caps:
        reasons.append("rate_limit rpm/tpm")
    if quota_caps:
        reasons.append("request-quota or per-key rpm/tpm")
    if usd_caps:
        reasons.append("USD budget windows")
    return CheckResult(
        name="soft_budget_ratio",
        ok=False,
        detail=(
            f"frontier.soft_budget_ratio=0 with {' + '.join(reasons)} — soft "
            "402/429 warnings are disabled while hard caps remain; set "
            "soft_budget_ratio (e.g. 0.8) so agents can back off before cliffs"
        ),
        optional=True,
    )


def _check_budget_webhook_secret(settings: Settings) -> CheckResult:
    """Warn when a budget webhook URL is set without a signing secret (#496)."""
    url = (settings.alerts.budget_webhook_url or "").strip()
    secret = (settings.alerts.budget_webhook_secret or "").strip()
    if url and not secret:
        return CheckResult(
            name="budget_webhook_secret",
            ok=False,
            detail=(
                "alerts.budget_webhook_url is set but alerts.budget_webhook_secret "
                "is empty — receivers cannot verify origin; set a secret "
                "(secret:// ok) or clear the URL"
            ),
            optional=True,
        )
    if url:
        detail = "budget webhook URL + secret configured"
    else:
        detail = "budget webhook disabled (empty URL)"
    return CheckResult(name="budget_webhook_secret", ok=True, detail=detail, optional=True)


def _check_store_migrate(settings: Settings, *, strict: bool = False) -> CheckResult:
    """Warn when SQLite stores have pending additive migrations (#942)."""
    from daari.setup.migrate import inspect_stores

    try:
        notes = inspect_stores(settings)
    except Exception as exc:
        return CheckResult(
            name="store_migrate",
            ok=False,
            detail=f"inspect failed: {exc}",
            optional=not strict,
        )
    pending = [n for n in notes if n.status == "pending"]
    if not pending:
        return CheckResult(
            name="store_migrate",
            ok=True,
            detail="no pending store migrations",
            optional=not strict,
        )
    detail = "; ".join(
        f"{n.name}: {', '.join(n.pending)}" for n in pending
    ) + " — run: daari migrate"
    return CheckResult(
        name="store_migrate",
        ok=False,
        detail=detail,
        optional=not strict,
    )


def _check_helm_image_tag() -> CheckResult:
    """Optional: chart image.tag behind daari.__version__ when values.yaml is present (#478)."""
    from daari import __version__

    values = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "daari" / "values.yaml"
    if not values.is_file():
        return CheckResult(
            name="helm_image_tag",
            ok=True,
            detail="chart values.yaml not present (skip)",
            optional=True,
        )
    try:
        text = values.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult(
            name="helm_image_tag",
            ok=True,
            detail=f"could not read chart values ({exc})",
            optional=True,
        )
    match = re.search(r"(?m)^\s*tag:\s*[\"']?([0-9]+(?:\.[0-9]+)*)[\"']?\s*$", text)
    if not match:
        return CheckResult(
            name="helm_image_tag",
            ok=True,
            detail="image.tag not found in chart values",
            optional=True,
        )
    tag = match.group(1)
    if tag != __version__:
        return CheckResult(
            name="helm_image_tag",
            ok=False,
            detail=(
                f"deploy/helm/daari/values.yaml image.tag={tag} behind package "
                f"{__version__} — bump Chart.yaml appVersion and values image.tag "
                "(see docs/developer/guides/operations/capacity-helm.md)"
            ),
            optional=True,
        )
    return CheckResult(
        name="helm_image_tag",
        ok=True,
        detail=f"chart image.tag={tag} matches package",
        optional=True,
    )


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


def _check_mlx(settings: Settings, client: httpx.Client | None) -> CheckResult:
    """MLX backend reachability (issue #97) — optional, only when enabled."""
    mlx = settings.mlx
    if not mlx.enabled:
        return CheckResult(name="mlx", ok=True, detail="disabled", optional=True)
    if not mlx.models:
        return CheckResult(
            name="mlx",
            ok=False,
            detail="enabled but mlx.models maps no tiers",
            optional=True,
        )
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    url = f"{mlx.base_url.rstrip('/')}/v1/models"
    try:
        response = http.get(url)
        if response.status_code == 200:
            tiers = ", ".join(sorted(mlx.models))
            return CheckResult(
                name="mlx",
                ok=True,
                detail=f"mlx_lm.server reachable at {mlx.base_url} (tiers: {tiers})",
                optional=True,
            )
        return CheckResult(
            name="mlx",
            ok=False,
            detail=f"unreachable at {mlx.base_url} (HTTP {response.status_code})",
            optional=True,
        )
    except Exception as exc:
        return CheckResult(
            name="mlx",
            ok=False,
            detail=f"unreachable at {mlx.base_url}: {exc} — start with: mlx_lm.server --port 11440",
            optional=True,
        )
    finally:
        if own_client:
            http.close()


def _check_local_pool_frontier_fallback(settings: Settings) -> CheckResult:
    """Surface routing.local_pool.frontier_fallback misconfig (#879)."""
    from daari.config.validate import local_pool_frontier_fallback_findings

    findings = local_pool_frontier_fallback_findings(settings)
    if not findings:
        enabled = bool(
            getattr(getattr(settings.routing, "local_pool", None), "frontier_fallback", False)
        )
        detail = (
            "routing.local_pool.frontier_fallback configured"
            if enabled
            else "routing.local_pool.frontier_fallback=false"
        )
        return CheckResult(
            name="local_pool_frontier_fallback",
            ok=True,
            detail=detail,
            optional=True,
        )
    return CheckResult(
        name="local_pool_frontier_fallback",
        ok=False,
        detail="; ".join(findings),
        optional=True,
    )


def _check_otlp_logs(settings: Settings) -> CheckResult:
    """Warn when otlp_logs is on but no OTLP endpoint is configured (#878)."""
    enabled = bool(getattr(settings.observability, "otlp_logs", False))
    if not enabled:
        return CheckResult(
            name="otlp_logs",
            ok=True,
            detail="observability.otlp_logs=false",
            optional=True,
        )
    endpoint = (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if endpoint:
        return CheckResult(
            name="otlp_logs",
            ok=True,
            detail=f"otlp_logs enabled; OTEL_EXPORTER_OTLP_ENDPOINT={endpoint}",
            optional=True,
        )
    return CheckResult(
        name="otlp_logs",
        ok=False,
        detail=(
            "observability.otlp_logs is true but OTEL_EXPORTER_OTLP_ENDPOINT is "
            "unset — gateway events will not export as OTLP logs; set the "
            "endpoint (same collector as traces/metrics) or disable otlp_logs"
        ),
        optional=True,
    )


def _check_request_deadline(settings: Settings) -> CheckResult:
    """Warn when no wall-clock request budget is configured (#867)."""
    raw = getattr(settings.upstream, "request_deadline_seconds", None)
    try:
        seconds = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds > 0:
        return CheckResult(
            name="request_deadline",
            ok=True,
            detail=f"upstream.request_deadline_seconds={seconds}",
            optional=True,
        )
    return CheckResult(
        name="request_deadline",
        ok=False,
        detail=(
            "upstream.request_deadline_seconds is unset or 0 — requests use "
            "per-tier timeouts only; set a positive wall-clock budget (or send "
            "X-Daari-Deadline-Ms) so escalation stops with 504 before runaway "
            "local/frontier hops"
        ),
        optional=True,
    )


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"})


def _is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower().strip("[]")
    return normalized in _LOOPBACK_HOSTS


def _check_tls_exposure(settings: Settings) -> CheckResult:
    """Warn when auth is on, TLS is off, and the bind host is non-loopback (#932)."""
    api_key = settings.server.primary_master_key()
    tls = getattr(settings.server, "tls", None)
    cert = str(getattr(tls, "cert_file", "") or "").strip()
    key = str(getattr(tls, "key_file", "") or "").strip()
    tls_on = bool(cert and key)
    host = str(settings.server.host or "").strip()
    if not api_key:
        return CheckResult(
            name="tls_exposure",
            ok=True,
            detail="skipped (server.api_key unset)",
            optional=True,
        )
    if tls_on:
        detail = "HTTPS enabled (server.tls.cert_file + key_file)"
        if str(getattr(tls, "client_ca", "") or "").strip():
            detail += " with mTLS (client_ca)"
        return CheckResult(name="tls_exposure", ok=True, detail=detail, optional=True)
    if _is_loopback_host(host):
        return CheckResult(
            name="tls_exposure",
            ok=True,
            detail=f"loopback bind ({host}) — plaintext acceptable for local-only",
            optional=True,
        )
    return CheckResult(
        name="tls_exposure",
        ok=False,
        detail=(
            f"auth enabled on non-loopback host {host!r} without TLS — API keys "
            "travel in plaintext; set server.tls.cert_file + key_file "
            "(or --tls-cert/--tls-key), or terminate TLS at a reverse proxy/ingress"
        ),
        optional=True,
    )


def _check_asr(settings: Settings, client: httpx.Client | None) -> CheckResult:
    """Local ASR reachability. Optional; unconfigured transcriptions stay 501."""
    asr = settings.asr
    base = str(asr.base_url or "").strip().rstrip("/")
    if base:
        own_client = client is None
        http = client or httpx.Client(timeout=3.0)
        url = f"{base}/models"
        try:
            response = http.get(url)
        except Exception as exc:
            return CheckResult(
                name="asr",
                ok=False,
                detail=f"unreachable at {base}: {exc}",
                optional=True,
            )
        finally:
            if own_client:
                http.close()
        if response.status_code == 200:
            return CheckResult(
                name="asr",
                ok=True,
                detail=f"reachable at {base}",
                optional=True,
            )
        return CheckResult(
            name="asr",
            ok=False,
            detail=f"unreachable at {base} (HTTP {response.status_code})",
            optional=True,
        )
    if asr.frontier_fallback:
        if not settings.frontier.enabled:
            return CheckResult(
                name="asr",
                ok=False,
                detail="asr.frontier_fallback is true but frontier.enabled is false",
                optional=True,
            )
        from daari.gateway.transcriptions import resolve_asr_target

        target = resolve_asr_target(settings)
        if target is None or not target.api_key:
            return CheckResult(
                name="asr",
                ok=False,
                detail="asr.frontier_fallback is true but no frontier API key resolves",
                optional=True,
            )
        return CheckResult(
            name="asr",
            ok=True,
            detail="frontier fallback configured",
            optional=True,
        )
    return CheckResult(
        name="asr",
        ok=True,
        detail="not configured (POST /v1/audio/transcriptions returns 501)",
        optional=True,
    )


def _check_tts(settings: Settings, client: httpx.Client | None) -> CheckResult:
    """Local TTS reachability. Optional; unconfigured speech stays 501 (#869)."""
    tts = settings.tts
    base = str(tts.base_url or "").strip().rstrip("/")
    if not base:
        return CheckResult(
            name="tts",
            ok=True,
            detail="not configured (POST /v1/audio/speech returns 501)",
            optional=True,
        )
    own_client = client is None
    http = client or httpx.Client(timeout=3.0)
    url = f"{base}/models"
    try:
        response = http.get(url)
    except Exception as exc:
        return CheckResult(
            name="tts",
            ok=False,
            detail=f"unreachable at {base}: {exc}",
            optional=True,
        )
    finally:
        if own_client:
            http.close()
    if response.status_code == 200:
        return CheckResult(
            name="tts",
            ok=True,
            detail=f"reachable at {base}",
            optional=True,
        )
    return CheckResult(
        name="tts",
        ok=False,
        detail=f"unreachable at {base} (HTTP {response.status_code})",
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
