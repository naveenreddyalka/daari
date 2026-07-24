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


def propose_routing_defaults(
    stats: dict[str, Any],
    *,
    out_dir: Path | None = None,
) -> Path:
    """Build a proposed defaults snippet from aggregate stats.

    Expected stats shape (flexible):
      {
        "by_category": {"code": {"accept_rate": 0.9, "n": 120}, ...},
        "suggested_confidence_threshold": 0.65,  # optional override
        "prefer": "balanced"
      }
    """
    root = out_dir or (Path.home() / ".daari" / "proposals")
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"routing-defaults-{stamp}.yaml"

    by_category = stats.get("by_category") or stats.get("categories") or {}
    confidence = stats.get("suggested_confidence_threshold")
    if confidence is None:
        # Heuristic: if overall accept rate is high, lower threshold slightly.
        rates = [
            float(v.get("accept_rate", 0))
            for v in by_category.values()
            if isinstance(v, dict) and v.get("n", 0) >= 20
        ]
        confidence = 0.65 if rates and sum(rates) / len(rates) >= 0.85 else 0.7

    category_policies: dict[str, Any] = {}
    for name, row in by_category.items():
        if not isinstance(row, dict):
            continue
        n = int(row.get("n") or row.get("samples") or 0)
        if n < 20:
            continue
        accept = float(row.get("accept_rate") or 0)
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
