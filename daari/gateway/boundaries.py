"""Product-domain boundary gate (Roadmap F6).

Local-first ladder:
  B0 — topic / example overlap, optional L1-embedder cosine
  B1 — optional local judge (injected callable)
  B2 — N-vote local quorum on still-ambiguous cases
  B3 — optional frontier judge, hard-capped by daily USD budget

Master switch: settings.boundaries.enabled (default False).
Mode: block (refuse) | warn (annotate + continue) | off.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from daari.config.settings import BoundariesSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.trace import add_step

_FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "boundaries" / "fixtures.jsonl"
_B3_CALL_USD = 0.01

Label = Literal["in", "out", "ambiguous"]

JudgeFn = Callable[[str, BoundariesSettings], Awaitable["BoundaryDecision"]]


@dataclass
class BoundaryDecision:
    label: Label
    confidence: float
    stage: str
    reason: str = ""

    def as_meta(self, *, mode: str) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "stage": self.stage,
            "reason": self.reason,
            "mode": mode,
        }


def _user_text(request: InternalRequest) -> str:
    parts = [
        m.content
        for m in request.messages
        if m.role == "user" and isinstance(m.content, str) and m.content.strip()
    ]
    return "\n".join(parts).strip()


def _topic_hit(text: str, topics: list[str]) -> tuple[str | None, float]:
    lower = text.lower()
    best: tuple[str | None, float] = (None, 0.0)
    for topic in topics:
        t = (topic or "").strip().lower()
        if not t:
            continue
        if t in lower:
            # Longer topic match → slightly higher confidence
            conf = min(0.99, 0.75 + 0.05 * min(len(t.split()), 4))
            if conf > best[1]:
                best = (topic, conf)
            continue
        # Token overlap for multi-word topics
        tokens = [w for w in re.split(r"\W+", t) if len(w) > 2]
        if len(tokens) >= 2:
            hits = sum(1 for w in tokens if w in lower)
            ratio = hits / len(tokens)
            if ratio >= 0.75:
                conf = 0.7 + 0.2 * ratio
                if conf > best[1]:
                    best = (topic, conf)
    return best


def _example_overlap(text: str, examples: list[str]) -> float:
    if not examples:
        return 0.0
    words = {w for w in re.split(r"\W+", text.lower()) if len(w) > 2}
    if not words:
        return 0.0
    best = 0.0
    for ex in examples:
        ex_words = {w for w in re.split(r"\W+", ex.lower()) if len(w) > 2}
        if not ex_words:
            continue
        overlap = len(words & ex_words) / len(ex_words)
        if overlap > best:
            best = overlap
    return best


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(x * y for x, y in zip(a[:n], b[:n]))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(y * y for y in b[:n]))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (na * nb)


def majority_vote(
    votes: list[BoundaryDecision], *, quorum: int
) -> BoundaryDecision | None:
    counts = {"in": 0, "out": 0}
    for vote in votes:
        if vote.label in counts:
            counts[vote.label] += 1
    in_n, out_n = counts["in"], counts["out"]
    if in_n >= quorum and in_n > out_n:
        winner: Label = "in"
    elif out_n >= quorum and out_n > in_n:
        winner = "out"
    else:
        return None
    picked = next(v for v in votes if v.label == winner)
    return BoundaryDecision(
        winner, picked.confidence, "b2", f"quorum:{winner}:{counts[winner]}"
    )


def _shadow_local_vote(text: str, settings: BoundariesSettings) -> BoundaryDecision:
    """Second local signal when B1 is already default_local_judge."""
    deny_topic, deny_conf = _topic_hit(text, settings.deny_topics)
    allow_topic, allow_conf = _topic_hit(text, settings.allow_topics)
    out_ex = _example_overlap(text, settings.examples_out)
    in_ex = _example_overlap(text, settings.examples_in)
    out_score = max(deny_conf, out_ex)
    in_score = max(allow_conf, in_ex)
    if out_score >= 0.4 and out_score > in_score:
        return BoundaryDecision("out", out_score, "b2", f"shadow_deny:{deny_topic}")
    if in_score >= 0.4 and in_score >= out_score:
        return BoundaryDecision("in", in_score, "b2", f"shadow_allow:{allow_topic}")
    return BoundaryDecision("ambiguous", max(out_score, in_score), "b2", "shadow_uncertain")


def startup_warnings(settings: Any) -> list[str]:
    """Stages that cannot run should be loud at boot, not a silent no-op."""
    block = getattr(settings, "boundaries", None)
    if block is None or not getattr(block, "enabled", False):
        return []
    if not getattr(block, "stages_b3", False):
        return []
    frontier = getattr(settings, "frontier", None)
    frontier_on = bool(getattr(frontier, "enabled", False))
    key = None
    resolver = getattr(settings, "resolve_frontier_api_key", None)
    if callable(resolver):
        key = resolver()
    if frontier_on and key:
        return []
    return [
        "boundaries.stages_b3 is on but no frontier judge is configured",
    ]


def copy_runtime_hooks(dst: BoundaryEngine | None, src: BoundaryEngine | None) -> None:
    if dst is None or src is None:
        return
    dst.embedder = getattr(src, "embedder", None)
    dst.frontier_judge = getattr(src, "frontier_judge", None)


def score_boundary_fixtures(
    engine: BoundaryEngine, path: Path | None = None
) -> dict[str, int]:
    fixture_path = path or _FIXTURES
    false_refuse = 0
    false_allow = 0
    total = 0
    for line in fixture_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        gold = row["label"]
        request = InternalRequest(
            messages=[Message(role="user", content=row["text"])],
            model="daari",
        )
        # Fixtures are the lexical B0 CI gate; keep this sync.
        predicted = engine.classify_b0(request)
        total += 1
        if gold == "in" and predicted.label == "out":
            false_refuse += 1
        if gold == "out" and predicted.label == "in":
            false_allow += 1
    return {"total": total, "false_refuse": false_refuse, "false_allow": false_allow}


@dataclass
class BoundaryEngine:
    settings: BoundariesSettings
    judge: JudgeFn | None = None
    embedder: Any = None
    frontier_judge: JudgeFn | None = None
    _b3_spend: float = 0.0
    _b3_day: str = field(default="")

    @classmethod
    def from_settings(
        cls,
        settings: BoundariesSettings,
        *,
        judge: JudgeFn | None = None,
        embedder: Any = None,
        frontier_judge: JudgeFn | None = None,
    ) -> BoundaryEngine:
        return cls(
            settings=settings,
            judge=judge,
            embedder=embedder,
            frontier_judge=frontier_judge,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled) and self.settings.mode != "off"

    @property
    def mode(self) -> str:
        return self.settings.mode if self.settings.mode in ("warn", "block", "off") else "block"

    def classify_b0(self, request: InternalRequest) -> BoundaryDecision:
        text = _user_text(request)
        if not text:
            return BoundaryDecision("ambiguous", 0.0, "b0", "empty")

        deny_topic, deny_conf = _topic_hit(text, self.settings.deny_topics)
        allow_topic, allow_conf = _topic_hit(text, self.settings.allow_topics)
        out_ex = _example_overlap(text, self.settings.examples_out)
        in_ex = _example_overlap(text, self.settings.examples_in)

        out_score = max(deny_conf, out_ex * 0.9)
        in_score = max(allow_conf, in_ex * 0.9)

        thr_out = float(self.settings.clear_out_threshold)
        thr_in = float(self.settings.clear_in_threshold)

        if out_score >= thr_out and out_score > in_score:
            reason = f"deny:{deny_topic}" if deny_topic else f"example_out:{out_ex:.2f}"
            return BoundaryDecision("out", out_score, "b0", reason)
        if in_score >= thr_in and in_score >= out_score:
            reason = f"allow:{allow_topic}" if allow_topic else f"example_in:{in_ex:.2f}"
            return BoundaryDecision("in", in_score, "b0", reason)
        return BoundaryDecision(
            "ambiguous",
            max(out_score, in_score),
            "b0",
            f"in={in_score:.2f},out={out_score:.2f}",
        )

    async def _classify_b0_embed(self, request: InternalRequest) -> BoundaryDecision:
        text = _user_text(request)
        if not text or self.embedder is None:
            return BoundaryDecision("ambiguous", 0.0, "b0", "embed_unavailable")
        text_vec = await self.embedder.embed(text)
        if not text_vec:
            return BoundaryDecision("ambiguous", 0.0, "b0", "embed_empty")

        async def best_of(candidates: list[str]) -> tuple[str | None, float]:
            best: tuple[str | None, float] = (None, 0.0)
            for candidate in candidates:
                if not (candidate or "").strip():
                    continue
                vec = await self.embedder.embed(candidate)
                if not vec:
                    continue
                sim = _cosine(text_vec, vec)
                if sim > best[1]:
                    best = (candidate, sim)
            return best

        deny_topic, deny_sim = await best_of(self.settings.deny_topics + self.settings.examples_out)
        allow_topic, allow_sim = await best_of(self.settings.allow_topics + self.settings.examples_in)
        thr_out = float(self.settings.clear_out_threshold)
        thr_in = float(self.settings.clear_in_threshold)
        if deny_sim >= thr_out and deny_sim > allow_sim:
            return BoundaryDecision("out", deny_sim, "b0", f"embed_deny:{deny_topic}")
        if allow_sim >= thr_in and allow_sim >= deny_sim:
            return BoundaryDecision("in", allow_sim, "b0", f"embed_allow:{allow_topic}")
        return BoundaryDecision(
            "ambiguous",
            max(deny_sim, allow_sim),
            "b0",
            f"embed_in={allow_sim:.2f},out={deny_sim:.2f}",
        )

    def _trace(self, decision: BoundaryDecision) -> BoundaryDecision:
        add_step(
            "boundary_stage",
            stage=decision.stage,
            label=decision.label,
            confidence=decision.confidence,
            reason=decision.reason,
        )
        return decision

    def _b1_decisive(self, judged: BoundaryDecision) -> BoundaryDecision | None:
        thr_out = float(self.settings.clear_out_threshold)
        thr_in = float(self.settings.clear_in_threshold)
        if judged.label == "out" and judged.confidence >= thr_out:
            return judged
        if judged.label == "in" and judged.confidence >= thr_in:
            return judged
        return None

    def _b3_budget_ok(self) -> bool:
        today = date.today().isoformat()
        if self._b3_day != today:
            self._b3_day = today
            self._b3_spend = 0.0
        return self._b3_spend < float(self.settings.frontier_judge_daily_budget_usd)

    def _effective_settings(self, request: InternalRequest) -> BoundariesSettings:
        profile = getattr(getattr(request, "meta", None), "boundary_profile", None) or ""
        profiles = self.settings.profiles or {}
        if not profile or profile not in profiles:
            return self.settings
        overlay = profiles[profile]
        if not isinstance(overlay, dict):
            return self.settings
        merged = self.settings.model_dump()
        merged.update({k: v for k, v in overlay.items() if k != "profiles"})
        return BoundariesSettings.model_validate(merged)

    async def classify(self, request: InternalRequest) -> BoundaryDecision:
        original = self.settings
        self.settings = self._effective_settings(request)
        try:
            return await self._classify(request)
        finally:
            self.settings = original

    async def _classify(self, request: InternalRequest) -> BoundaryDecision:
        if not self.settings.stages_b0:
            decision = BoundaryDecision("ambiguous", 0.0, "b0", "b0_disabled")
        else:
            decision = self.classify_b0(request)
            if decision.label == "ambiguous" and self.embedder is not None:
                try:
                    embedded = await self._classify_b0_embed(request)
                    if embedded.label != "ambiguous":
                        decision = embedded
                except Exception:
                    pass
        self._trace(decision)
        if decision.label != "ambiguous":
            return decision

        votes: list[BoundaryDecision] = []
        text = _user_text(request)
        judged: BoundaryDecision | None = None
        if self.settings.stages_b1 and self.judge is not None:
            judged = await self.judge(text, self.settings)
            self._trace(judged)
            decisive = self._b1_decisive(judged)
            if decisive is not None:
                if not self.settings.stages_b2:
                    return decisive
                votes.append(decisive)
            elif not self.settings.stages_b2 and not self.settings.stages_b3:
                return BoundaryDecision(
                    "ambiguous",
                    judged.confidence,
                    judged.stage or "b1",
                    judged.reason or "judge_uncertain",
                )

        if self.settings.stages_b2:
            if self.judge is not default_local_judge:
                extra = await default_local_judge(text, self.settings)
            else:
                extra = _shadow_local_vote(text, self.settings)
            if extra.label in ("in", "out"):
                votes.append(extra)
            decided = majority_vote(votes, quorum=int(self.settings.quorum_votes))
            if decided is not None:
                return self._trace(decided)
            self._trace(
                BoundaryDecision(
                    "ambiguous",
                    max((v.confidence for v in votes), default=0.0),
                    "b2",
                    "quorum_unmet",
                )
            )

        if self.settings.stages_b3 and self.frontier_judge is not None and self._b3_budget_ok():
            self._b3_spend += _B3_CALL_USD
            frontier = await self.frontier_judge(text, self.settings)
            frontier.stage = "b3"
            return self._trace(frontier)

        if judged is not None:
            return BoundaryDecision(
                "ambiguous",
                judged.confidence,
                judged.stage or "b1",
                judged.reason or "judge_uncertain",
            )
        return decision


def _overlay_named_profile(
    block: BoundariesSettings, profile_name: str
) -> BoundariesSettings:
    """Merge `boundaries.profiles[name]` onto the base block (issue #171)."""
    name = (profile_name or "").strip()
    profiles = getattr(block, "profiles", None) or {}
    if not name or not isinstance(profiles, dict) or name not in profiles:
        return block
    overlay = profiles[name]
    if not isinstance(overlay, dict):
        return block
    merged = block.model_dump()
    merged.update({k: v for k, v in overlay.items() if k != "profiles"})
    merged["active_profile"] = name
    return BoundariesSettings.model_validate(merged)


def engine_from_settings(
    settings: Any,
    *,
    judge: JudgeFn | None = None,
    profile: str | None = None,
) -> BoundaryEngine | None:
    block = getattr(settings, "boundaries", None)
    if block is None:
        return None
    # Request header X-Daari-Boundary-Profile selects a named overlay (#171).
    requested = (profile or "").strip()
    if requested:
        block = _overlay_named_profile(block, requested)
        if not block.enabled:
            block = BoundariesSettings.model_validate(
                {**block.model_dump(), "enabled": True}
            )
    elif not getattr(block, "enabled", False):
        return None
    if getattr(block, "mode", "block") == "off":
        return None
    if not requested:
        active = (getattr(block, "active_profile", None) or "").strip()
        if active:
            block = _overlay_named_profile(block, active)
    return BoundaryEngine.from_settings(block, judge=judge)


def engine_for_request(
    base: BoundaryEngine | None,
    *,
    profile: str | None = None,
) -> BoundaryEngine | None:
    """Per-request profile overlay on an already-built engine (#171)."""
    name = (profile or "").strip()
    if not name:
        if base is not None and getattr(base, "enabled", False):
            return base
        return None
    if base is None:
        return None
    profiles = base.settings.profiles or {}
    if name not in profiles:
        if getattr(base, "enabled", False):
            return base
        return None
    overlaid = _overlay_named_profile(base.settings, name)
    if not overlaid.enabled:
        overlaid = BoundariesSettings.model_validate(
            {**overlaid.model_dump(), "enabled": True}
        )
    if overlaid.mode == "off":
        return None
    return BoundaryEngine.from_settings(overlaid, judge=base.judge)


def refused_response(
    request: InternalRequest, message: str, decision: BoundaryDecision, *, mode: str
) -> InternalResponse:
    return InternalResponse(
        content=message,
        model=request.model,
        daari_meta=DaariMeta(
            tier="boundary",
            executor="boundary",
            provider_id="boundary",
            latency_ms=0,
            warning="boundary_blocked" if mode == "block" else "boundary_warn",
            boundary=decision.as_meta(mode=mode),
            confidence=decision.confidence,
        ),
    )


async def default_local_judge(text: str, settings: BoundariesSettings) -> BoundaryDecision:
    """Heuristic fallback when no L3 judge is wired — prefer ambiguous over false refuse."""
    deny_topic, deny_conf = _topic_hit(text, settings.deny_topics)
    allow_topic, allow_conf = _topic_hit(text, settings.allow_topics)
    if deny_conf > allow_conf and deny_conf >= 0.6:
        return BoundaryDecision("out", deny_conf, "b1", f"deny:{deny_topic}")
    if allow_conf >= 0.6:
        return BoundaryDecision("in", allow_conf, "b1", f"allow:{allow_topic}")
    # Description keyword hints
    desc = (settings.product_description or "").lower()
    desc_words = {w for w in re.split(r"\W+", desc) if len(w) > 3}
    text_words = {w for w in re.split(r"\W+", text.lower()) if len(w) > 3}
    if desc_words and text_words:
        overlap = len(desc_words & text_words) / max(1, len(desc_words))
        if overlap >= 0.15:
            return BoundaryDecision("in", min(0.8, 0.5 + overlap), "b1", "desc_overlap")
    return BoundaryDecision("ambiguous", 0.4, "b1", "uncertain")
