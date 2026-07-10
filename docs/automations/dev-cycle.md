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

1. List open issues labeled auto-dev that do NOT have the agent:working label and no open linked PR:
   gh issue list --label auto-dev --state open --json number,title,labels
   Pick the highest priority (P1 > P2 > P3, then lowest issue number). If none, stop and report "backlog empty".
2. Add the agent:working label to the chosen issue.
3. Create branch autodev/<issue-number>-<short-slug> from latest main.
4. Implement the issue TDD-style: failing test first, then the minimal fix. Respect the acceptance criteria checklist in the issue body.
5. Run: pytest -m "not integration and not benchmark" -q  — everything must pass.
6. Update docs/TRACKING.md if the issue corresponds to a tracked row.
7. Commit (conventional commits), push, open a PR with "Closes #<issue>" in the body, then run:
   gh pr merge --auto --squash
8. Remove the agent:working label. If blocked, comment your findings on the issue and remove the label.

Hard limits from AGENTS.md apply: no tags, no releases, no force-push, no new runtime deps, no workflow-file edits.
```
