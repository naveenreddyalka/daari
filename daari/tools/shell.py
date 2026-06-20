from __future__ import annotations

import asyncio
import os
import shlex
from dataclasses import dataclass


@dataclass
class ShellResult:
    command: str
    output: str
    exit_code: int


class ShellExecutor:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def run(self, command: str, *, cwd: str | None = None) -> ShellResult:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd or os.getcwd(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            return ShellResult(command=command, output="Command timed out.", exit_code=124)

        output = (stdout or b"").decode("utf-8", errors="replace")
        output = output.strip()[:12000]
        return ShellResult(command=command, output=output, exit_code=process.returncode or 0)

    @staticmethod
    def normalize(command: str) -> str:
        return " ".join(shlex.split(command))

