"""OpenRouter-shaped `provider` object (G2 / #224)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ProviderPreferences(BaseModel):
    """Client routing constraints Cursor already sends to OpenRouter."""

    order: list[str] | None = None
    only: list[str] | None = None
    ignore: list[str] | None = None
    sort: Literal["price", "throughput", "latency"] | None = None
    zdr: bool = False
    data_collection: Literal["allow", "deny"] | None = None
    max_price: dict[str, Any] | None = None
    allow_fallbacks: bool | None = None


class ZdrUnavailable(Exception):
    """`zdr: true` was requested but no L6 slot declares zero-data-retention."""

    def __init__(self) -> None:
        super().__init__(
            "no configured L6 provider declares zdr; refusing to drop the constraint"
        )


class RegionUnavailable(Exception):
    """region_pin set but no L6 slot declares a matching region (#466)."""

    def __init__(self, pin: str) -> None:
        self.pin = pin
        super().__init__(
            f"no configured L6 provider declares region={pin!r}; "
            "refusing to route out of the pinned region"
        )


def parse_provider(raw: Any) -> ProviderPreferences | None:
    if not raw or not isinstance(raw, dict):
        return None
    prefs = ProviderPreferences.model_validate(raw)
    if prefs.model_dump(exclude_defaults=True) == {}:
        return None
    return prefs


def as_openrouter_payload(prefs: ProviderPreferences) -> dict[str, Any]:
    return prefs.model_dump(exclude_none=True, exclude_defaults=True) | (
        {"zdr": True} if prefs.zdr else {}
    )


def is_openrouter_base(url: str) -> bool:
    return "openrouter.ai" in (url or "").lower()


def configured_frontier_slots(settings: Any) -> list[Any]:
    frontier = settings.frontier
    providers = list(getattr(frontier, "providers", None) or [])
    if providers:
        return providers
    from daari.config.settings import FrontierProviderConfig

    return [
        FrontierProviderConfig(
            id=frontier.provider,
            base_url=frontier.base_url,
            model=frontier.model,
            zdr=False,
        )
    ]


def require_zdr_slot(prefs: ProviderPreferences | None, slots: list[Any]) -> None:
    if prefs is None or not prefs.zdr:
        return
    if not any(bool(getattr(slot, "zdr", False)) for slot in slots):
        raise ZdrUnavailable()


def normalize_region(value: str | None) -> str:
    return (value or "").strip().lower()


def require_region_slot(region_pin: str | None, slots: list[Any]) -> None:
    pin = normalize_region(region_pin)
    if not pin:
        return
    if any(_slot_satisfies_region(slot, pin) for slot in slots):
        return
    raise RegionUnavailable(pin)


def filter_slots_for_region(region_pin: str | None, slots: list[Any]) -> list[Any]:
    pin = normalize_region(region_pin)
    if not pin:
        return list(slots)
    return [slot for slot in slots if _slot_satisfies_region(slot, pin)]


def _slot_satisfies_region(slot: Any, pin: str) -> bool:
    if normalize_region(getattr(slot, "region", "")) == pin:
        return True
    # OpenRouter in-region routing is hostname-based (#1052): a global
    # openrouter.ai slot can honor us/eu pins by rewriting the base URL.
    from daari.router.openrouter import openrouter_can_satisfy_region

    base = ""
    executor = getattr(slot, "executor", None)
    if executor is not None:
        base = str(getattr(executor, "base_url", "") or "")
    if not base:
        base = str(getattr(slot, "base_url", "") or "")
    return openrouter_can_satisfy_region(pin, base)


def usage_cost_and_cache(
    data: dict[str, Any],
) -> tuple[float | None, int | None, int]:
    """Return (reported_cost, cache_read_tokens, cache_write_tokens).

    OpenAI/OpenRouter: ``prompt_tokens_details.cached_tokens`` is cache read.
    Anthropic: ``cache_read_input_tokens`` / ``cache_creation_input_tokens``.
    Multi-agent (#1500): when nested agent costs exist and top-level ``usage.cost``
    already covers them, keep the aggregated cost; otherwise sum parent + nested.
    """
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    cost_raw = usage.get("cost")
    cost = float(cost_raw) if isinstance(cost_raw, (int, float)) else None
    try:
        from daari.observability.tokens import nested_agent_usages

        agents = nested_agent_usages(data)
    except Exception:
        agents = []
    nested_costs = [float(a["cost"]) for a in agents if isinstance(a.get("cost"), (int, float))]
    if nested_costs:
        nested_sum = sum(nested_costs)
        if cost is not None and cost + 1e-12 >= nested_sum:
            pass  # aggregated top-level already includes subagents
        else:
            cost = (cost or 0.0) + nested_sum
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    input_details = usage.get("input_tokens_details")
    input_details = input_details if isinstance(input_details, dict) else {}
    cached_raw = (
        details.get("cached_tokens")
        or input_details.get("cached_tokens")
        or usage.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
    )
    cached = int(cached_raw) if isinstance(cached_raw, (int, float)) and cached_raw >= 0 else None
    write_raw = (
        usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_tokens")
        or input_details.get("cache_write_tokens")
    )
    write = int(write_raw) if isinstance(write_raw, (int, float)) and write_raw >= 0 else 0
    return cost, cached, write


WEB_SEARCH_USD = 0.01

# Responses output item type → pricing.server_tools key (#2197).
_OUTPUT_ITEM_TOOL_KEYS: dict[str, str] = {
    "web_search_call": "web_search",
    "web_fetch_call": "web_fetch",
    "file_search_call": "file_search",
    "code_interpreter_call": "code_execution",
    "code_execution_call": "code_execution",
}

# Anthropic usage.server_tool_use field → pricing.server_tools key.
_ANTHROPIC_TOOL_REQUEST_KEYS: dict[str, str] = {
    "web_search_requests": "web_search",
    "web_fetch_requests": "web_fetch",
    "file_search_requests": "file_search",
    "code_execution_requests": "code_execution",
}


def _positive_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 0


def _count_web_search_items(output: list[Any]) -> int:
    """Billable web_search_call items: search / missing action only (#1770)."""
    item_count = 0
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "web_search_call":
            continue
        action = item.get("action")
        if action is None:
            item_count += 1
            continue
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type in {None, "", "search"}:
            item_count += 1
    return item_count


def count_server_tool_usage(data: dict[str, Any]) -> dict[str, int]:
    """Count billable server-side tool calls from Responses + Anthropic shapes.

    For web_search, when both Responses items and Anthropic
    ``web_search_requests`` are present, bill the larger count (#1770). Other
    tools use the same max-not-sum rule when both shapes appear.
    """
    item_counts: dict[str, int] = {}
    output = data.get("output")
    if isinstance(output, list):
        web_items = _count_web_search_items(output)
        if web_items:
            item_counts["web_search"] = web_items
        for item in output:
            if not isinstance(item, dict):
                continue
            key = _OUTPUT_ITEM_TOOL_KEYS.get(str(item.get("type") or ""))
            if key is None or key == "web_search":
                continue
            item_counts[key] = item_counts.get(key, 0) + 1

    request_counts: dict[str, int] = {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    server = usage.get("server_tool_use")
    server = server if isinstance(server, dict) else {}
    for field, key in _ANTHROPIC_TOOL_REQUEST_KEYS.items():
        n = _positive_int(server.get(field))
        if n:
            request_counts[key] = n

    keys = set(item_counts) | set(request_counts)
    return {
        key: max(item_counts.get(key, 0), request_counts.get(key, 0)) for key in keys
    }


def resolve_server_tool_prices(pricing: Any = None) -> dict[str, float]:
    """Shipped defaults merged with ``pricing.server_tools`` (operator wins)."""
    from daari.config.settings import _DEFAULT_SERVER_TOOL_PRICES

    prices = {str(k): float(v) for k, v in _DEFAULT_SERVER_TOOL_PRICES.items()}
    configured = getattr(pricing, "server_tools", None) if pricing is not None else None
    if isinstance(configured, dict):
        for key, value in configured.items():
            try:
                prices[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return prices


def server_tool_fees(
    data: dict[str, Any],
    *,
    pricing: Any = None,
) -> tuple[float, dict[str, int]]:
    """Return (total_usd, tool_usage) for server-side tools (#2197).

    Fees sit outside service-tier / region / speed multipliers. Unknown or
    unpriced tool types contribute $0. ``tool_usage`` omits zero counts.
    """
    usage = count_server_tool_usage(data)
    if not usage:
        return 0.0, {}
    prices = resolve_server_tool_prices(pricing)
    total = 0.0
    for tool, count in usage.items():
        total += count * float(prices.get(tool, 0.0) or 0.0)
    return total, usage


def web_search_fee_usd(data: dict[str, Any], *, pricing: Any = None) -> float:
    """Bill Responses web_search_call and Anthropic web_search_requests once.

    Web-search only (legacy helper). ``open_page`` / ``find_in_page`` are not
    searches. When both shapes are present, bill the larger count (#1770).
    Prefer :func:`server_tool_fees` for multi-tool billing (#2197).
    """
    usage = count_server_tool_usage(data)
    count = int(usage.get("web_search", 0) or 0)
    if count <= 0:
        return 0.0
    prices = resolve_server_tool_prices(pricing)
    return count * float(prices.get("web_search", WEB_SEARCH_USD) or WEB_SEARCH_USD)
