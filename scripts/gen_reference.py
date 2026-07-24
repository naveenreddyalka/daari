"""Generate API and config reference pages for the docs site (issue #114).

Run: python scripts/gen_reference.py [output_dir]

Writes config.md (every settings key with type/default/description, from the
pydantic model — always in sync with the code) and api.md (every HTTP route,
from the FastAPI OpenAPI schema).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from daari.config.settings import Settings


def _default_repr(field: Any) -> str:
    if field.default_factory is not None:
        try:
            value = field.default_factory()
        except TypeError:
            return "—"
        if isinstance(value, BaseModel):
            return "*(section)*"
        return f"`{value!r}`"
    default = field.default
    if type(default).__name__ == "PydanticUndefinedType":
        return "*(required)*"
    if isinstance(default, BaseModel):
        return "*(section)*"
    return f"`{default!r}`"


def _type_repr(annotation: Any) -> str:
    text = getattr(annotation, "__name__", None) or str(annotation)
    return text.replace("typing.", "").replace("NoneType", "None")


def iter_config_rows(model: type[BaseModel], prefix: str = "") -> list[tuple[str, str, str, str]]:
    """Flatten nested settings models into (key, type, default, description) rows."""
    rows: list[tuple[str, str, str, str]] = []
    for name, field in model.model_fields.items():
        path = f"{prefix}.{name}" if prefix else name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            rows.extend(iter_config_rows(annotation, path))
            continue
        rows.append(
            (path, _type_repr(annotation), _default_repr(field), field.description or "")
        )
    return rows


def render_config_reference() -> str:
    lines = [
        "# Configuration reference",
        "",
        "Generated from the pydantic settings model — do not edit by hand.",
        "",
        "Keys live in `~/.daari/config.yaml` (nested YAML), can be overridden per-project",
        "in `.daari.yaml`, and every key is also settable via environment variable:",
        "`DAARI_<SECTION>__<KEY>` (double underscore per nesting level).",
        "",
        "| Key | Type | Default | Description |",
        "|-----|------|---------|-------------|",
    ]
    for key, type_text, default, description in iter_config_rows(Settings):
        lines.append(f"| `{key}` | {type_text} | {default} | {description} |")
    lines.append("")
    return "\n".join(lines)


def render_api_reference() -> str:
    from daari.server.app import create_app

    app = create_app(Settings())
    schema = app.openapi()
    lines = [
        "# HTTP API reference",
        "",
        "Generated from the FastAPI OpenAPI schema — do not edit by hand.",
        "",
        f"OpenAPI version: {schema.get('openapi', '?')} · daari gateway on `127.0.0.1:11435` by default.",
        "",
        "| Method | Path | Summary |",
        "|--------|------|---------|",
    ]
    for path, methods in sorted(schema.get("paths", {}).items()):
        for method, operation in sorted(methods.items()):
            summary = operation.get("summary") or operation.get("operationId", "")
            lines.append(f"| `{method.upper()}` | `{path}` | {summary} |")
    lines.append("")
    return "\n".join(lines)


def main(output_dir: str | None = None) -> None:
    out = Path(output_dir or "docs/reference")
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.md").write_text(render_config_reference(), encoding="utf-8")
    (out / "api.md").write_text(render_api_reference(), encoding="utf-8")
    print(f"Wrote {out / 'config.md'} and {out / 'api.md'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
