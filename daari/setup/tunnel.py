from __future__ import annotations

import re
from typing import Iterable

_TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


def parse_cloudflared_tunnel_url(line: str) -> str | None:
    """Extract a public trycloudflare URL from one output line."""
    match = _TUNNEL_URL_PATTERN.search(line)
    if match is None:
        return None
    return match.group(0)


def find_cloudflared_tunnel_url(lines: Iterable[str]) -> str | None:
    """Return first tunnel URL seen in cloudflared output."""
    for line in lines:
        url = parse_cloudflared_tunnel_url(line)
        if url:
            return url
    return None
