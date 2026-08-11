"""D4 defaults pipeline tracer — propose routing defaults from local stats.

Does not upload anything. Reads feedback/export-style aggregates (or a JSON
file from `daari learn export-stats`) and writes a reviewable YAML proposal
under `~/.daari/proposals/`. Human / next-month review decides whether to
promote into package defaults.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


MIN_SAMPLES = 20


def _flatten_category(row: dict[str, Any]) -> tuple[float, int] | None:
    """Return (accept_rate, n) for one category row.

    Accepts both shapes: the flat `{"accept_rate": .., "n": ..}` summary and the
    real `build_collective_stats` payload, which nests per tier and reports raw
    `outcomes`/`accepts`/`rejects` counts with no rate at all.
    """
    if "accept_rate" in row or "n" in row or "samples" in row:
        n = int(row.get("n") or row.get("samples") or 0)
        return float(row.get("accept_rate") or 0.0), n

    accepts = 0
    rejects = 0
    outcomes = 0
    for tier_row in row.values():
        if not isinstance(tier_row, dict):
            continue
        accepts += int(tier_row.get("accepts") or 0)
        rejects += int(tier_row.get("rejects") or 0)
        outcomes += int(tier_row.get("outcomes") or 0)
    if not outcomes:
        return None
    judged = accepts + rejects
    # No explicit accept/reject signal means no evidence about quality, even
    # though the category has traffic.
    if not judged:
        return None
    return accepts / judged, outcomes


def propose_routing_defaults(
    stats: dict[str, Any],
    *,
    out_dir: Path | None = None,
) -> Path:
    """Build a proposed defaults snippet from aggregate stats.

    Accepts either a flat summary or a `daari learn export-stats` payload:
      {"by_category": {"code": {"accept_rate": 0.9, "n": 120}}}
      {"categories": {"code": {"L3": {"outcomes": 60, "accepts": 57, ...}}}}
    Optional overrides: `suggested_confidence_threshold`, `prefer`.
    """
    root = out_dir or (Path.home() / ".daari" / "proposals")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"routing-defaults-{stamp}.yaml"

    by_category = stats.get("by_category") or stats.get("categories") or {}
    evidence: dict[str, tuple[float, int]] = {}
    for name, row in by_category.items():
        if not isinstance(row, dict):
            continue
        flattened = _flatten_category(row)
        if flattened is not None:
            evidence[name] = flattened

    confidence = stats.get("suggested_confidence_threshold")
    if confidence is None:
        # Heuristic: if overall accept rate is high, lower threshold slightly.
        rates = [rate for rate, n in evidence.values() if n >= MIN_SAMPLES]
        confidence = 0.65 if rates and sum(rates) / len(rates) >= 0.85 else 0.7

    category_policies: dict[str, Any] = {}
    for name, (accept, n) in evidence.items():
        if n < MIN_SAMPLES:
            continue
        # High-accept categories can stay on cheaper tiers; low-accept bump.
        if accept >= 0.9:
            category_policies[name] = {"tier": "L3"}
        elif accept < 0.6:
            category_policies[name] = {"tier": "L5"}

    proposal = {
        "generated_at": stamp,
        "source": "daari learn propose-defaults (D4 tracer)",
        "review": "PROPOSAL — do not ship without human review",
        "routing": {
            "prefer": stats.get("prefer") or "balanced",
            "confidence_threshold": float(confidence),
            "category_policies": category_policies,
        },
        "notes": (
            "Promote into daari package defaults only after multi-user D3 "
            "aggregates exist and a release owner signs off."
        ),
    }
    path.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8")
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    return path
