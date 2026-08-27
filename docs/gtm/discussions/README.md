# GitHub Discussions templates

> Community surface for daari. License is [PolyForm Noncommercial](../../../LICENSE) — say **source-available / local-first**, never “open source.”
> Docs: https://naveenreddyalka.github.io/daari/  
> Repo: https://github.com/naveenreddyalka/daari

The welcome thread is already live (human-published, not a bot flood):
[Welcome — daari v1.3.0](https://github.com/naveenreddyalka/daari/discussions/238).

**Do not spam.** One welcome post. Recreate it only if that thread is deleted.

## Categories

| Category | Use |
|----------|-----|
| Announcements | Releases and project news (`welcome.md`) |
| Show and tell | `daari report` savings, setups that worked (`show-report.md`) |
| Q&A | Cursor / Claude Code / tunnel help (`setup-help.md`) |

## Publish with `gh` (human or one-time agent with confirmation)

```bash
# already posted as discussion 238 — do not run again unless that thread is gone
gh discussion create \
  --repo naveenreddyalka/daari \
  --category "Announcements" \
  --title "Welcome — daari v1.3.0 (source-available, local-first)" \
  --body-file docs/gtm/discussions/welcome.md
```

Optional follow-ups (only when a human asks for a pinned starter):

```bash
gh discussion create \
  --repo naveenreddyalka/daari \
  --category "Show and tell" \
  --title "Show your daari report savings" \
  --body-file docs/gtm/discussions/show-report.md

gh discussion create \
  --repo naveenreddyalka/daari \
  --category "Q&A" \
  --title "Cursor / Claude Code setup help" \
  --body-file docs/gtm/discussions/setup-help.md
```

Never auto-comment, upvote, or open a second welcome thread.
