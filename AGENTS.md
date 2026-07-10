# AGENTS.md — how agents work in this repo

Contract for any AI agent (Cursor Automation, cursor-agent CI run, or interactive session) doing development in `daari`. Human-facing docs live in [docs/](docs/); this file is the agent operating manual.

## Environment

```bash
python3.12 -m venv .venv          # if .venv missing
source .venv/bin/activate
pip install -e ".[dev]"
```

- Python 3.12, FastAPI, Typer, diskcache. Local models run via Ollama (`http://127.0.0.1:11434`).
- CI (and agents without Ollama) run the mocked suite only.

## Test commands

| Suite | Command | When |
|-------|---------|------|
| Default (CI parity) | `pytest -m "not integration and not benchmark" -q` | Always, before every commit |
| Live Ollama | `OLLAMA_HOST=http://127.0.0.1:11434 pytest -m integration` | Local machines with Ollama only |
| Benchmark | `pytest -m benchmark` | Optional |

A change is not done until the default suite passes.

## Working an issue

1. Pick the highest-priority open issue labeled `auto-dev` (P1 > P2 > P3, then oldest). Skip issues with an open linked PR or an `agent:working` label; add `agent:working` when you start.
2. Branch from latest `main`: `autodev/<issue-number>-<slug>` (e.g. `autodev/1-tool-hallucination`).
3. TDD: write the failing test first, then the minimal implementation. Acceptance criteria in the issue are the definition of done.
4. Keep the change scoped to the issue. No drive-by refactors, no new dependencies unless the issue calls for them.
5. Update docs touched by the change: [docs/TRACKING.md](docs/TRACKING.md) status row, plus any setup/ADR docs the issue lists.
6. Run the default test suite; fix what you broke.

## Commits and PRs

- Conventional commits: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`, `chore: ...`.
- One PR per issue. Title: conventional-commit style; body must include `Closes #<issue>`, a summary, and the test output tail.
- Push branch, open PR against `main`, then enable auto-merge: `gh pr merge --auto --squash`.
- CI (`test` check) and review must pass before merge; do not bypass, do not force-push shared branches.

## Hard limits (human-only actions)

Never do these autonomously — stop and leave a comment on the issue/PR instead:

- Git tags, GitHub releases, PyPI publishes
- Force-push, history rewrites, branch protection changes
- Major-version dependency bumps or new runtime dependencies not named in the issue
- Deleting issues/labels, editing workflow files in `.github/workflows/` beyond what an issue explicitly requires
- Committing secrets, `.env` files, or anything under `~/.daari/`

## Failure protocol

- Test failures you cannot fix within the issue scope: comment findings on the issue, remove `agent:working`, leave the branch pushed for a human.
- Flaky/environmental failure: retry once; if still failing, file a new issue labeled `auto-dev,regression` with logs.

## Code style

- Match existing patterns (`daari/gateway/`, `daari/router/`). No narrating comments; comments explain non-obvious intent only.
- Public behavior changes need a test at the integration level (`tests/integration/test_gateway_flow.py` for gateway work).
- Debug/event logging goes through `log_gateway_event()` (`daari/gateway/request_log.py`), never `print`.
