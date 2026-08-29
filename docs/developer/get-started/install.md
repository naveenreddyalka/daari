# Install

**Outcome:** daari CLI available and ready to `daari serve`.

## Option A — Docker Compose (recommended)

Bundles Ollama + model pull + daari:

```bash
git clone https://github.com/naveenreddyalka/daari.git
cd daari
docker compose up
```

Daemon: `http://127.0.0.1:11435`. Readiness: `GET /ready`. Image: `ghcr.io/naveenreddyalka/daari`.

Optional profiles:

```bash
docker compose --profile org up          # org-cache on :11436
docker compose --profile backends up -d  # Redis + Postgres
```

## Option B — from source

```bash
git clone https://github.com/naveenreddyalka/daari.git && cd daari
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# optional extras: pip install -e ".[redis,postgres,oidc,otel]"
ollama pull llama3.2:3b
daari serve
```

## Option C — Homebrew (macOS/Linux)

```bash
brew tap naveenreddyalka/daari
brew trust naveenreddyalka/daari
brew install daari
daari onboard --yes --serve
```

`brew trust` is not optional — Homebrew 6 refuses to load formulae from
third-party taps until you trust them explicitly. The formula compiles the Rust
extensions in `pydantic-core` and `watchfiles`, so the first install pulls the
Rust toolchain and takes a few minutes.

Tap: [naveenreddyalka/homebrew-daari](https://github.com/naveenreddyalka/homebrew-daari).

## Option D — pip

```bash
pip install daari
daari onboard --yes --serve
```

`daari onboard` probes Ollama (prints https://ollama.com/download if it is down), pulls L3 + the L1 embed model when missing, and runs `daari doctor`. `--serve` starts the daemon in the background (`http://127.0.0.1:11435/v1`). `--minimal` pulls L3 only. `daari install` does the same when `scripts/install.sh` is not on disk (pip/brew). In a git clone it still runs the source installer (venv + editable install) and now also pulls `nomic-embed-text` unless `MINIMAL=1`. With L1 on, `daari doctor` fails if the embed model is missing.

Package: [pypi.org/project/daari](https://pypi.org/project/daari/) (`daari==1.2.0`).

## Option E — Windows / WSL2

Native Windows is **not** a supported first-run. Use WSL2:

→ [install-windows.md](install-windows.md)

```powershell
wsl --install
# then inside WSL, or:
.\scripts\install.ps1
```

## Verify

```bash
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:11435/ready
daari doctor
```

## Stay up without Docker

`daari serve` in a terminal dies on logout. For a user-level stay-up path (no root):

```bash
daari service install --now
daari service status
```

`--now` writes the unit and enables/starts it (`systemctl --user enable --now daari.service` on Linux, `launchctl load -w` on macOS). Without `--now` the file is written and the command prints the enable hint for you to run yourself.

Logs: `~/.daari/serve.log`. `daari service uninstall` removes only the file this command created; `daari service uninstall --now` stops and disables it first. Native Windows is not supported — use WSL2.

## Cursor over a tunnel

```bash
daari setup cursor --tunnel --yes --daemonize
```

Starts `daari serve` if needed, opens a Cloudflare quick tunnel, and writes the public base URL into Cursor. Requires `cloudflared` (`brew install cloudflared`).

## Next

→ [Quickstart](quickstart.md) · [First client](first-client.md)
