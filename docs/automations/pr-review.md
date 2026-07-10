# Automation draft: autodev PR review

Ready-to-create Cursor Automation (or enable Bugbot for the repo at cursor.com/dashboard → Bugbot, which covers the same need with zero prompt).

| Field | Value |
|-------|-------|
| Name | daari autodev — PR review |
| Description | Review every opened PR in naveenreddyalka/daari for bugs and AGENTS.md compliance; approve or request changes. |
| Trigger | GitHub: pull request opened (repo naveenreddyalka/daari) |
| Tools | Comment on PRs |

## Prompt

```
Review this PR in naveenreddyalka/daari like a strict senior engineer.

Checklist:
- Does the diff actually satisfy the acceptance criteria of the linked issue (body says "Closes #N")?
- Bugs: logic errors, missed edge cases in changed code paths, broken OpenAI/Anthropic wire compatibility (daari/gateway/), broken routing tiers (daari/router/router.py).
- Tests: new behavior must have a test; pytest markers must keep the change out of CI-blocked live suites.
- AGENTS.md compliance: no new runtime deps, no workflow edits, no secrets, conventional commit title.

If everything passes: approve the PR with a short summary comment.
If not: leave specific blocking comments referencing file/line, and do NOT approve.
```

## Merge gate

Branch protection on main requires the CI `test` check; with auto-merge enabled the PR lands only when CI is green. To also require this review formally, add "required approving reviews: 1" to branch protection once a review bot account is active.
