"""In-flight budget reservation ledger (#2198).

Opt-in via ``budgets.reserve_in_flight``. At admission, estimated USD is held
against active windows so parallel bursts cannot overshoot settled spend.
Reservations are always released on completion, error, or stream abort.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from daari.auth.rate_limit import estimate_request_tokens
from daari.pricing import cost_usd, is_ollama_cloud_model, matching_model_key

LOCAL_TIERS = frozenset({"L0", "L1", "L2", "L3", "L4", "L5"})
DEFAULT_OUTPUT_TOKENS = 4096


@dataclass
class Reservation:
    reservation_id: str
    amount: float
    windows: tuple[tuple[str, str, str], ...] = ()


@dataclass
class BudgetReservationLedger:
    """Process-local reserved USD keyed by (scope, scope_id, duration)."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _reserved: dict[tuple[str, str, str], float] = field(default_factory=dict)
    _by_id: dict[str, Reservation] = field(default_factory=dict)

    def reserved(self, scope: str, scope_id: str, duration: str) -> float:
        with self._lock:
            return float(self._reserved.get((scope, scope_id, duration), 0.0))

    def try_reserve(
        self,
        *,
        windows: Iterable[tuple[str, str, str, float, float]],
        amount: float,
    ) -> Reservation | None:
        """Reserve ``amount`` against each window or return None if any would exceed.

        ``windows`` entries are ``(scope, scope_id, duration, settled_spend, limit)``.
        A zero/negative amount succeeds without holding quota (local tiers).
        """
        amt = max(0.0, float(amount))
        window_list = list(windows)
        keys = [(s, sid, dur) for s, sid, dur, _spend, _lim in window_list]
        with self._lock:
            if amt > 0:
                for scope, scope_id, duration, settled, limit in window_list:
                    held = float(self._reserved.get((scope, scope_id, duration), 0.0))
                    if float(settled) + held + amt > float(limit) + 1e-12:
                        return None
                for key in keys:
                    self._reserved[key] = float(self._reserved.get(key, 0.0)) + amt
            reservation_id = uuid.uuid4().hex
            reservation = Reservation(
                reservation_id=reservation_id,
                amount=amt,
                windows=tuple(keys),
            )
            self._by_id[reservation_id] = reservation
            return reservation

    def release(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        with self._lock:
            reservation = self._by_id.pop(reservation_id, None)
            if reservation is None:
                return
            amt = float(reservation.amount)
            if amt <= 0:
                return
            for key in reservation.windows:
                current = float(self._reserved.get(key, 0.0)) - amt
                if current <= 1e-12:
                    self._reserved.pop(key, None)
                else:
                    self._reserved[key] = current


def is_zero_cost_admission_model(
    model: str | None,
    settings: Any,
    *,
    tier_header: str | None = None,
) -> bool:
    """Local L1–L5 / configured local models reserve $0 (#2198)."""
    tier = (tier_header or "").strip().upper()
    if tier in LOCAL_TIERS:
        return True
    if tier == "L6":
        return False
    name = (model or "").strip()
    if not name or name == "daari":
        return False
    if is_ollama_cloud_model(name):
        return False
    models = getattr(settings, "models", None)
    if models is not None:
        for attr in ("l1", "l2", "l3", "l4", "l5"):
            configured = getattr(models, attr, None)
            if isinstance(configured, str) and configured.strip() == name:
                return True
    pricing = getattr(settings, "pricing", None)
    price_models = getattr(pricing, "models", None) if pricing is not None else None
    if matching_model_key(name, price_models or {}):
        return False
    # Unpriced non-cloud ids (typical Ollama locals) are zero-cost at admission.
    return True


def _output_tokens(payload: dict[str, Any] | None, default_output_tokens: int) -> int:
    if not payload:
        return max(1, int(default_output_tokens))
    for key in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return max(1, int(default_output_tokens))


def estimate_admission_cost_usd(
    payload: dict[str, Any] | None,
    *,
    model: str | None,
    pricing: Any,
    fallback_per_1k: float,
    default_output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> float:
    """Prompt tokens at input rate + max_tokens (or default) at output rate."""
    prompt = estimate_request_tokens(payload)
    output = _output_tokens(payload, default_output_tokens)
    return float(
        cost_usd(
            model,
            prompt,
            output,
            pricing,
            fallback_per_1k=float(fallback_per_1k),
        )
    )


def admission_reserve_amount(
    payload: dict[str, Any] | None,
    *,
    model: str | None,
    settings: Any,
    pricing: Any,
    fallback_per_1k: float,
    tier_header: str | None = None,
) -> float:
    if is_zero_cost_admission_model(model, settings, tier_header=tier_header):
        return 0.0
    bill_model = (model or "").strip() or "daari"
    if bill_model == "daari":
        frontier = getattr(settings, "frontier", None)
        bill_model = str(getattr(frontier, "model", None) or bill_model)
    budgets = getattr(settings, "budgets", None)
    default_out = int(
        getattr(budgets, "default_output_tokens", DEFAULT_OUTPUT_TOKENS) or DEFAULT_OUTPUT_TOKENS
    )
    return estimate_admission_cost_usd(
        payload,
        model=bill_model,
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
        default_output_tokens=default_out,
    )
