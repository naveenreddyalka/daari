# daari GTM plan

> Status: executing (2026-08-26)  
> Spine: **Approach C** — public launch for stars + installs now. License is Apache 2.0 ([ADR-0016](../adr/0016-apache-2-relicense.md) / [#227](https://github.com/naveenreddyalka/daari/issues/227)).  
> Say **open source / local-first**. Do not describe the current license as source-available.

## KPI

Unique GitHub viewers and real `pip` / Compose installs. Stars are a lagging signal. Clone counts are not a KPI (CI and the local watchdog inflate them).

## Always-on engine

Mirrors the auto-dev loop. The machine never sleeps on **measure** and **draft**. A human publishes anything that is not first-party (this repo, docs site).

| Loop | Cadence | Machine | Human |
|------|---------|---------|-------|
| Measure | Daily | `python scripts/gtm_scoreboard.py` → `docs/gtm/SCOREBOARD.md` ([#229](https://github.com/naveenreddyalka/daari/issues/229)) | Read the week |
| Draft | On each release / notable merge | [#232](https://github.com/naveenreddyalka/daari/issues/232) shipping note | Edit tone |
| Publish (owned) | When a draft is ready | Open a PR | Merge |
| Publish (HN / Reddit / PH / X) | Calendar below | Drafts in [launches/](launches/) | You post. Stay in comments 6 hours. |
| Listen | Daily | Search queue (later) | You reply in [Discussions](https://github.com/naveenreddyalka/daari/discussions) ([templates](discussions/)) |

**Never:** buy stars, auto-comment, upvote bots, unattended Reddit/HN posts, scrape-and-DM.

## 90-day calendar

| Window | Work | Exit |
|--------|------|------|
| Days 0–3 | Listing + honest README + scoreboard + these drafts | Stranger can explain daari from the repo header |
| Days 4–10 | Proof pack — link existing [vs LiteLLM bench](../developer/resources/benchmark-vs-litellm.md); finish [#173](https://github.com/naveenreddyalka/daari/issues/173) | A Show HN comment has a numbers page |
| Days 11–18 | Post [localllama.md](launches/localllama.md) and [cursor.md](launches/cursor.md) | ≥200 unique viewers in a week (baseline was 8) |
| Days 19–25 | [Show HN](launches/show-hn.md) Tue–Thu morning ET | Long thread or front page; 50–200 stars is a good first hit |
| Days 26–40 | [Product Hunt](launches/product-hunt.md) after HN dust; [#231](https://github.com/naveenreddyalka/daari/issues/231) compare pages | Search “local llm router cursor” shows us |
| Days 41–90 | Weekly shipping note + scoreboard. Kill channels that only produce CI clones | Trailing 7-day unique viewers stay above 50 |

## Commands

```bash
python scripts/gtm_scoreboard.py              # refresh SCOREBOARD.md
python scripts/gtm_scoreboard.py --check-drought   # exit 2 if unique viewers (14d) == 0
```

Cloud `autodev-cycle` will not pick GTM issues until [#226](https://github.com/naveenreddyalka/daari/issues/226) (`CURSOR_API_KEY`).
