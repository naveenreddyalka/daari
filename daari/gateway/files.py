"""OpenAI-compatible Files API — local disk store for Batch JSONL (#442)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MiB


@dataclass
class StoredFile:
    id: str
    filename: str
    purpose: str
    bytes: int
    created_at: int = field(default_factory=lambda: int(time.time()))
    path: Path | None = None

    def as_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "object": "file",
            "bytes": self.bytes,
            "created_at": self.created_at,
            "filename": self.filename,
            "purpose": self.purpose,
        }


class FileStore:
    """Disk-backed OpenAI-shaped file registry under the daari data dir."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(1, int(max_bytes))
        self._meta_path = self.root / "index.json"
        self._files: dict[str, StoredFile] = {}
        self._order: list[str] = []
        self._load_index()

    def _load_index(self) -> None:
        if not self._meta_path.is_file():
            return
        try:
            raw = json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        for entry in raw.get("files") or []:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            file_id = str(entry["id"])
            path = self.root / f"{file_id}.bin"
            stored = StoredFile(
                id=file_id,
                filename=str(entry.get("filename") or "upload"),
                purpose=str(entry.get("purpose") or "batch"),
                bytes=int(entry.get("bytes") or 0),
                created_at=int(entry.get("created_at") or time.time()),
                path=path if path.is_file() else None,
            )
            if stored.path is None:
                continue
            self._files[file_id] = stored
            self._order.append(file_id)

    def _persist_index(self) -> None:
        payload = {
            "files": [
                {
                    "id": stored.id,
                    "filename": stored.filename,
                    "purpose": stored.purpose,
                    "bytes": stored.bytes,
                    "created_at": stored.created_at,
                }
                for file_id in self._order
                if (stored := self._files.get(file_id)) is not None
            ]
        }
        self._meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create(
        self,
        *,
        content: bytes,
        filename: str,
        purpose: str = "batch",
    ) -> StoredFile:
        if len(content) > self.max_bytes:
            raise ValueError(
                f"file exceeds max size of {self.max_bytes} bytes "
                f"({len(content)} bytes uploaded)"
            )
        file_id = f"file-{uuid.uuid4().hex}"
        path = self.root / f"{file_id}.bin"
        path.write_bytes(content)
        stored = StoredFile(
            id=file_id,
            filename=filename or "upload",
            purpose=purpose or "batch",
            bytes=len(content),
            path=path,
        )
        self._files[file_id] = stored
        self._order.append(file_id)
        self._persist_index()
        return stored

    def get(self, file_id: str) -> StoredFile | None:
        return self._files.get(file_id)

    def list_files(self, *, purpose: str | None = None, limit: int = 10000) -> list[StoredFile]:
        ids = list(reversed(self._order))
        out: list[StoredFile] = []
        for file_id in ids:
            stored = self._files.get(file_id)
            if stored is None:
                continue
            if purpose and stored.purpose != purpose:
                continue
            out.append(stored)
            if len(out) >= max(1, min(limit, 10000)):
                break
        return out

    def read_bytes(self, file_id: str) -> bytes | None:
        stored = self.get(file_id)
        if stored is None or stored.path is None or not stored.path.is_file():
            return None
        return stored.path.read_bytes()

    def read_text(self, file_id: str) -> str | None:
        raw = self.read_bytes(file_id)
        if raw is None:
            return None
        return raw.decode("utf-8")

    def delete(self, file_id: str) -> bool:
        stored = self._files.pop(file_id, None)
        if stored is None:
            return False
        self._order = [item for item in self._order if item != file_id]
        if stored.path is not None and stored.path.is_file():
            try:
                stored.path.unlink()
            except OSError:
                pass
        self._persist_index()
        return True

    def write_jsonl(
        self,
        *,
        lines: Iterable[dict[str, Any]],
        filename: str,
        purpose: str,
    ) -> StoredFile:
        body = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        return self.create(content=body.encode("utf-8"), filename=filename, purpose=purpose)


def parse_batch_jsonl(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse OpenAI batch input JSONL into request objects + line errors.

    Returns ``(requests, errors)`` where each error has
    ``code``, ``message``, ``param``, ``line`` (1-based).
    """
    requests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                {
                    "code": "invalid_json",
                    "message": f"line {index}: {exc.msg}",
                    "param": "input_file_id",
                    "line": index,
                }
            )
            continue
        if not isinstance(entry, dict):
            errors.append(
                {
                    "code": "invalid_request",
                    "message": f"line {index}: expected a JSON object",
                    "param": "input_file_id",
                    "line": index,
                }
            )
            continue
        if "body" in entry and isinstance(entry["body"], dict):
            requests.append(entry)
        elif "messages" in entry:
            requests.append(entry)
        else:
            errors.append(
                {
                    "code": "invalid_request",
                    "message": (
                        f"line {index}: must be a chat-completion body or "
                        "{custom_id, method, url, body}"
                    ),
                    "param": "input_file_id",
                    "line": index,
                }
            )
    return requests, errors
