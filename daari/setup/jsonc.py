from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def strip_jsonc(text: str) -> str:
    """Normalize JSONC-like text into strict JSON.

    Supports line/block comments, trailing commas, and raw control characters.
    """

    def _sanitize_char(ch: str, *, in_string: bool) -> str:
        code = ord(ch)
        if code >= 0x20:
            return ch
        if ch in "\n\r\t":
            if in_string:
                return {"\n": r"\n", "\r": r"\r", "\t": r"\t"}[ch]
            return ch
        if in_string:
            return f"\\u{code:04x}"
        return ""

    # Pass 1: remove comments while preserving strings and line structure.
    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    in_line_comment = False
    in_block_comment = False
    text_len = len(text)

    while i < text_len:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < text_len else ""

        if in_line_comment:
            if ch in "\n\r":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            if ch in "\n\r":
                out.append(ch)
            i += 1
            continue

        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                i += 1
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                i += 1
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                i += 1
                continue
            out.append(_sanitize_char(ch, in_string=True))
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        out.append(_sanitize_char(ch, in_string=False))
        i += 1

    # Pass 2: remove trailing commas outside strings.
    source = "".join(out)
    cleaned: list[str] = []
    i = 0
    in_string = False
    escaped = False
    source_len = len(source)

    while i < source_len:
        ch = source[i]
        if in_string:
            cleaned.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            cleaned.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < source_len and source[j] in " \t\r\n":
                j += 1
            if j < source_len and source[j] in "}]":
                i += 1
                continue

        cleaned.append(ch)
        i += 1

    return "".join(cleaned)


def load_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        try:
            loaded = json.loads(strip_jsonc(text))
        except json.JSONDecodeError as inner_exc:
            raise ValueError(
                f"Could not parse JSON/JSONC settings in {path}: {inner_exc.msg}"
            ) from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return loaded


def dump_jsonc(data: dict[str, Any], *, indent: int = 4) -> str:
    """Write standard JSON (Cursor accepts it on reload)."""
    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
