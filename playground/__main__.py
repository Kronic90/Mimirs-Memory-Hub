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
    # MIMIR_PORT lets an in-app restart come back on the same port
    try:
        port = int(os.environ.get("MIMIR_PORT", "") or 19009)
    except ValueError:
        port = 19009
    os.environ["MIMIR_PORT"] = str(port)

    # Data brought over from an older copy is swapped in here, before
    # anything has loaded (or could overwrite) memories.
    from playground.updater import apply_pending_data_import
    note = apply_pending_data_import()
    if note:
        print("  " + note)

    def _open_browser():
        # Open the page only once the hub is answering -- opening it on a
        # timer showed a half-loaded page (no characters, no memories) on
        # slower starts.
        import socket, time
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        time.sleep(0.5)
        webbrowser.open(f"http://{host}:{port}")

    # After an in-app restart the page that's already open reconnects itself
    if not os.environ.pop("MIMIR_NO_BROWSER", ""):
        threading.Thread(target=_open_browser, daemon=True).start()

    from playground.version import __version__
    title = f"Mimir's Well v{__version__}"
    print()
    print("  +======================================+")
    print(f"  |{title:^38}|")
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
