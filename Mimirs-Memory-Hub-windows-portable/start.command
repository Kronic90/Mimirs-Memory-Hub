#!/bin/bash
# ============================================================
#  Mimir's Memory Hub — macOS double-click launcher
#  This file can be double-clicked from Finder.
#  It ensures run.sh is executable and then launches it.
# ============================================================
DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$DIR/run.sh"
"$DIR/run.sh"
