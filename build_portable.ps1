# ============================================================
#  build_portable.ps1
#  Builds a self-contained Windows portable release of
#  Mimir's Memory Hub — no Python install required.
#
#  Output: Mimirs-Memory-Hub-windows-portable.zip
#
#  Usage:
#    .\build_portable.ps1
#    .\build_portable.ps1 -PythonVersion 3.11.9
# ============================================================
param(
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"

$ROOT        = Split-Path -Parent $MyInvocation.MyCommand.Path
$BUILD_DIR   = "$ROOT\_build_portable"
$PYTHON_DIR  = "$BUILD_DIR\python_embeded"
$PYTHON_URL  = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$OUTPUT_ZIP  = "$ROOT\Mimirs-Memory-Hub-windows-portable.zip"

Write-Host ""
Write-Host " ============================================================" -ForegroundColor Cyan
Write-Host "  Mimir's Memory Hub - Portable Windows Release Builder" -ForegroundColor Cyan
Write-Host " ============================================================" -ForegroundColor Cyan
Write-Host ""

# Clean previous build
if (Test-Path $BUILD_DIR) {
    Write-Host " Cleaning previous build..."
    Remove-Item $BUILD_DIR -Recurse -Force
}
New-Item -ItemType Directory -Path $BUILD_DIR | Out-Null

# ── Step 1: Download embedded Python ─────────────────────────────────
Write-Host " [1/5] Downloading Python $PythonVersion (embedded)..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $PYTHON_URL -OutFile "$BUILD_DIR\_python.zip" -UseBasicParsing
Expand-Archive -Path "$BUILD_DIR\_python.zip" -DestinationPath $PYTHON_DIR -Force
Remove-Item "$BUILD_DIR\_python.zip"

# Enable site-packages and add app root to embedded Python's path
$pthFile = Get-ChildItem -Path $PYTHON_DIR -Filter "python*._pth" | Select-Object -First 1
if ($pthFile) {
    # '.' = python_embeded dir, '..' = app root (where Mimir.py and playground/ live)
    Add-Content -Path $pthFile.FullName -Value "`n..`nimport site"
    Write-Host "   Patched $($pthFile.Name) to enable site-packages and app root."
} else {
    Write-Warning "Could not find python*._pth - site-packages may not load."
}

# ── Step 2: Install pip ───────────────────────────────────────────────
Write-Host " [2/5] Installing pip into embedded Python..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$BUILD_DIR\_get-pip.py" -UseBasicParsing
& "$PYTHON_DIR\python.exe" "$BUILD_DIR\_get-pip.py" --quiet
Remove-Item "$BUILD_DIR\_get-pip.py"

# ── Step 3: Install packages ──────────────────────────────────────────
Write-Host " [3/5] Installing packages (this takes a few minutes)..." -ForegroundColor Yellow
& "$PYTHON_DIR\python.exe" -m pip install -r "$ROOT\requirements.txt" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-Error "Package installation failed."
    exit 1
}

# ── Step 4: Copy app files ────────────────────────────────────────────
Write-Host " [4/5] Copying application files..." -ForegroundColor Yellow
Copy-Item -Path "$ROOT\playground"       -Destination "$BUILD_DIR\playground"       -Recurse
Copy-Item -Path "$ROOT\Mimir.py"         -Destination "$BUILD_DIR\Mimir.py"
Copy-Item -Path "$ROOT\run.bat"          -Destination "$BUILD_DIR\run.bat"
Copy-Item -Path "$ROOT\run.sh"           -Destination "$BUILD_DIR\run.sh"
Copy-Item -Path "$ROOT\start.command"    -Destination "$BUILD_DIR\start.command"
Copy-Item -Path "$ROOT\requirements.txt" -Destination "$BUILD_DIR\requirements.txt"
Copy-Item -Path "$ROOT\README.md"        -Destination "$BUILD_DIR\README.md"

# Empty data directory (users get a fresh start)
New-Item -ItemType Directory -Path "$BUILD_DIR\playground_data" | Out-Null
New-Item -ItemType Directory -Path "$BUILD_DIR\playground_data\models" | Out-Null

# ── Step 5: Zip it up ────────────────────────────────────────────────
Write-Host " [5/5] Creating release zip..." -ForegroundColor Yellow
if (Test-Path $OUTPUT_ZIP) { Remove-Item $OUTPUT_ZIP }
Compress-Archive -Path "$BUILD_DIR\*" -DestinationPath $OUTPUT_ZIP

$sizeMB = [math]::Round((Get-Item $OUTPUT_ZIP).Length / 1MB, 1)

Write-Host ""
Write-Host " ============================================================" -ForegroundColor Green
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host "  Output : $OUTPUT_ZIP" -ForegroundColor Green
Write-Host "  Size   : $sizeMB MB" -ForegroundColor Green
Write-Host " ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host " Users just need to:" -ForegroundColor White
Write-Host "   1. Unzip  Mimirs-Memory-Hub-windows-portable.zip" -ForegroundColor White
Write-Host "   2. Double-click  run.bat" -ForegroundColor White
Write-Host "   3. Done." -ForegroundColor White
Write-Host ""
