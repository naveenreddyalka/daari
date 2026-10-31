"""Reconcile local spend ledger against Anthropic Usage/Cost Analytics (#2033).

Fetches ``GET /v1/organizations/analytics/cost`` (and usage) with the
``analytics-usage-cost-2026-08-24`` beta header, groups by model + day, and
compares provider ``amount`` (discounted, cents→USD) to daari's ledger rollup
for Anthropic-served rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from daari.enterprise.enforcement_sync import DEFAULT_BASE_URL
from daari.router.anthropic_messages import ANTHROPIC_VERSION

ANALYTICS_BETA = "analytics-usage-cost-2026-08-24"
MAX_WINDOW_DAYS = 31


@dataclass
class ReconcileRow:
    day: str
    model: str
    daari_cost_usd: float
    provider_amount_usd: float
    provider_list_amount_usd: float
    drift_pct: float
    daari_tokens: int
    provider_tokens: int


@dataclass
class ReconcileResult:
    rows: list[ReconcileRow]
    exceeded: list[ReconcileRow]
    threshold_pct: float


class AnalyticsReconcileError(ValueError):
    """Operator-facing reconcile failure (missing key, window, provider)."""


def _parse_iso(raw: str) -> datetime:
    text = (raw or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_window(since: str, until: str) -> tuple[str, str]:
    """Return ISO bounds; raise when the span exceeds 31 days."""
    start = _parse_iso(since)
    end = _parse_iso(until)
    if end <= start:
        raise AnalyticsReconcileError("--until must be after --since")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise AnalyticsReconcileError(
            f"Anthropic analytics window is at most {MAX_WINDOW_DAYS} days; "
            "narrow --since/--until"
        )
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def cents_to_usd(raw: Any) -> float:
    """Anthropic amounts are decimal strings in cents with six decimal places."""
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw) / 100.0
    except (TypeError, ValueError):
        return 0.0


def resolve_anthropic_admin_key(settings: Any) -> str:
    """Admin/analytics key: ``anthropic.analytics_api_key`` or frontier key."""
    from daari.security.secret_refs import current_secret

    anthropic = getattr(settings, "anthropic", None)
    raw = str(getattr(anthropic, "analytics_api_key", "") or "").strip()
    if raw:
        resolved = current_secret(raw) if raw.startswith("secret://") else raw
        if resolved:
            return str(resolved).strip()
    key = settings.resolve_frontier_api_key() or ""
    return str(key).strip()


def _analytics_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": ANALYTICS_BETA,
        "content-type": "application/json",
    }


def _paginate_analytics(
    *,
    client: Any,
    root: str,
    path: str,
    api_key: str,
    starting_at: str,
    ending_at: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page: str | None = None
    while True:
        params: list[tuple[str, str]] = [
            ("starting_at", starting_at),
            ("ending_at", ending_at),
            ("time_bucket_width", "1d"),
            ("group_by[]", "model"),
            ("order_by", "time"),
            ("order", "asc"),
            ("limit", "100"),
        ]
        if page:
            params.append(("page", page))
        url = f"{root}{path}?{urlencode(params)}"
        response = client.get(url, headers=_analytics_headers(api_key))
        response.raise_for_status()
        body = response.json()
        for row in body.get("data") or []:
            if isinstance(row, dict):
                out.append(row)
        next_page = body.get("has_more") and body.get("next_page")
        if not next_page:
            break
        page = str(next_page)
    return out


def fetch_anthropic_cost_rows(
    api_key: str,
    *,
    starting_at: str,
    ending_at: str,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    import httpx

    key = (api_key or "").strip()
    if not key:
        raise AnalyticsReconcileError(
            "Anthropic admin/analytics API key missing — set "
            "anthropic.analytics_api_key (secret:// ok) or a frontier key"
        )
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    with httpx.Client(transport=transport, timeout=timeout) as client:
        return _paginate_analytics(
            client=client,
            root=root,
            path="/v1/organizations/analytics/cost",
            api_key=key,
            starting_at=starting_at,
            ending_at=ending_at,
        )


def fetch_anthropic_usage_rows(
    api_key: str,
    *,
    starting_at: str,
    ending_at: str,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    import httpx

    key = (api_key or "").strip()
    if not key:
        raise AnalyticsReconcileError(
            "Anthropic admin/analytics API key missing — set "
            "anthropic.analytics_api_key (secret:// ok) or a frontier key"
        )
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    with httpx.Client(transport=transport, timeout=timeout) as client:
        return _paginate_analytics(
            client=client,
            root=root,
            path="/v1/organizations/analytics/usage",
            api_key=key,
            starting_at=starting_at,
            ending_at=ending_at,
        )


def _row_day(row: dict[str, Any]) -> str:
    start = str(row.get("starting_at") or "")
    if "T" in start:
        return start.split("T", 1)[0]
    return start[:10]


def _row_model(row: dict[str, Any]) -> str:
    group = row.get("group") or {}
    if isinstance(group, dict):
        return str(group.get("model") or "").strip()
    return ""


def provider_cost_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    index: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        day = _row_day(row)
        model = _row_model(row)
        if not day or not model:
            continue
        cost = row.get("cost") if isinstance(row.get("cost"), dict) else {}
        key = (day, model)
        slot = index.setdefault(
            key, {"amount_usd": 0.0, "list_amount_usd": 0.0}
        )
        slot["amount_usd"] += cents_to_usd(cost.get("amount"))
        slot["list_amount_usd"] += cents_to_usd(cost.get("list_amount"))
    return index


def provider_usage_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    index: dict[tuple[str, str], int] = {}
    for row in rows:
        day = _row_day(row)
        model = _row_model(row)
        if not day or not model:
            continue
        usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
        tokens = int(usage.get("total_tokens") or 0)
        key = (day, model)
        index[key] = index.get(key, 0) + tokens
    return index


def local_anthropic_rollup(
    ledger: Any,
    *,
    since: str,
    until: str,
) -> dict[tuple[str, str], dict[str, float]]:
    """Sum ledger cost/tokens per (day, model) for Anthropic-served rows."""
    if not getattr(ledger, "enabled", False):
        return {}
    ph = "%s" if hasattr(ledger, "dsn") else "?"
    sql = (
        f"SELECT substr(ts, 1, 10) AS day, model, "
        f"SUM(cost_usd) AS cost_usd, "
        f"SUM(input_tokens + output_tokens) AS tokens "
        f"FROM spend_requests WHERE ts >= {ph} AND ts < {ph} "
        f"AND ("
        f"  lower(provider) LIKE {ph} OR lower(provider) LIKE {ph} "
        f"  OR lower(model) LIKE {ph}"
        f") "
        f"GROUP BY day, model ORDER BY day, model"
    )
    params: list[Any] = [since, until, "%anthropic%", "%claude%", "claude%"]
    try:
        with ledger._lock, ledger._connect() as conn:
            if hasattr(ledger, "dsn"):
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
            else:
                rows = conn.execute(sql, params).fetchall()
    except Exception:
        return {}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for day, model, cost, tokens in rows:
        key = (str(day or ""), str(model or ""))
        if not key[0] or not key[1]:
            continue
        out[key] = {
            "cost_usd": float(cost or 0.0),
            "tokens": float(tokens or 0),
        }
    return out


def drift_pct(daari: float, provider: float) -> float:
    base = max(abs(provider), abs(daari), 1e-9)
    return abs(daari - provider) / base * 100.0


def reconcile(
    *,
    api_key: str,
    ledger: Any,
    since: str,
    until: str,
    threshold_pct: float = 5.0,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
) -> ReconcileResult:
    starting_at, ending_at = validate_window(since, until)
    cost_rows = fetch_anthropic_cost_rows(
        api_key,
        starting_at=starting_at,
        ending_at=ending_at,
        base_url=base_url,
        transport=transport,
    )
    usage_rows = fetch_anthropic_usage_rows(
        api_key,
        starting_at=starting_at,
        ending_at=ending_at,
        base_url=base_url,
        transport=transport,
    )
    provider_cost = provider_cost_index(cost_rows)
    provider_usage = provider_usage_index(usage_rows)
    local = local_anthropic_rollup(ledger, since=starting_at, until=ending_at)
    keys = sorted(set(provider_cost) | set(local) | set(provider_usage))
    rows: list[ReconcileRow] = []
    exceeded: list[ReconcileRow] = []
    for key in keys:
        day, model = key
        local_slot = local.get(key) or {"cost_usd": 0.0, "tokens": 0.0}
        prov = provider_cost.get(key) or {
            "amount_usd": 0.0,
            "list_amount_usd": 0.0,
        }
        daari_cost = float(local_slot["cost_usd"])
        provider_amount = float(prov["amount_usd"])
        pct = drift_pct(daari_cost, provider_amount)
        row = ReconcileRow(
            day=day,
            model=model,
            daari_cost_usd=daari_cost,
            provider_amount_usd=provider_amount,
            provider_list_amount_usd=float(prov["list_amount_usd"]),
            drift_pct=pct,
            daari_tokens=int(local_slot["tokens"]),
            provider_tokens=int(provider_usage.get(key, 0)),
        )
        rows.append(row)
        if pct > threshold_pct:
            exceeded.append(row)
    return ReconcileResult(
        rows=rows, exceeded=exceeded, threshold_pct=threshold_pct
    )


def format_reconcile_table(rows: list[ReconcileRow]) -> str:
    if not rows:
        return "No overlapping Anthropic analytics / ledger rows."
    header = (
        f"{'day':<12} {'model':<28} {'daari_$':>10} {'provider_$':>10} "
        f"{'drift_%':>8} {'daari_tok':>10} {'prov_tok':>10}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.day:<12} {row.model:<28} {row.daari_cost_usd:10.4f} "
            f"{row.provider_amount_usd:10.4f} {row.drift_pct:8.2f} "
            f"{row.daari_tokens:10d} {row.provider_tokens:10d}"
        )
    return "\n".join(lines)
