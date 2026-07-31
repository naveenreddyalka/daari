# FAQ

**Is daari a LiteLLM replacement?**  
No. LiteLLM optimizes multi-provider cloud access. daari optimizes **local-first** execution and measured cache trust. See [Compare](compare.md).

**Why does Cursor need a tunnel?**  
Cursor BYOK is proxied through Cursor cloud, which blocks private IPs. Claude Code / JetBrains / VS Code use localhost directly.

**Where is my data?**  
Caches, ledger, and traces default under `~/.daari/`. Frontier prompts leave the machine only on L6 escalation.

**How do I dry-run product boundaries?**  
`boundaries.mode: warn` — classifies and annotates without refusing.

**How do I contribute?**  
[DEVELOPING.md](../../DEVELOPING.md), [AGENTS.md](https://github.com/naveenreddyalka/daari/blob/main/AGENTS.md), default pytest suite before PRs.
