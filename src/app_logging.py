"""File logging plus a privacy-scrubbed log tail for GitHub bug reports.

Log lines must never contain player names, attributes or save details: the app logs only event
types, counts and error messages. ``tail_for_report`` additionally replaces the user's home
directory and account name so local paths do not leak into a public issue.
"""

from __future__ import annotations

import getpass
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
from typing import List, Optional

from src.app_paths import APP_NAME, APP_VERSION, is_frozen, log_file

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO) -> Path:
    """Attach a rotating ``app.log`` handler to the root logger (idempotent); return the log path."""
    global _configured
    path = log_file()
    if _configured:
        return path
    root = logging.getLogger()
    root.setLevel(level)
    try:
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)  # read-only location: still log somewhere
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    _configured = True
    logging.getLogger("tacticfy").info(
        "%s %s starting (%s, Python %s)", APP_NAME, APP_VERSION,
        "installed build" if is_frozen() else "source checkout", sys.version.split()[0],
    )
    sys.excepthook = _log_uncaught
    return path


def _log_uncaught(exc_type, exc, tb) -> None:
    logging.getLogger("tacticfy").critical("Uncaught exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


def _private_tokens() -> List[str]:
    tokens = [str(Path.home())]
    try:
        tokens.append(getpass.getuser())
    except Exception:  # noqa: BLE001 - getuser can fail on odd environments
        pass
    tokens.append(os.environ.get("COMPUTERNAME", ""))
    return [t for t in tokens if t and len(t) > 2]


def scrub(text: str, tokens: Optional[List[str]] = None) -> str:
    """Replace home path, account name and machine name with placeholders."""
    for token in sorted(tokens if tokens is not None else _private_tokens(), key=len, reverse=True):
        placeholder = "~" if os.sep in token or "/" in token else "<user>"
        text = re.sub(re.escape(token), placeholder, text, flags=re.IGNORECASE)
        # Also catch the forward-slash spelling of Windows paths.
        text = re.sub(re.escape(token.replace("\\", "/")), placeholder, text, flags=re.IGNORECASE)
    return text


def tail_for_report(lines: int = 20, path: Optional[Path] = None) -> List[str]:
    """Last ``lines`` lines of the log, scrubbed of local identifiers."""
    path = path or log_file()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            tail = handle.read().splitlines()[-lines:]
    except OSError:
        return []
    tokens = _private_tokens()
    return [scrub(line, tokens) for line in tail]
