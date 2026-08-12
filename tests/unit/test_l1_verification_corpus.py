"""Regression gate for L1 verification quality (#168).

The verifier trades cache hits for correctness, so both directions need a floor:
it must reject near-misses (the point) without rejecting paraphrases (which
would quietly turn the cache off). This runs the labeled corpus in
`evals/cache/verification.jsonl` in CI so a future tweak to the guards cannot
silently collapse either number.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from daari.cache.verify import LexicalVerifier

CORPUS = Path(__file__).resolve().parents[2] / "evals" / "cache" / "verification.jsonl"

# A paraphrase wrongly rejected costs a cache hit; a near-miss wrongly served is
# a wrong answer. The floors are asymmetric on purpose, and both are gates.
MIN_PARAPHRASE_RETENTION = 0.90
MIN_NEAR_MISS_REJECTION = 0.90
MAX_MEAN_LATENCY_MS = 0.5


def _load() -> list[dict]:
    with CORPUS.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="module")
def results() -> dict:
    verifier = LexicalVerifier()
    rows = _load()
    paraphrases = [row for row in rows if row["label"] == "paraphrase"]
    near_misses = [row for row in rows if row["label"] == "near_miss"]
    synonyms = [row for row in rows if row["label"] == "synonym_substitution"]
    assert paraphrases and near_misses, "corpus must cover both gated labels"

    started = time.perf_counter()
    retained = [
        row
        for row in paraphrases
        if verifier.verify(row["candidate"], row["stored"]).ok
    ]
    rejected = [
        row
        for row in near_misses
        if not verifier.verify(row["candidate"], row["stored"]).ok
    ]
    synonyms_retained = [
        row for row in synonyms if verifier.verify(row["candidate"], row["stored"]).ok
    ]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "paraphrases": paraphrases,
        "near_misses": near_misses,
        "synonyms": synonyms,
        "retained": retained,
        "rejected": rejected,
        "synonyms_retained": synonyms_retained,
        "mean_latency_ms": elapsed_ms / len(rows),
    }


def test_paraphrase_retention_meets_floor(results):
    """Rejecting paraphrases silently disables the cache — the worse failure."""
    retention = len(results["retained"]) / len(results["paraphrases"])
    missed = [
        row["id"]
        for row in results["paraphrases"]
        if row not in results["retained"]
    ]
    assert retention >= MIN_PARAPHRASE_RETENTION, (
        f"paraphrase retention {retention:.2%} below {MIN_PARAPHRASE_RETENTION:.0%}; "
        f"wrongly rejected: {missed}"
    )


def test_near_miss_rejection_meets_floor(results):
    rejection = len(results["rejected"]) / len(results["near_misses"])
    served = [
        row["id"] for row in results["near_misses"] if row not in results["rejected"]
    ]
    assert rejection >= MIN_NEAR_MISS_REJECTION, (
        f"near-miss rejection {rejection:.2%} below {MIN_NEAR_MISS_REJECTION:.0%}; "
        f"wrongly served: {served}"
    )


def test_verification_latency_is_a_small_fraction_of_a_hit(results):
    """A cache hit saves hundreds of ms; verification must not eat that."""
    assert results["mean_latency_ms"] < MAX_MEAN_LATENCY_MS, (
        f"mean verification latency {results['mean_latency_ms']:.3f}ms "
        f"exceeds {MAX_MEAN_LATENCY_MS}ms"
    )


def test_synonym_substitutions_are_a_known_limitation(results):
    """Not a gate — a documented cost, tracked so it stays visible.

    A lexical verifier cannot tell "fix" for "resolve" (harmless) from
    "staging" for "production" (not harmless): both are one-word substitutions.
    These lose a cache hit and get regenerated, which is the safe direction.
    `cache.l1.verify = "model"` is the path to recovering them.
    """
    retained = len(results["synonyms_retained"])
    total = len(results["synonyms"])
    assert retained <= total
    assert total >= 5, "keep tracking enough synonym cases for the rate to mean something"


def test_corpus_reports_its_rates(results, capsys):
    """Prints the rates so CI logs carry the numbers, not just pass/fail."""
    retention = len(results["retained"]) / len(results["paraphrases"])
    rejection = len(results["rejected"]) / len(results["near_misses"])
    synonym_rate = len(results["synonyms_retained"]) / len(results["synonyms"])
    with capsys.disabled():
        print(
            f"\nL1 verification: paraphrase retention {retention:.1%} "
            f"({len(results['retained'])}/{len(results['paraphrases'])}), "
            f"near-miss rejection {rejection:.1%} "
            f"({len(results['rejected'])}/{len(results['near_misses'])}), "
            f"synonym retention {synonym_rate:.1%} "
            f"({len(results['synonyms_retained'])}/{len(results['synonyms'])}, ungated), "
            f"{results['mean_latency_ms']:.3f}ms mean"
        )
