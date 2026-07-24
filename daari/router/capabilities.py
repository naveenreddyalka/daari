"""Model capability catalog + tier filtering (issue #113).

Capabilities are declared per model in config (`models.capabilities`) and
optionally probed. The router skips tiers whose model lacks a required
capability (e.g. tools → skip models without `tools`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from daari.gateway.internal import InternalRequest

KNOWN_CAPABILITIES = ("tools", "json", "vision", "long_context")


@dataclass
class CapabilityCatalog:
    # model name -> frozenset of capability strings
    models: dict[str, frozenset[str]] = field(default_factory=dict)
    # Default when a model has no entry: assume basic chat only.
    default: frozenset[str] = field(default_factory=lambda: frozenset())

    def for_model(self, model: str) -> frozenset[str]:
        return self.models.get(model, self.default)

    def supports(self, model: str, required: Iterable[str]) -> bool:
        caps = self.for_model(model)
        return all(cap in caps for cap in required)


def required_capabilities(request: InternalRequest) -> set[str]:
    """Infer capabilities the request needs from its shape."""
    needed: set[str] = set()
    if request.tools or request.has_tool_calls_in_history:
        needed.add("tools")
    for message in request.messages:
        content = message.content or ""
        # Lightweight vision hint: multimodal content markers in text form.
        if "data:image/" in content or "image_url" in content:
            needed.add("vision")
        if '"response_format"' in content or "json_object" in content.lower():
            needed.add("json")
    prompt_chars = sum(len(m.content or "") for m in request.messages)
    if prompt_chars > 24_000:  # ~6k tokens
        needed.add("long_context")
    return needed


def filter_tiers_by_capability(
    tiers: list[str],
    *,
    tier_models: dict[str, str],
    catalog: CapabilityCatalog,
    required: set[str],
) -> list[str]:
    """Drop tiers whose model lacks any required capability. Empty required → no-op."""
    if not required:
        return list(tiers)
    kept: list[str] = []
    for tier in tiers:
        model = tier_models.get(tier, "")
        if catalog.supports(model, required):
            kept.append(tier)
    return kept


def catalog_from_settings(settings: Any) -> CapabilityCatalog:
    raw = getattr(settings.models, "capabilities", None) or {}
    models: dict[str, frozenset[str]] = {}
    for name, caps in raw.items():
        if isinstance(caps, (list, tuple, set, frozenset)):
            models[str(name)] = frozenset(str(c) for c in caps)
    # Sensible defaults for the stock Ollama stack when config is empty.
    if not models:
        models = {
            settings.models.l3: frozenset({"tools"}),
            settings.models.l4: frozenset({"tools", "json", "long_context"}),
            settings.models.l5: frozenset({"tools", "json", "vision", "long_context"}),
        }
    return CapabilityCatalog(models=models)


def suggest_models_for_vram(total_ram_gb: float) -> dict[str, str]:
    """VRAM/RAM-aware stack advisor for `daari doctor --suggest-models`."""
    if total_ram_gb >= 64:
        return {
            "l3": "llama3.2:3b",
            "l4": "llama3.1:8b",
            "l5": "llama3.1:70b",
            "note": "64GB+: full L3/L4/L5 stack fits comfortably.",
        }
    if total_ram_gb >= 32:
        return {
            "l3": "llama3.2:3b",
            "l4": "llama3.1:8b",
            "l5": "qwen2.5:14b",
            "note": "32GB: prefer a 14B L5 over 70B.",
        }
    if total_ram_gb >= 16:
        return {
            "l3": "llama3.2:3b",
            "l4": "llama3.2:3b",
            "l5": "llama3.1:8b",
            "note": "16GB: collapse L3/L4 onto 3B; L5 at 8B.",
        }
    return {
        "l3": "llama3.2:1b",
        "l4": "llama3.2:3b",
        "l5": "llama3.2:3b",
        "note": "<16GB: stay on tiny models; skip L5 upgrades.",
    }


def detect_system_ram_gb() -> float | None:
    """Best-effort total RAM in GiB (macOS/Linux)."""
    try:
        import os

        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024**3), 1)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        import subprocess

        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        return round(int(out) / (1024**3), 1)
    except Exception:
        return None
