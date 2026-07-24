# Contributing to daari

Thanks for your interest. daari is an open-source local-first LLM router — contributions of all sizes are welcome.

## Quick start for contributors

```bash
git clone https://github.com/naveenreddyalka/daari.git && cd daari
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # default suite is fully mocked — no Ollama needed
ruff check daari tests      # lint (version pinned in pyproject.toml)
```

Full environment guide: [docs/DEVELOPING.md](docs/DEVELOPING.md). Architecture map: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How we work

- **Backlog:** GitHub issues. Issues labeled `auto-dev` are picked up by the project's autonomous dev loop ([docs/AUTOMATION.md](docs/AUTOMATION.md)); anything else is fair game for humans. Comment on an issue before starting so work isn't duplicated.
- **TDD:** add failing tests first, then the implementation. PRs without tests for behavior changes will be asked to add them.
- **CI:** four required checks on `main` — `test`, `lint`, `sanity`, `extension`. `main` is protected; PRs merge via squash when green.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`). Reference issues (`(#123)`) where relevant.
- **Style:** `ruff` enforced; no comments that narrate the code; keep modules small and duck-typed (see `OllamaExecutor`/`MLXExecutor` for the pattern).

## What makes a good PR

1. One concern per PR — a feature train can be several PRs.
2. Unit tests for logic, integration tests (mocked gateway) for wire behavior.
3. Update [docs/TRACKING.md](docs/TRACKING.md) when a tracked item ships, and the relevant PRD status if you complete one.
4. No new hard dependencies without discussion — daari deliberately stays lean (optional deps like `mlx-lm` are gated).

## Reporting bugs / requesting features

Use the issue templates. For routing-quality problems, include the trace (`daari trace <id>` — redact anything sensitive) and your relevant `~/.daari/config.yaml` routing settings.

## Security issues

Do **not** open a public issue — see [SECURITY.md](SECURITY.md).

## License

By contributing you agree your contributions are licensed under the [Apache License 2.0](LICENSE).
