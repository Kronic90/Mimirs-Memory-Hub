@echo off
setlocal enabledelayedexpansion
title Mimir's Memory Hub - Setup

echo.
echo  ============================================================
echo   Mimir's Memory Hub - First Time Setup
echo  ============================================================
echo.

set "ROOT_DIR=%~dp0"
set "PYTHON_DIR=%ROOT_DIR%python_embeded"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"

:: ── Step 1: Download + extract embedded Python ──────────────────────

if exist "%PYTHON_DIR%\python.exe" (
    echo [OK] Python already installed - skipping download.
    goto :install_packages
)

echo [1/3] Downloading Python %PYTHON_VERSION% (embedded, ~15 MB)...
powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%ROOT_DIR%_python_embed.zip' -UseBasicParsing"

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Could not download Python. Check your internet connection.
    pause
    exit /b 1
)

echo [2/3] Extracting Python...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%ROOT_DIR%_python_embed.zip' -DestinationPath '%PYTHON_DIR%' -Force"
del "%ROOT_DIR%_python_embed.zip"

:: Enable site-packages (required for pip to work in embedded Python)
for %%f in ("%PYTHON_DIR%\python*._pth") do (
    echo import site>> "%%f"
)

:: Install pip into embedded Python
echo [3/3] Installing pip...
powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%ROOT_DIR%_get-pip.py' -UseBasicParsing"
"%PYTHON_DIR%\python.exe" "%ROOT_DIR%_get-pip.py" --quiet
del "%ROOT_DIR%_get-pip.py"

:: ── Step 2: Install Python packages ──────────────────────────────────

:install_packages
echo.
echo Installing packages (this may take a few minutes on first run)...
echo.
"%PYTHON_DIR%\python.exe" -m pip install -r "%ROOT_DIR%requirements.txt" --quiet --disable-pip-version-check

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Try running this file again, or check your internet connection.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   Setup complete!  Run  run.bat  to start.
echo  ============================================================
echo.
pause
