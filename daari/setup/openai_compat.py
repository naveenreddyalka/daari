from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from daari.config.settings import Settings

OPENAI_COMPAT_ENV_PATH = Path.home() / ".daari" / ".env.example"
FRONTIER_SNIPPET_MARKER = "# daari-frontier-key"


@dataclass
class OpenAICompatResult:
    base_url: str
    env_example_path: Path
    env_example_written: bool


@dataclass
class FrontierHintResult:
    shell: str
    profile_path: Path
    profile_updated: bool
    env_example_path: Path
    env_example_written: bool


def print_openai_compat_recipe(settings: Settings) -> str:
    base_url = f"http://{settings.server.host}:{settings.server.port}/v1"
    lines = [
        f"export OPENAI_BASE_URL='{base_url}'",
        "export OPENAI_API_KEY='daari-local'",
        "export OPENAI_MODEL='daari'",
    ]
    return "\n".join(lines)


def write_openai_env_example(
    settings: Settings,
    *,
    path: Path | None = None,
    include_frontier_hint: bool = True,
) -> bool:
    resolved_path = path or OPENAI_COMPAT_ENV_PATH
    base_url = f"http://{settings.server.host}:{settings.server.port}/v1"
    content = [
        "# daari OpenAI-compatible environment template",
        f"OPENAI_BASE_URL={base_url}",
        "OPENAI_API_KEY=daari-local",
        "OPENAI_MODEL=daari",
    ]
    if include_frontier_hint:
        content.extend(
            [
                "",
                "# Optional: frontier escalation key for L6",
                "# DAARI_FRONTIER_API_KEY=sk-...",
            ]
        )
    rendered = "\n".join(content).strip() + "\n"

    changed = True
    if resolved_path.is_file() and resolved_path.read_text(encoding="utf-8") == rendered:
        changed = False
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(rendered, encoding="utf-8")
    return changed


def _shell_profile_path(shell: str) -> Path:
    resolved = shell.strip().lower()
    home = Path.home()
    if resolved == "bash":
        return home / ".bashrc"
    if resolved == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".zshrc"


def write_frontier_shell_hint(*, shell: str, profile_path: Path | None = None) -> tuple[Path, bool]:
    path = profile_path or _shell_profile_path(shell)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if FRONTIER_SNIPPET_MARKER in existing:
        return path, False

    snippet = (
        "\n"
        f"{FRONTIER_SNIPPET_MARKER}\n"
        "# Optional daari frontier key (do not commit this):\n"
        "# export DAARI_FRONTIER_API_KEY='sk-...'\n"
        "# end daari-frontier-key\n"
    )
    path.write_text(existing + snippet, encoding="utf-8")
    return path, True


def setup_openai_compat(
    settings: Settings,
    *,
    write_env_example: bool = True,
) -> OpenAICompatResult:
    typer.echo("OpenAI-compatible env for daari:\n")
    typer.echo(print_openai_compat_recipe(settings))
    typer.echo("\nPython example:")
    typer.echo("  from openai import OpenAI")
    typer.echo("  client = OpenAI()  # reads OPENAI_* env vars")
    typer.echo("  client.chat.completions.create(model='daari', messages=[...])")
    typer.echo("\nTypeScript example:")
    typer.echo("  import OpenAI from 'openai'")
    typer.echo("  const client = new OpenAI() // reads OPENAI_* env vars")
    typer.echo("  await client.chat.completions.create({ model: 'daari', messages: [...] })")

    wrote = False
    if write_env_example:
        wrote = write_openai_env_example(settings, include_frontier_hint=True)
        typer.echo(f"\nWrote env template: {OPENAI_COMPAT_ENV_PATH}")
    return OpenAICompatResult(
        base_url=f"http://{settings.server.host}:{settings.server.port}/v1",
        env_example_path=OPENAI_COMPAT_ENV_PATH,
        env_example_written=wrote,
    )


def setup_frontier_key_hint(
    settings: Settings,
    *,
    shell: str,
    write_profile_snippet: bool = False,
    write_env_example: bool = True,
) -> FrontierHintResult:
    env_written = False
    if write_env_example:
        env_written = write_openai_env_example(settings, include_frontier_hint=True)
        typer.echo(f"Wrote env template: {OPENAI_COMPAT_ENV_PATH}")

    profile_path = _shell_profile_path(shell)
    profile_updated = False
    if write_profile_snippet:
        profile_path, profile_updated = write_frontier_shell_hint(shell=shell, profile_path=profile_path)
        action = "Updated" if profile_updated else "Already present"
        typer.echo(f"{action} shell profile hint: {profile_path}")

    typer.echo("Frontier key (optional): export DAARI_FRONTIER_API_KEY='sk-...'")
    typer.echo("This key is intentionally not written to ~/.daari/config.yaml.")
    return FrontierHintResult(
        shell=shell,
        profile_path=profile_path,
        profile_updated=profile_updated,
        env_example_path=OPENAI_COMPAT_ENV_PATH,
        env_example_written=env_written,
    )
