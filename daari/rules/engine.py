from __future__ import annotations

import json
import re

import yaml


def apply_l2_rules(text: str) -> tuple[str, str] | None:
    """Return (rule_id, transformed_output) when a deterministic rule matches."""

    stripped = text.strip()

    json_match = re.search(r"(?is)(?:format as json|convert to json)\s*:\s*(.+)$", stripped)
    if json_match:
        raw = json_match.group(1).strip()
        normalized = _coerce_json_like(raw)
        if normalized is not None:
            return ("L2-JSON-01", normalized)

    yaml_match = re.search(r"(?is)convert this yaml to json\s*:?\s*(.+)$", stripped)
    if yaml_match:
        raw_yaml = yaml_match.group(1).strip()
        try:
            parsed = yaml.safe_load(raw_yaml)
            return ("L2-YAML-01", json.dumps(parsed, indent=2, sort_keys=True))
        except Exception:
            return None

    return None


def _coerce_json_like(raw: str) -> str | None:
    try:
        return json.dumps(json.loads(raw), indent=2, sort_keys=True)
    except Exception:
        pass

    # Tiny fixer for common unquoted-key cases.
    fixed = re.sub(r"([{,]\s*)([A-Za-z_][\w-]*)(\s*:)", r'\1"\2"\3', raw)
    fixed = re.sub(r":\s*([A-Za-z_][\w-]*)\s*([,}])", r': "\1"\2', fixed)
    try:
        return json.dumps(json.loads(fixed), indent=2, sort_keys=True)
    except Exception:
        return None

