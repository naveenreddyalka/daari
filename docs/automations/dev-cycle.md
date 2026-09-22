# Automation draft: autodev dev cycle

Ready-to-create Cursor Automation. To create: open the Agents Window, run the automate skill ("create a Cursor automation from docs/automations/dev-cycle.md"), or paste the fields into the Automations editor manually.

| Field | Value |
|-------|-------|
| Name | daari autodev — dev cycle |
| Description | Every 4 hours, pick the top open `auto-dev` issue in naveenreddyalka/daari, implement it per AGENTS.md, open an auto-merging PR. |
| Trigger | Schedule (cron): `0 */4 * * *` |
| Repo / branch | naveenreddyalka/daari @ main |
| Tools | none extra (repo + terminal are default) |

## Prompt

```
You are working in naveenreddyalka/daari. Read AGENTS.md at the repo root and follow it exactly.

0. Drain first. List open PRs on autodev/* branches with auto-merge enabled and
   handle them in issue priority order before picking anything new:
   - BEHIND / BLOCKED with green checks: gh pr update-branch, wait for the
     test check, then gh pr merge --squash yourself (main moves too fast for
     auto-merge to win the up-to-date race).
   - DIRTY (conflicting): check out, merge origin/main, resolve (keep both
     docs/TRACKING.md ### sections), run the default suite, push, then merge.
   - Genuinely red or unresolvable in 15 min: comment findings on the PR, move on.
1. List open issues labeled auto-dev that do NOT have the agent:working label and no open linked PR:
   gh issue list --label auto-dev --state open --json number,title,labels
   Pick the highest priority (P1 > P2 > P3, then lowest issue number). If none,
   refill: follow docs/automations/prd-cycle.md, file 3–5 auto-dev issues
   (features or performance / usability / testability / benchmarking /
   documentation / tooling / tech debt), then pick again. Never stop solely
   because the backlog is empty.
2. Add the agent:working label to the chosen issue.
3. Create branch autodev/<issue-number>-<short-slug> from latest main.
4. Implement the issue TDD-style: failing test first, then the minimal fix. Respect the acceptance criteria checklist in the issue body.
5. Run: pytest -m "not integration and not benchmark" -q  — everything must pass.
6. Update docs/TRACKING.md if the issue corresponds to a tracked row.
7. Commit (conventional commits), push, open a PR with "Closes #<issue>" in the body, then run:
   gh pr merge --auto --squash
8. Remove the agent:working label. If blocked, comment your findings on the issue and remove the label.
9. Go back to step 1 and keep draining. Time box: before each pick, check the
   wall clock against your run's deadline (the GitHub Actions fallback exports
   AUTODEV_DEADLINE_EPOCH, 50 min after job start). With under 10 minutes left,
   do not pick another issue — leave the current PR auto-merging with
   agent:working removed, print "time box reached", and exit 0. Never start an
   issue you cannot finish.

Hard limits from AGENTS.md apply: no tags, no releases, no force-push, no new runtime deps, no workflow-file edits.
```

## Why drain first

Branch protection requires PRs to be up to date with `main`, and during a run
`main` moves every few minutes. A PR the agent is not actively babysitting gets
rebased by `scripts/autodev_pr_watch.py`, finishes CI, and is already `BEHIND`
again — auto-merge never fires. Conflicted (`DIRTY`) PRs are worse: the watcher
only resolves `docs/TRACKING.md`. Draining at the top of each run keeps
higher-priority work from starving behind the run's own new PRs (#983).

## Why the time box

Runs drain several issues back-to-back. Without a stopping rule the agent runs
until `timeout-minutes` kills the job — usually while waiting on the last
auto-merge — which shows as `cancelled` and can strand an `agent:working`
label or unpushed branch until `scripts/autodev_pr_watch.py` sweeps it. The
GitHub Actions fallback ([`.github/workflows/autodev.yml`](../../.github/workflows/autodev.yml))
sets `timeout-minutes: 60` and a 50-minute pick deadline so the final PR always
has room to settle.
