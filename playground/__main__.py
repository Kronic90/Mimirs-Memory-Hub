"""Launch Mimir's Well server."""
import sys
import webbrowser
import threading
from pathlib import Path

# Ensure playground + Mimir are importable regardless of how this is launched
_mimir_root = str(Path(__file__).resolve().parent.parent)
if _mimir_root not in sys.path:
    sys.path.insert(0, _mimir_root)

import os
if _mimir_root not in os.environ.get("PYTHONPATH", ""):
    os.environ["PYTHONPATH"] = _mimir_root + os.pathsep + os.environ.get("PYTHONPATH", "")

def main():
    import uvicorn

    host = "127.0.0.1"
    port = 19009

    def _open_browser():
        import time
        time.sleep(1.8)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    print()
    print("  +======================================+")
    print("  |         Mimir's Well v0.1.0          |")
    print(f"  |   http://{host}:{port}          |")
    print("  +======================================+")
    print()

    uvicorn.run(
        "playground.server:app",
        host=host,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
