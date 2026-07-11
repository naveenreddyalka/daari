"""Markdown renderers for client-shareable reports and traces (issue #35)."""

from __future__ import annotations

from typing import Any


def report_markdown(payload: dict[str, Any], *, days: int = 7) -> str:
    if not payload.get("enabled", False):
        return "# daari usage report\n\nUsage ledger is disabled (settings: usage.enabled).\n"

    lines = [f"# daari usage report (last {days} days)", ""]

    lines.append("| day | requests | cache hits | prompt chars | completion chars |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for entry in payload.get("days", []):
        lines.append(
            f"| {entry['day']} | {entry['requests']} | {entry['cache_hits']} |"
            f" {entry['prompt_chars']} | {entry['completion_chars']} |"
        )
    lines.append("")

    lines.append("## Tier breakdown")
    lines.append("")
    lines.append("| day | tier | requests | cache hits | prompt chars | completion chars |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for entry in payload.get("days", []):
        for tier in sorted(entry.get("tiers", {})):
            stats = entry["tiers"][tier]
            lines.append(
                f"| {entry['day']} | {tier} | {stats['requests']} | {stats['cache_hits']} |"
                f" {stats['prompt_chars']} | {stats['completion_chars']} |"
            )
    lines.append("")

    totals = payload.get("totals", {})
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total requests: {totals.get('requests', 0)}")
    lines.append(f"- Cache hits: {totals.get('cache_hits', 0)}")
    lines.append(f"- Local requests: {totals.get('local_requests', 0)}")
    lines.append(f"- Frontier requests: {totals.get('frontier_requests', 0)}")
    lines.append("")
    lines.append(f"**Estimated saved:** ${totals.get('estimated_saved_usd', 0.0):.4f}")
    lines.append("")
    return "\n".join(lines)


def trace_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# daari request trace `{payload.get('trace_id', 'unknown')}`", ""]
    lines.append(f"- **Tier:** {payload.get('tier')}")
    lines.append(f"- **Category:** {payload.get('category')}")
    if payload.get("ts"):
        lines.append(f"- **Timestamp:** {payload['ts']}")
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    lines.append("| elapsed | step | detail |")
    lines.append("| ---: | --- | --- |")
    for step in payload.get("steps", []):
        detail = step.get("detail") or {}
        detail_text = "  ".join(f"{key}={value}" for key, value in detail.items())
        lines.append(f"| +{step.get('elapsed_ms', 0)}ms | {step.get('step', '')} | {detail_text} |")
    lines.append("")
    return "\n".join(lines)
