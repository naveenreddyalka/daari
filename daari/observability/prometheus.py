"""Prometheus exposition format for /metrics (Roadmap F3 / issue #107).

Hand-rolled — no prometheus-client dependency. Scrapers only need the
text/plain; version=0.0.4 content type and the HELP/TYPE/sample lines.
"""

from __future__ import annotations

from typing import Any

from daari.observability.metrics import LATENCY_BUCKETS_MS, Metrics


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**kwargs: str) -> str:
    if not kwargs:
        return ""
    parts = [f'{key}="{_escape_label(str(value))}"' for key, value in kwargs.items()]
    return "{" + ",".join(parts) + "}"


def render_prometheus(
    metrics: Metrics,
    *,
    budget_state: dict[str, Any] | None = None,
    false_hit_rate: float | None = None,
    rate_limit: dict[str, Any] | None = None,
    backend_pool: dict[str, Any] | None = None,
) -> str:
    """Render the current Metrics snapshot (plus optional gauges) as exposition text."""
    snap = metrics.snapshot(include_histograms=True)
    lines: list[str] = []

    lines.append("# HELP daari_requests_total Total requests handled, by tier.")
    lines.append("# TYPE daari_requests_total counter")
    if not snap["tiers"]:
        lines.append("daari_requests_total 0")
    else:
        for tier, stats in snap["tiers"].items():
            lines.append(f"daari_requests_total{_labels(tier=tier)} {stats['count']}")

    lines.append("# HELP daari_cache_hits_total Cache hits recorded, by tier.")
    lines.append("# TYPE daari_cache_hits_total counter")
    for tier, stats in snap["tiers"].items():
        lines.append(f"daari_cache_hits_total{_labels(tier=tier)} {stats['cache_hits']}")

    lines.append("# HELP daari_errors_total Gateway/router errors.")
    lines.append("# TYPE daari_errors_total counter")
    lines.append(f"daari_errors_total {snap['errors']}")

    lines.append("# HELP daari_escalations_total Local→frontier (L6) escalations.")
    lines.append("# TYPE daari_escalations_total counter")
    lines.append(f"daari_escalations_total {snap['escalations']}")
    lines.append(
        "# HELP daari_cache_false_hits_avoided_total L1 hits vetoed by verification."
    )
    lines.append("# TYPE daari_cache_false_hits_avoided_total counter")
    lines.append(
        f"daari_cache_false_hits_avoided_total {snap.get('cache_false_hits_avoided', 0)}"
    )
    lines.append(
        "# HELP daari_upstream_retries_total Transient upstream failures retried."
    )
    lines.append("# TYPE daari_upstream_retries_total counter")
    lines.append(f"daari_upstream_retries_total {snap.get('upstream_retries', 0)}")

    lines.append(
        "# HELP daari_tier_shadow_samples_total Local-tier answers replayed at a "
        "comparison tier, by whether the answers agreed."
    )
    lines.append("# TYPE daari_tier_shadow_samples_total counter")
    shadow = snap.get("tier_shadow") or {}
    for key, label in (("agree", "true"), ("disagree", "false")):
        if key in shadow:
            lines.append(f"daari_tier_shadow_samples_total{_labels(agreed=label)} {shadow[key]}")

    lines.append("# HELP daari_guardrail_trips_total Guardrail actions taken.")
    lines.append("# TYPE daari_guardrail_trips_total counter")
    for action, count in snap["guardrails"].items():
        lines.append(f"daari_guardrail_trips_total{_labels(action=action)} {count}")

    lines.append("# HELP daari_boundary_decisions_total Product-boundary classifications.")
    lines.append("# TYPE daari_boundary_decisions_total counter")
    for key, count in (snap.get("boundaries") or {}).items():
        if ":" in key:
            stage, label = key.split(":", 1)
        else:
            stage, label = "unknown", key
        lines.append(
            f"daari_boundary_decisions_total{_labels(stage=stage, label=label)} {count}"
        )

    lines.append(
        "# HELP daari_request_latency_ms Request latency histogram in milliseconds, by tier."
    )
    lines.append("# TYPE daari_request_latency_ms histogram")
    for tier, stats in snap["tiers"].items():
        buckets = stats.get("latency_buckets") or {}
        cumulative = 0
        for bound in LATENCY_BUCKETS_MS:
            cumulative += buckets.get(bound, 0)
            lines.append(
                f"daari_request_latency_ms_bucket{_labels(tier=tier, le=str(bound))} {cumulative}"
            )
        cumulative += buckets.get("+Inf", 0)
        lines.append(
            f'daari_request_latency_ms_bucket{_labels(tier=tier, le="+Inf")} {cumulative}'
        )
        lines.append(
            f"daari_request_latency_ms_sum{_labels(tier=tier)} {stats['total_latency_ms']}"
        )
        lines.append(f"daari_request_latency_ms_count{_labels(tier=tier)} {stats['count']}")

    if budget_state is not None:
        lines.append("# HELP daari_frontier_spend_usd Estimated frontier spend in USD.")
        lines.append("# TYPE daari_frontier_spend_usd gauge")
        daily = float(budget_state.get("daily_spend_usd") or 0.0)
        monthly = float(budget_state.get("monthly_spend_usd") or 0.0)
        lines.append(f'daari_frontier_spend_usd{_labels(window="daily")} {daily}')
        lines.append(f'daari_frontier_spend_usd{_labels(window="monthly")} {monthly}')
        lines.append("# HELP daari_frontier_budget_usd Configured frontier budget in USD.")
        lines.append("# TYPE daari_frontier_budget_usd gauge")
        lines.append(
            f'daari_frontier_budget_usd{_labels(window="daily")} '
            f'{float(budget_state.get("daily_budget_usd") or 0.0)}'
        )
        lines.append(
            f'daari_frontier_budget_usd{_labels(window="monthly")} '
            f'{float(budget_state.get("monthly_budget_usd") or 0.0)}'
        )
        state = str(budget_state.get("state") or "ok")
        lines.append("# HELP daari_frontier_budget_state Budget state as a one-hot gauge.")
        lines.append("# TYPE daari_frontier_budget_state gauge")
        for candidate in ("ok", "soft", "exceeded"):
            lines.append(
                f"daari_frontier_budget_state{_labels(state=candidate)} "
                f"{1 if candidate == state else 0}"
            )

    if false_hit_rate is not None:
        lines.append(
            "# HELP daari_cache_false_hit_rate Shadow-sampled L1 false-hit rate (0..1)."
        )
        lines.append("# TYPE daari_cache_false_hit_rate gauge")
        lines.append(f"daari_cache_false_hit_rate {float(false_hit_rate)}")

    if rate_limit is not None:
        lines.append("# HELP daari_rate_limit_limit Configured rate / concurrency limits.")
        lines.append("# TYPE daari_rate_limit_limit gauge")
        lines.append(
            f'daari_rate_limit_limit{_labels(kind="rpm")} {int(rate_limit.get("rpm_limit") or 0)}'
        )
        lines.append(
            f'daari_rate_limit_limit{_labels(kind="tpm")} {int(rate_limit.get("tpm_limit") or 0)}'
        )
        lines.append("# HELP daari_rate_limit_in_flight Current in-flight requests.")
        lines.append("# TYPE daari_rate_limit_in_flight gauge")
        lines.append(f"daari_rate_limit_in_flight {int(rate_limit.get('in_flight') or 0)}")
        lines.append("# HELP daari_rate_limit_in_flight_max Configured in-flight cap.")
        lines.append("# TYPE daari_rate_limit_in_flight_max gauge")
        lines.append(
            f"daari_rate_limit_in_flight_max {int(rate_limit.get('in_flight_max') or 0)}"
        )
        lines.append("# HELP daari_rate_limit_queued Requests waiting on the concurrency gate.")
        lines.append("# TYPE daari_rate_limit_queued gauge")
        lines.append(f"daari_rate_limit_queued {int(rate_limit.get('queued') or 0)}")

    pool = backend_pool or {}
    backends = list(pool.get("backends") or [])
    recorded = snap.get("backends") or {}
    if backends or recorded:
        lines.append("# HELP daari_backend_up 1 if the local backend last health-check succeeded.")
        lines.append("# TYPE daari_backend_up gauge")
        lines.append("# HELP daari_backend_outstanding In-flight requests on this backend.")
        lines.append("# TYPE daari_backend_outstanding gauge")
        lines.append("# HELP daari_backend_requests_total Requests served by this backend.")
        lines.append("# TYPE daari_backend_requests_total counter")
        seen: set[str] = set()
        for entry in backends:
            backend_id = str(entry.get("id") or "unknown")
            seen.add(backend_id)
            lines.append(
                f"daari_backend_up{_labels(backend=backend_id)} "
                f"{1 if entry.get('healthy') else 0}"
            )
            lines.append(
                f"daari_backend_outstanding{_labels(backend=backend_id)} "
                f"{int(entry.get('outstanding') or 0)}"
            )
            count = int(entry.get("requests") or recorded.get(backend_id) or 0)
            lines.append(f"daari_backend_requests_total{_labels(backend=backend_id)} {count}")
        for backend_id, count in recorded.items():
            if backend_id in seen:
                continue
            lines.append(f"daari_backend_requests_total{_labels(backend=backend_id)} {int(count)}")

    alerts = snap.get("budget_alerts") or {}
    if alerts:
        lines.append(
            "# HELP daari_budget_alerts_total Budget threshold crossings notified, by scope and threshold."
        )
        lines.append("# TYPE daari_budget_alerts_total counter")
        for key, count in alerts.items():
            scope, _, threshold = str(key).partition(":")
            lines.append(
                f"daari_budget_alerts_total{_labels(scope=scope, threshold=threshold)} {int(count)}"
            )

    return "\n".join(lines) + "\n"
