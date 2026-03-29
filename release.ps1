# ============================================================
#  release.ps1
#  Builds the portable zip and creates/updates a GitHub release.
#
#  First-time only: run  gh auth login  in a terminal, then run this.
#
#  Usage:
#    .\release.ps1               # creates v1.0.0
#    .\release.ps1 -Tag v1.2.0   # creates a specific tag
#    .\release.ps1 -Tag v1.2.0 -Title "My Release"
# ============================================================
param(
    [string]$Tag   = "v1.0.0",
    [string]$Title = "Mimir's Memory Hub $Tag"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Verify gh is authenticated ────────────────────────────────────────
Write-Host ""
$authCheck = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " gh CLI is not authenticated." -ForegroundColor Red
    Write-Host " Run this first, then try again:" -ForegroundColor Yellow
    Write-Host "   gh auth login" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}
Write-Host " gh authenticated." -ForegroundColor Green

# ── Build the portable zip ────────────────────────────────────────────
Write-Host ""
Write-Host " Building portable zip..." -ForegroundColor Yellow
& "$ROOT\build_portable.ps1"

$ZIP = "$ROOT\Mimirs-Memory-Hub-windows-portable.zip"
if (-not (Test-Path $ZIP)) {
    Write-Error "Zip not found after build: $ZIP"
    exit 1
}

# ── Create/update GitHub release ─────────────────────────────────────
Write-Host ""
Write-Host " Publishing release $Tag to GitHub..." -ForegroundColor Yellow

# Delete existing release + tag if they exist (allows re-running)
gh release delete $Tag --yes 2>$null
git tag -d $Tag 2>$null
git push hub --delete $Tag 2>$null

$Notes = @"
## Download & Run (Windows — no Python required)

1. Download **Mimirs-Memory-Hub-windows-portable.zip** below
2. Unzip anywhere
3. Double-click **run.bat**
4. Browser opens automatically at http://127.0.0.1:19009

### First run
The app downloads a small (~15 MB) embedded Python and installs packages once.
After that, launching is instant.

### Requirements
- Windows 10 / 11
- Internet connection (first run only, for setup and for cloud LLM APIs)
- [Ollama](https://ollama.com) if you want free local AI (recommended)

---

**macOS / Linux:** clone the repo and run ``./start.command`` (macOS) or ``chmod +x run.sh && ./run.sh`` (Linux).
"@

gh release create $Tag $ZIP `
    --repo "Kronic90/Mimirs-Memory-Hub" `
    --title $Title `
    --notes $Notes `
    --latest

Write-Host ""
Write-Host " ============================================================" -ForegroundColor Green
Write-Host "  Release $Tag published!" -ForegroundColor Green
Write-Host "  https://github.com/Kronic90/Mimirs-Memory-Hub/releases/tag/$Tag" -ForegroundColor Green
Write-Host " ============================================================" -ForegroundColor Green
Write-Host ""
