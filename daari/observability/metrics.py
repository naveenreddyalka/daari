from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# Prometheus histogram upper bounds (ms). Keep sorted; +Inf is implicit.
LATENCY_BUCKETS_MS: tuple[float, ...] = (5, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)
# TTFT tends to be shorter than full request latency; reuse the same bounds.
TTFT_BUCKETS_MS: tuple[float, ...] = LATENCY_BUCKETS_MS
# Decision-classifier hop latency (#1452); same bounds as request latency.
DECISION_CLASSIFIER_LATENCY_BUCKETS_MS: tuple[float, ...] = LATENCY_BUCKETS_MS

DECISION_CLASSIFIER_OUTCOMES = frozenset(
    {"success", "heuristic_fallback", "error", "skipped"}
)

# Bounded TTL classes for cache-write token counters (#1872).
CACHE_WRITE_TTL_LABELS = frozenset({"30m", "12h", "1h", "unset"})


def cache_write_ttl_label(ttl: str | None) -> str:
    """Map request cache TTL to a low-cardinality Prometheus label (#1872)."""
    label = (ttl or "").strip().lower()
    if label in ("30m", "12h", "1h"):
        return label
    return "unset"

# Prometheus modality label values (#1106).
MODALITIES = frozenset(
    {
        "chat",
        "embed",
        "tts",
        "asr",
        "images",
        "moderations",
        "rerank",
        "systemone",
        "decisions",
        "ocr",
        "mcp",
    }
)

# GenAI semantic-convention operation.name per modality.
GENAI_OPERATION_NAMES: dict[str, str] = {
    "chat": "chat",
    "embed": "embeddings",
    "tts": "text_to_speech",
    "asr": "transcription",
    "images": "image_generation",
    "moderations": "moderation",
    "rerank": "rerank",
    "systemone": "systemone",
    "decisions": "decisions",
    "ocr": "ocr",
    "mcp": "mcp",
}


def cache_invalidate_scope(
    *,
    model: str | None = None,
    entry_hash: str | None = None,
    team_id: str | None = None,
    key_id: str | None = None,
    speed: str | None = None,
) -> str:
    """Bounded scope label for admin cache invalidate metrics (#1639)."""
    if entry_hash:
        return "hash"
    if model:
        return "model"
    if team_id:
        return "team"
    if key_id:
        return "key"
    if speed:
        return "speed"
    return "all"


def infer_modality(tier: str, modality: str | None = None) -> str:
    """Map a metrics tier (or explicit tag) to a stable modality label."""
    if modality and modality in MODALITIES:
        return modality
    t = (tier or "").strip().lower()
    if t == "embed":
        return "embed"
    if t == "tts":
        return "tts"
    if t.startswith("asr"):
        return "asr"
    if t == "images":
        return "images"
    if t == "moderations":
        return "moderations"
    if t == "rerank":
        return "rerank"
    if t == "systemone":
        return "systemone"
    if t == "decisions":
        return "decisions"
    if t == "ocr":
        return "ocr"
    if t == "mcp":
        return "mcp"
    return "chat"


def genai_operation_name(modality: str | None = None, *, tier: str = "") -> str:
    return GENAI_OPERATION_NAMES.get(infer_modality(tier, modality), "chat")


def error_status_label(status: int | str | None = None) -> str:
    """Bounded HTTP status label for ``daari_errors_total`` (#1661).

    Unlabeled / invalid call sites bucket as ``"0"`` (unknown).
    """
    if status is None or status == "":
        return "0"
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "0"
    if code < 100 or code > 599:
        return "0"
    return str(code)


def histogram_percentile_ms(
    buckets: dict[float | str, int],
    *,
    count: int,
    percentile: float,
) -> float | None:
    """Approximate a percentile from exclusive histogram buckets (#529).

    ``buckets`` maps upper bound → count in that exclusive bucket (same shape
    as ``TtftStats.buckets``). Returns the bucket upper bound covering the
    target rank, or None when there are no samples.
    """
    if count <= 0:
        return None
    mark = max(0.0, min(1.0, float(percentile)))
    # Ceiling of mark * count without importing math.
    target = int(mark * count)
    if target < mark * count:
        target += 1
    target = max(1, target)
    cumulative = 0
    for bound in TTFT_BUCKETS_MS:
        cumulative += int(buckets.get(bound, 0))
        if cumulative >= target:
            return float(bound)
    if int(buckets.get("+Inf", 0)) > 0:
        return float("inf")
    return float(TTFT_BUCKETS_MS[-1]) if cumulative else None


@dataclass
class TierStats:
    count: int = 0
    cache_hits: int = 0
    total_latency_ms: int = 0
    latency_buckets: dict[float | str, int] = field(default_factory=dict)

    @property
    def avg_latency_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_latency_ms / self.count

    def observe_latency(self, latency_ms: int) -> None:
        for bound in LATENCY_BUCKETS_MS:
            if latency_ms <= bound:
                self.latency_buckets[bound] = self.latency_buckets.get(bound, 0) + 1
                return
        self.latency_buckets["+Inf"] = self.latency_buckets.get("+Inf", 0) + 1


@dataclass
class TtftStats:
    """Stream time-to-first-token histogram for one tier (#508)."""

    count: int = 0
    total_ttft_ms: int = 0
    buckets: dict[float | str, int] = field(default_factory=dict)

    def observe(self, ttft_ms: int) -> None:
        self.count += 1
        self.total_ttft_ms += max(0, int(ttft_ms))
        for bound in TTFT_BUCKETS_MS:
            if ttft_ms <= bound:
                self.buckets[bound] = self.buckets.get(bound, 0) + 1
                return
        self.buckets["+Inf"] = self.buckets.get("+Inf", 0) + 1


@dataclass
class Metrics:
    tiers: dict[str, TierStats] = field(default_factory=dict)
    ttft: dict[str, TtftStats] = field(default_factory=dict)
    # (modality, tier) → request count for additive modality-labeled series (#1106).
    modality_requests: dict[tuple[str, str], int] = field(default_factory=dict)
    # (modality, tier, direction) → token count; direction is input|output.
    tokens: dict[tuple[str, str, str], int] = field(default_factory=dict)
    errors: int = 0
    # status label → count; "0" = unlabeled/unknown (#1661).
    errors_by_status: dict[str, int] = field(default_factory=dict)
    escalations: int = 0
    guardrails: dict[str, int] = field(default_factory=dict)
    boundaries: dict[str, int] = field(default_factory=dict)
    cache_false_hits_avoided: int = 0
    upstream_retries: int = 0
    backends: dict[str, int] = field(default_factory=dict)
    tier_shadow: dict[str, int] = field(default_factory=dict)
    budget_alerts: dict[str, int] = field(default_factory=dict)
    responses_webhooks: dict[str, int] = field(default_factory=dict)
    org_enforcement_webhooks: dict[str, int] = field(default_factory=dict)
    soft_warnings: dict[str, int] = field(default_factory=dict)
    # requested:served → count when Phonon coerces response_format (#1961).
    tts_phonon_format_coerced: dict[str, int] = field(default_factory=dict)
    rejects: dict[str, int] = field(default_factory=dict)
    ttft_preferences: dict[str, int] = field(default_factory=dict)
    mcp_tool_calls: dict[str, int] = field(default_factory=dict)
    mcp_tasks: dict[str, int] = field(default_factory=dict)
    # server:outcome:circuit → count for MCP egress resilience (#1203).
    mcp_egress: dict[str, int] = field(default_factory=dict)
    # event (open|trip|reject) → count for systemone upstream breaker (#1801).
    systemone_breaker: dict[str, int] = field(default_factory=dict)
    # family:event → count for fleet-wide breaker trips (#1932).
    breaker_events: dict[str, int] = field(default_factory=dict)
    cancelled: dict[str, int] = field(default_factory=dict)
    deadline_exhausted: int = 0
    compact_to_fit_applied: int = 0
    compact_to_fit_tokens_dropped: int = 0
    mcp_grant_denied: int = 0
    # outcome → count for optional systemone decision classifier (#1452).
    decision_classifier: dict[str, int] = field(default_factory=dict)
    decision_classifier_latency: TtftStats = field(default_factory=TtftStats)
    # scope:result → count for admin cache invalidate (#1639).
    cache_invalidate: dict[str, int] = field(default_factory=dict)
    # layer (l0|l1) → entries removed across invalidate calls (#1639).
    cache_invalidate_entries_removed: dict[str, int] = field(default_factory=dict)
    # Gzip JSON middleware outcomes (#1830): "compressed" or "skipped:<reason>".
    gzip: dict[str, int] = field(default_factory=dict)
    gzip_bytes_before: int = 0
    gzip_bytes_after: int = 0
    # Cache-write tokens by TTL class (30m|12h|1h|unset) (#1872).
    cache_write_tokens: dict[str, int] = field(default_factory=dict)
    # Optional full-fleet inventory provider (set by AppContext) (#1932).
    breaker_inventory_fn: Callable[[], list[dict[str, Any]]] | None = field(
        default=None, repr=False
    )
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(
        self,
        tier: str,
        *,
        cache_hit: bool = False,
        latency_ms: int = 0,
        backend_id: str | None = None,
        modality: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        mod = infer_modality(tier, modality)
        with self._lock:
            stats = self.tiers.setdefault(tier, TierStats())
            stats.count += 1
            if cache_hit:
                stats.cache_hits += 1
            stats.total_latency_ms += latency_ms
            if latency_ms > 0:
                stats.observe_latency(latency_ms)
            if backend_id:
                self.backends[backend_id] = self.backends.get(backend_id, 0) + 1
            key = (mod, tier)
            self.modality_requests[key] = self.modality_requests.get(key, 0) + 1
            if input_tokens:
                tok_key = (mod, tier, "input")
                self.tokens[tok_key] = self.tokens.get(tok_key, 0) + max(0, int(input_tokens))
            if output_tokens:
                tok_key = (mod, tier, "output")
                self.tokens[tok_key] = self.tokens.get(tok_key, 0) + max(0, int(output_tokens))

    def record_ttft(self, tier: str, *, ttft_ms: int) -> None:
        """Record stream time-to-first-token. Non-stream requests omit TTFT (#508)."""
        with self._lock:
            self.ttft.setdefault(tier, TtftStats()).observe(ttft_ms)

    def record_error(self, status: int | str | None = None) -> None:
        """Count a gateway/router error; optional HTTP status for Prom labels (#1661)."""
        label = error_status_label(status)
        with self._lock:
            self.errors += 1
            self.errors_by_status[label] = self.errors_by_status.get(label, 0) + 1

    def record_escalation(self) -> None:
        with self._lock:
            self.escalations += 1

    def record_guardrail(self, action: str, *, kind: str = "deny") -> None:
        """Count a guardrail trip keyed as ``action:kind`` for Prometheus (#1610)."""
        label_kind = (kind or "deny").strip() or "deny"
        key = f"{action}:{label_kind}"
        with self._lock:
            self.guardrails[key] = self.guardrails.get(key, 0) + 1

    def record_boundary(self, label: str, stage: str) -> None:
        key = f"{stage}:{label}"
        with self._lock:
            self.boundaries[key] = self.boundaries.get(key, 0) + 1

    def record_false_hit_avoided(self) -> None:
        """An L1 candidate that cleared cosine but failed verification (#168)."""
        with self._lock:
            self.cache_false_hits_avoided += 1

    def record_upstream_retry(self) -> None:
        """A transient upstream failure that was retried rather than surfaced (#159).

        A rising count means backoff is absorbing instability the client never
        saw; a flat count with rising errors means failures are not retryable.
        """
        with self._lock:
            self.upstream_retries += 1

    def record_tier_shadow(self, *, agreed: bool) -> None:
        """A sampled local-tier answer was replayed at a comparison tier (#318)."""
        key = "agree" if agreed else "disagree"
        with self._lock:
            self.tier_shadow[key] = self.tier_shadow.get(key, 0) + 1

    def record_budget_alert(self, *, scope: str, threshold: float) -> None:
        key = f"{scope}:{threshold:g}"
        with self._lock:
            self.budget_alerts[key] = self.budget_alerts.get(key, 0) + 1

    def record_responses_webhook(self, result: str) -> None:
        """Responses completion webhook delivery outcome (#1913)."""
        label = (result or "").strip().lower() or "error"
        with self._lock:
            self.responses_webhooks[label] = self.responses_webhooks.get(label, 0) + 1

    def record_org_enforcement_webhook(self, result: str) -> None:
        """Anthropic org enforcement webhook ingest outcome (#1914)."""
        label = (result or "").strip().lower() or "error"
        with self._lock:
            self.org_enforcement_webhooks[label] = (
                self.org_enforcement_webhooks.get(label, 0) + 1
            )

    def record_soft_warning(self, kind: str) -> None:
        """Soft band before hard 402/429 (request_quota or rate_limit, #526)."""
        with self._lock:
            self.soft_warnings[kind] = self.soft_warnings.get(kind, 0) + 1

    def record_tts_phonon_format_coerced(self, *, requested: str, served: str) -> None:
        """Phonon rewrote an unsupported OpenAI TTS response_format (#1961)."""
        key = f"{requested}:{served}"
        with self._lock:
            self.tts_phonon_format_coerced[key] = (
                self.tts_phonon_format_coerced.get(key, 0) + 1
            )

    def record_reject(self, kind: str) -> None:
        """Hard 402/429/410 deny (budget, request_quota, rate_limit, body_too_large, retired)."""
        with self._lock:
            self.rejects[kind] = self.rejects.get(kind, 0) + 1

    def record_ttft_preference(self, *, from_tier: str, to_tier: str) -> None:
        """TTFT-aware routing rewrote the heuristic pick (#539)."""
        key = f"{from_tier}:{to_tier}"
        with self._lock:
            self.ttft_preferences[key] = self.ttft_preferences.get(key, 0) + 1

    def record_mcp_tool_call(self, *, tool: str, outcome: str) -> None:
        """MCP ingress tools/call outcome (ok, deny, error, guardrail) (#603)."""
        key = f"{tool}:{outcome}"
        with self._lock:
            self.mcp_tool_calls[key] = self.mcp_tool_calls.get(key, 0) + 1

    def record_mcp_task(self, *, outcome: str) -> None:
        """MCP task create/poll/cancel/complete/fail outcomes (#1632)."""
        label = (outcome or "").strip().lower() or "error"
        with self._lock:
            self.mcp_tasks[label] = self.mcp_tasks.get(label, 0) + 1

    def record_mcp_egress(self, *, server: str, outcome: str, circuit: str = "closed") -> None:
        """MCP egress call outcome with circuit-breaker state (#1203)."""
        key = f"{server}:{outcome}:{circuit}"
        with self._lock:
            self.mcp_egress[key] = self.mcp_egress.get(key, 0) + 1

    def record_systemone_breaker(self, *, event: str) -> None:
        """Systemone upstream breaker trip / open / reject (#1801)."""
        label = (event or "").strip().lower() or "trip"
        with self._lock:
            self.systemone_breaker[label] = self.systemone_breaker.get(label, 0) + 1
            key = f"systemone:{label}"
            self.breaker_events[key] = self.breaker_events.get(key, 0) + 1

    def record_breaker(self, *, family: str, event: str) -> None:
        """Fleet breaker event counter by family (#1932)."""
        fam = (family or "").strip().lower() or "unknown"
        label = (event or "").strip().lower() or "trip"
        key = f"{fam}:{label}"
        with self._lock:
            self.breaker_events[key] = self.breaker_events.get(key, 0) + 1

    def _systemone_breaker_state(self) -> list[dict[str, Any]]:
        """Live per-upstream open/closed (+ rejects) for exporters (#1822)."""
        try:
            from daari.gateway.systemone import breaker_snapshot

            return list(breaker_snapshot())
        except Exception:
            return []

    def _breaker_state(self) -> list[dict[str, Any]]:
        """Fleet inventory for ``daari_breaker_state`` (#1932)."""
        try:
            if self.breaker_inventory_fn is not None:
                return list(self.breaker_inventory_fn())
            from daari.router.breaker_inventory import collect_breaker_inventory

            return collect_breaker_inventory()
        except Exception:
            return []

    def record_cancelled(self, phase: str) -> None:
        """Client abandoned the request before upstream work finished (#769)."""
        with self._lock:
            self.cancelled[phase] = self.cancelled.get(phase, 0) + 1

    def record_deadline_exhausted(self) -> None:
        """A request-scoped deadline ran out before a tier could finish (#771)."""
        with self._lock:
            self.deadline_exhausted += 1

    def record_compact_to_fit_applied(self, *, tokens_dropped: int = 0) -> None:
        """History was actually trimmed before an L6 hop (#1351, #1392)."""
        with self._lock:
            self.compact_to_fit_applied += 1
            self.compact_to_fit_tokens_dropped += max(0, int(tokens_dropped))

    def record_mcp_grant_denied(self) -> None:
        """Fail-closed MCP grant missing on initialize / list / call (#1390)."""
        with self._lock:
            self.mcp_grant_denied += 1

    def record_cache_invalidate(
        self,
        *,
        scope: str,
        result: str = "ok",
        l0_removed: int = 0,
        l1_removed: int = 0,
    ) -> None:
        """Admin cache invalidate op; labels stay bounded (no per-hash) (#1639)."""
        scope_label = (scope or "all").strip().lower() or "all"
        if scope_label not in ("model", "hash", "team", "key", "speed", "all"):
            scope_label = "all"
        result_label = (result or "ok").strip().lower() or "ok"
        if result_label not in ("ok", "error"):
            result_label = "error"
        key = f"{scope_label}:{result_label}"
        with self._lock:
            self.cache_invalidate[key] = self.cache_invalidate.get(key, 0) + 1
            if l0_removed:
                self.cache_invalidate_entries_removed["l0"] = (
                    self.cache_invalidate_entries_removed.get("l0", 0) + max(0, int(l0_removed))
                )
            if l1_removed:
                self.cache_invalidate_entries_removed["l1"] = (
                    self.cache_invalidate_entries_removed.get("l1", 0) + max(0, int(l1_removed))
                )

    def record_decision_classifier(self, *, outcome: str, latency_ms: int = 0) -> None:
        """Optional /v1/systemone difficulty hop outcome + latency (#1452)."""
        label = (outcome or "").strip().lower() or "error"
        if label not in DECISION_CLASSIFIER_OUTCOMES:
            label = "error"
        with self._lock:
            self.decision_classifier[label] = self.decision_classifier.get(label, 0) + 1
            # Skipped bypasses the hop — do not invent latency samples.
            if label != "skipped" and latency_ms >= 0:
                self.decision_classifier_latency.observe(max(0, int(latency_ms)))

    def record_gzip(
        self,
        *,
        result: str,
        reason: str | None = None,
        bytes_before: int = 0,
        bytes_after: int = 0,
    ) -> None:
        """Buffered JSON gzip middleware outcome; labels stay bounded (#1830)."""
        result_label = (result or "").strip().lower() or "skipped"
        if result_label not in ("compressed", "skipped"):
            result_label = "skipped"
        reason_label = (reason or "").strip().lower() or ""
        if result_label == "skipped":
            if reason_label not in ("below_min", "not_json", "already_encoded", "streaming"):
                reason_label = "below_min"
            key = f"skipped:{reason_label}"
        else:
            key = "compressed"
        with self._lock:
            self.gzip[key] = self.gzip.get(key, 0) + 1
            if result_label == "compressed":
                self.gzip_bytes_before += max(0, int(bytes_before))
                self.gzip_bytes_after += max(0, int(bytes_after))

    def record_cache_write(self, *, tokens: int, ttl: str | None = None) -> None:
        """Accumulate provider cache-write tokens by TTL class (#1872)."""
        amount = max(0, int(tokens))
        if amount == 0:
            return
        label = cache_write_ttl_label(ttl)
        with self._lock:
            self.cache_write_tokens[label] = self.cache_write_tokens.get(label, 0) + amount

    def snapshot(self, *, include_histograms: bool = False) -> dict[str, Any]:
        """Tier map for /v1/daari/stats. With include_histograms=True also
        returns {"tiers", "errors", "escalations", "guardrails"} for exporters."""
        with self._lock:
            tiers: dict[str, dict[str, Any]] = {}
            for tier, stats in sorted(self.tiers.items()):
                entry: dict[str, Any] = {
                    "count": stats.count,
                    "cache_hits": stats.cache_hits,
                    "avg_latency_ms": round(stats.avg_latency_ms, 1),
                }
                if include_histograms:
                    entry["total_latency_ms"] = stats.total_latency_ms
                    entry["latency_buckets"] = dict(stats.latency_buckets)
                tiers[tier] = entry
            if not include_histograms:
                return tiers
            ttft: dict[str, dict[str, Any]] = {}
            for tier, stats in sorted(self.ttft.items()):
                ttft[tier] = {
                    "count": stats.count,
                    "total_ttft_ms": stats.total_ttft_ms,
                    "buckets": dict(stats.buckets),
                }
            return {
                "tiers": tiers,
                "ttft": ttft,
                "errors": self.errors,
                "errors_by_status": dict(self.errors_by_status),
                "escalations": self.escalations,
                "guardrails": dict(self.guardrails),
                "boundaries": dict(self.boundaries),
                "cache_false_hits_avoided": self.cache_false_hits_avoided,
                "upstream_retries": self.upstream_retries,
                "backends": dict(self.backends),
                "tier_shadow": dict(self.tier_shadow),
                "budget_alerts": dict(self.budget_alerts),
                "responses_webhooks": dict(self.responses_webhooks),
                "org_enforcement_webhooks": dict(self.org_enforcement_webhooks),
                "soft_warnings": dict(self.soft_warnings),
                "tts_phonon_format_coerced": dict(self.tts_phonon_format_coerced),
                "rejects": dict(self.rejects),
                "ttft_preferences": dict(self.ttft_preferences),
                "mcp_tool_calls": dict(self.mcp_tool_calls),
                "mcp_tasks": dict(self.mcp_tasks),
                "mcp_egress": dict(self.mcp_egress),
                "systemone_breaker": dict(self.systemone_breaker),
                "systemone_breaker_state": self._systemone_breaker_state(),
                "breaker_events": dict(self.breaker_events),
                "breaker_state": self._breaker_state(),
                "cancelled": dict(self.cancelled),
                "deadline_exhausted": self.deadline_exhausted,
                "compact_to_fit_applied": self.compact_to_fit_applied,
                "compact_to_fit_tokens_dropped": self.compact_to_fit_tokens_dropped,
                "mcp_grant_denied": self.mcp_grant_denied,
                "cache_invalidate": dict(self.cache_invalidate),
                "cache_invalidate_entries_removed": dict(self.cache_invalidate_entries_removed),
                "gzip": dict(self.gzip),
                "gzip_bytes_before": self.gzip_bytes_before,
                "gzip_bytes_after": self.gzip_bytes_after,
                "cache_write_tokens": dict(self.cache_write_tokens),
                "decision_classifier": dict(self.decision_classifier),
                "decision_classifier_latency": {
                    "count": self.decision_classifier_latency.count,
                    "total_ttft_ms": self.decision_classifier_latency.total_ttft_ms,
                    "buckets": dict(self.decision_classifier_latency.buckets),
                },
                "modality_requests": {
                    f"{mod}:{tier}": count
                    for (mod, tier), count in sorted(self.modality_requests.items())
                },
                "tokens": {
                    f"{mod}:{tier}:{direction}": count
                    for (mod, tier, direction), count in sorted(self.tokens.items())
                },
            }
