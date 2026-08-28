# daari first-run for Windows — WSL2 only.
# This script does not install a native Windows daemon.
$ErrorActionPreference = "Stop"

function Install-InsideWsl {
    Write-Host "Installing daari inside WSL, then running onboard..."
    python3 -m pip install --user daari
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    daari onboard --yes
    exit $LASTEXITCODE
}

if ($env:WSL_DISTRO_NAME) {
    Write-Host "Detected WSL distro: $env:WSL_DISTRO_NAME"
    Install-InsideWsl
}

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    Write-Error @"
WSL2 is required. Native Windows Ollama + daari is not a supported first-run.
This script does not install a native Windows daemon.
Install WSL2 (PowerShell as admin):  wsl --install
Then re-run this script, or inside WSL:
  pip install daari
  daari onboard --yes
See docs/developer/get-started/install-windows.md
"@
    exit 1
}

Write-Host "Delegating to WSL (does not install a native Windows daemon)..."
& wsl.exe -e bash -lc "set -euo pipefail; python3 -m pip install --user daari && daari onboard --yes"
exit $LASTEXITCODE
