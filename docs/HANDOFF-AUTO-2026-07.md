# Handoff — Auto-mode deepeners (2026-07-24)

> For review by a stronger model next month. **Not** production-certified.
> Built under Auto mode after fable-5 token limit; skipped deep testing / code review / live setup.

## Context

Roadmap v2 trains F1–F5 landed on `main` via PRs #124–#134 (+ #126/#129/#131/#133).
This branch/commit deepens tracer-bullet areas that were thin:

| Slice | What landed | Review focus |
|---|---|---|
| Periodic org policy sync | `daari/enterprise/policy_sync.py`; hooked into `AppContext.start_org_learning_sync` when `enterprise.policy_sync_url` is set | Signature failure modes; concurrent apply vs in-flight requests; whether persist should default on |
| Config editor persist | `PATCH /v1/daari/config` accepts `persist: true` → `daari/config/persist.py` writes `~/.daari/config.yaml` | Path injection / partial merge correctness; race with `Settings.load` |
| D4 defaults proposal | `daari learn propose-defaults` + `daari/learning/propose_defaults.py` | Heuristic quality; schema vs real `build_collective_stats` output; never auto-promote |
| Web UI config panel | `packages/web-ui` Load/Save for confidence / prefer / daily budget | Auth headers when `server.api_key` set; disabled-state UX; no SSO token field yet |
| Docs | CHANGELOG Unreleased + this handoff | Accuracy vs git history |

## Explicitly NOT done (user-gated / next-month)

1. **PyPI upload** — needs `PYPI_API_TOKEN` in repo secrets; cut 1.2.x or 1.3.0.
2. **Homebrew sha256** — fill `Formula/daari.rb` after release tarball exists.
3. **Real OIDC** — **done** (#136 / PR #140); HMAC retained for local/dev.
4. **Redis L1 semantic** — **done** (#135 / PR #139).
5. **Live Postgres / Redis E2E** — unit fakes only; tracked as [#142](https://github.com/naveenreddyalka/daari/issues/142).
6. **Config editor auth in web-ui** — **done** (#141); toolbar Bearer field + `localStorage`.
7. **Full suite + live E2E** — intentionally skipped this pass; run default pytest + daemon smoke before shipping a release.
8. **D4 promotion** — proposals under `~/.daari/proposals/` must stay review-gated.

## Suggested next-month review checklist

- [ ] `pytest -m "not integration and not benchmark" -q` green on this diff
- [ ] Manual: enable `observability.config_editor`, PATCH with/without `persist`, restart daemon
- [ ] Manual: set `enterprise.policy_sync_url` + signing secret; confirm loop applies without crashing serve
- [ ] `daari learn export-stats --out /tmp/s.json && daari learn propose-defaults --from /tmp/s.json`
- [ ] Web UI: config card with and without API key / SSO
- [ ] Security pass on persist + policy_sync (YAML merge, HMAC, admin role)
- [ ] Decide 1.3.0 scope: Redis L1, real OIDC, ghcr publish, PyPI

## How to resume

```bash
git checkout main && git pull
# or the PR branch from this deepen commit
source .venv/bin/activate
pip install -e ".[dev]"
pytest -m "not integration and not benchmark" -q
```

Open issues: prefer new `auto-dev` issues labeled `needs-review` for items 3–8 above rather than expanding this handoff.
