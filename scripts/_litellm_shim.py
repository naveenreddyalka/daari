"""Minimal OpenAI-compat server around litellm.completion (issue #214).

The official `litellm --config` proxy in 1.97 needs Prisma and a FastAPI pin
that fights starlette. This shim is only for the comparison bench: same
`ollama_chat/` adapter, no paid providers, stdlib HTTP.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from litellm import completion


class Handler(BaseHTTPRequestHandler):
    server_version = "daari-litellm-shim/1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] in {"/health", "/v1/models"}:
            self._json(200, {"data": [{"id": os.environ.get("SHIM_MODEL", "llama3.2:3b")}]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/v1/chat/completions":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        model = body.get("model") or os.environ.get("SHIM_MODEL", "llama3.2:3b")
        messages = body.get("messages") or []
        try:
            result = completion(
                model=f"ollama_chat/{model}",
                messages=messages,
                api_base=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
            )
        except Exception as exc:
            self._json(502, {"error": str(exc)})
            return
        choice = result.choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        self._json(
            200,
            {
                "id": getattr(result, "id", "chatcmpl-shim"),
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content or ""},
                        "finish_reason": getattr(choice, "finish_reason", "stop"),
                    }
                ],
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    os.environ["SHIM_MODEL"] = args.model
    os.environ["OLLAMA_HOST"] = args.ollama
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
