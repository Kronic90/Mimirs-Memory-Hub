@echo off
setlocal
title Mimir's Memory Hub

set "ROOT_DIR=%~dp0"
set "PYTHON_DIR=%ROOT_DIR%python_embeded"

:: ── First-time setup if needed ───────────────────────────────────────
if not exist "%PYTHON_DIR%\python.exe" (
    echo First-time setup required - launching installer...
    echo.
    call "%ROOT_DIR%install.bat"
    if %errorlevel% neq 0 exit /b 1
)

:: ── Launch app ───────────────────────────────────────────────────────
echo  ============================================================
echo   Mimir's Memory Hub
echo   Starting at http://127.0.0.1:19009
echo   Press Ctrl+C to stop.
echo  ============================================================
echo.

cd /d "%ROOT_DIR%"
"%PYTHON_DIR%\python.exe" -m playground

:: If Python exits with an error, keep the window open so the user can read it
if %errorlevel% neq 0 (
    echo.
    echo  Mimir exited with an error (code %errorlevel%).
    echo  Check the output above for details.
    pause
)
