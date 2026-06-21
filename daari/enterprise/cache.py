from __future__ import annotations

from pathlib import Path

from daari.enterprise.config import OrgSettings


def resolve_org_cache_root(org: OrgSettings) -> Path | None:
    org_id = org.resolved_org_id
    if not org.enabled or not org_id:
        return None
    if org.shared_cache_path:
        return Path(org.shared_cache_path).expanduser()
    return Path.home() / ".daari" / "org" / org_id / "cache"


def resolve_org_shared_cache_root(org: OrgSettings) -> Path | None:
    org_id = org.resolved_org_id
    if not org_id:
        return None
    if org.shared_cache_path:
        return Path(org.shared_cache_path).expanduser()
    return Path.home() / ".daari" / "org" / org_id / "shared-cache"


def resolve_org_scoped_path(base_path: Path, org: OrgSettings, *, leaf: str) -> Path:
    root = resolve_org_cache_root(org)
    if root is None:
        return base_path
    return root / leaf
