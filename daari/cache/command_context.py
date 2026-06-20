from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandContextEntry:
    command: str
    cwd: str
    output: str
    exit_code: int
    ran_at: float
    ttl_seconds: int

    @property
    def is_fresh(self) -> bool:
        return (time.time() - self.ran_at) <= self.ttl_seconds


class CommandContextStore:
    """Simple disk-backed command context store (CCS)."""

    def __init__(self, root: str | Path = "~/.daari/context/commands", *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.root = Path(root).expanduser()
        if self.enabled:
            self.root.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, repo_root: str, cwd: str, command: str) -> Path:
        key_input = f"{repo_root}|{cwd}|{command}".encode("utf-8")
        digest = hashlib.sha256(key_input).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, *, repo_root: str, cwd: str, command: str) -> CommandContextEntry | None:
        if not self.enabled:
            return None
        path = self._entry_path(repo_root, cwd, command)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entry = CommandContextEntry(
                command=str(payload.get("command", command)),
                cwd=str(payload.get("cwd", cwd)),
                output=str(payload.get("output", "")),
                exit_code=int(payload.get("exit_code", 0)),
                ran_at=float(payload.get("ran_at", 0.0)),
                ttl_seconds=int(payload.get("ttl_seconds", 0)),
            )
        except Exception:
            return None
        if not entry.is_fresh:
            return None
        return entry

    def put(
        self,
        *,
        repo_root: str,
        cwd: str,
        command: str,
        output: str,
        exit_code: int,
        ttl_seconds: int,
    ) -> None:
        if not self.enabled:
            return
        path = self._entry_path(repo_root, cwd, command)
        payload = {
            "command": command,
            "cwd": cwd,
            "output": output,
            "exit_code": exit_code,
            "ran_at": time.time(),
            "ttl_seconds": ttl_seconds,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

