"""Entry point for Tacticfy: starts the local web server and opens the UI in the default browser.

Usage:  python main.py [--port 8527] [--no-browser]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from typing import Optional
import urllib.error
import urllib.request
import webbrowser

from src import app_paths
from src.app_logging import setup_logging

log = logging.getLogger("tacticfy")


def running_instance(port: int) -> Optional[str]:
    """URL of a Tacticfy server already listening on ``port``, if any."""
    url = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{url}/api/ping", timeout=1.5) as resp:
            if json.load(resp).get("app") == app_paths.APP_NAME:
                return url
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return None


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Tacticfy - FM27 tactics in your browser")
    parser.add_argument("--port", type=int, default=None, help="port to listen on (default 8527)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args(argv)

    setup_logging()
    from src.web.server import DEFAULT_PORT, create_server  # after logging, so import errors reach app.log

    port = args.port or DEFAULT_PORT
    existing = running_instance(port)
    if existing:
        # Second launch (e.g. Start Menu clicked again): just bring up the running app.
        log.info("Tacticfy is already running at %s; opening it", existing)
        if not args.no_browser:
            webbrowser.open(existing)
        return 0

    try:
        server = create_server(port)
    except OSError:
        log.warning("Port %d is in use by another program; using a free port", port)
        server = create_server(0)

    url = server.origin + "/"
    log.info("Serving Tacticfy at %s", url)
    if sys.stdout is not None:  # the windowed .exe has no console
        print(f"Tacticfy is running at {url}  (close the browser tab or click Quit to stop)", flush=True)
    threading.Thread(target=server.watchdog, name="tacticfy-watchdog", daemon=True).start()
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log.info("Tacticfy stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
