# Install on Windows

**Native Windows Ollama + daari is not a supported first-run.** The honest path is WSL2. This is not one-click native Windows.

## WSL2 (supported)

1. Install WSL2 if you do not have it:

   ```powershell
   wsl --install
   ```

   Reboot if Windows asks, then open Ubuntu (or your distro).

2. Inside WSL:

   ```bash
   pip install daari
   daari onboard --yes --serve
   ```

   Or from PowerShell, run the helper (it only talks to WSL):

   ```powershell
   .\scripts\install.ps1
   ```

`daari onboard` probes Ollama inside WSL, pulls L3 + the L1 embed model, and runs doctor. Install Ollama **in the WSL distro** (or use the Docker path below). Do not expect a native-Windows daemon.

## Docker Desktop

`docker compose up` from a clone also works if Docker Desktop is set to use the WSL2 backend. Same ports as [install.md](install.md) Option A.

## What we will not claim

- One-click native-Windows Ollama
- `daari service install` on native Windows (it refuses; use WSL — issue #261 / #260)

## Next

→ [Install](install.md) · [Quickstart](quickstart.md)
