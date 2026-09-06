"""
Entry point for the BeerKeeper desktop app.

This does exactly three things:
  1. Points the existing backend at a proper OS data folder instead of the
     Docker-oriented /data default, and switches on single-user mode.
  2. Runs that backend (completely unmodified FastAPI app - see
     app/main.py) in a background thread, on an unused local port.
  3. Opens a native window pointed at it with pywebview.

Nothing here is desktop-specific business logic - all of that lives in
app/, shared with the self-hosted version. This file is just plumbing.
"""

import os
import socket
import sys
import threading
import time

import platformdirs

# --- 1. Data directory + mode, set BEFORE importing anything from `app` ---
#
# app.config and app.database both read their environment variables at
# import time, so this has to happen first. platformdirs picks the right
# per-OS convention on its own:
#   Windows -> C:\Users\<you>\AppData\Local\BeerKeeper\BeerKeeper
#   macOS   -> ~/Library/Application Support/BeerKeeper
#   Linux   -> ~/.local/share/BeerKeeper
DATA_DIR = platformdirs.user_data_dir("BeerKeeper", "BeerKeeper", roaming=False)
os.makedirs(DATA_DIR, exist_ok=True)
os.environ.setdefault("CELLAR_DATA_DIR", DATA_DIR)
os.environ["CELLAR_SINGLE_USER_MODE"] = "true"
# CELLAR_SECRET_KEY is intentionally left unset - app/auth.py already
# generates one on first run and persists it to DATA_DIR/.secret_key,
# which is exactly the right behavior here too.

# PyInstaller's onefile mode extracts bundled data (static/, the seed
# .txt files) to a temp folder at sys._MEIPASS and adjusts sys.path so
# `import app` finds the right copy - nothing extra needed here, but this
# makes the assumption explicit rather than accidental.
if hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)

import uvicorn  # noqa: E402
import webview  # noqa: E402


def _free_port() -> int:
    """Ask the OS for an unused local port rather than hard-coding one -
    avoids ever colliding with something else already running."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"BeerKeeper's local server didn't come up on port {port} in time.")


def main() -> None:
    from app.main import app  # imported only now, after env vars above are set

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    _wait_until_up(port)

    window = webview.create_window(
        "BeerKeeper",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=860,
        min_size=(900, 600),
    )
    # Blocks until the window is closed. gui=None lets pywebview pick the
    # right native backend itself (WebView2 on Windows, WebKit on Linux,
    # Cocoa on macOS) rather than forcing one.
    webview.start()

    # Window closed - shut the background server down cleanly rather than
    # leaving a orphaned uvicorn thread when the process exits.
    server.should_exit = True
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
