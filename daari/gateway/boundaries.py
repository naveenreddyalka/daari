"""Product-domain boundary gate (Roadmap F6).

Local-first ladder:
  B0 — topic / example overlap (no model)
  B1 — optional local L3 structured judge (injected callable)
  B2/B3 — reserved (quorum / frontier); wired later

Master switch: settings.boundaries.enabled (default False).
Mode: block (refuse) | warn (annotate + continue) | off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from daari.config.settings import BoundariesSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse

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


@dataclass
class BoundaryEngine:
    settings: BoundariesSettings
    judge: JudgeFn | None = None

    @classmethod
    def from_settings(
        cls, settings: BoundariesSettings, *, judge: JudgeFn | None = None
    ) -> BoundaryEngine:
        return cls(settings=settings, judge=judge)

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

    async def classify(self, request: InternalRequest) -> BoundaryDecision:
        if not self.settings.stages_b0:
            decision = BoundaryDecision("ambiguous", 0.0, "b0", "b0_disabled")
        else:
            decision = self.classify_b0(request)

        if decision.label != "ambiguous":
            return decision

        if not self.settings.stages_b1 or self.judge is None:
            return decision

        text = _user_text(request)
        judged = await self.judge(text, self.settings)
        thr_out = float(self.settings.clear_out_threshold)
        thr_in = float(self.settings.clear_in_threshold)
        if judged.label == "out" and judged.confidence >= thr_out:
            return judged
        if judged.label == "in" and judged.confidence >= thr_in:
            return judged
        return BoundaryDecision(
            "ambiguous",
            judged.confidence,
            judged.stage or "b1",
            judged.reason or "judge_uncertain",
        )


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
