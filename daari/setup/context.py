from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from daari.config.settings import Settings


@dataclass
class ClearedPath:
    name: str
    path: Path
    existed: bool
    error: str | None = None


def _clear_path(path: Path) -> tuple[bool, str | None]:
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            return False, None
        if path.is_file():
            path.unlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            return True, None
        shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return True, None
    except (PermissionError, OSError) as exc:
        return path.exists(), str(exc)


def clear_context_caches(
    settings: Settings,
    *,
    clear_l0: bool = True,
    clear_l1: bool = True,
    clear_ccs: bool = True,
) -> list[ClearedPath]:
    cleared: list[ClearedPath] = []
    targets: list[tuple[str, Path]] = []
    if clear_l0:
        targets.append(("L0", settings.l0_cache_path))
    if clear_l1:
        targets.append(("L1", settings.l1_cache_path))
    if clear_ccs:
        targets.append(("CCS", settings.context_store_path))

    for name, path in targets:
        existed, error = _clear_path(path.expanduser())
        cleared.append(ClearedPath(name=name, path=path.expanduser(), existed=existed, error=error))
    return cleared
