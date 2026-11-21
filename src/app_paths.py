"""Application identity, bundled-resource lookup and writable runtime locations.

Two run modes are supported:

* Source checkout (``run.bat`` / ``python main.py``): resources come from the project root and
  writable files (logs, calibrated offset overrides) stay inside the checkout (git-ignored).
* Frozen build (PyInstaller, installed under ``Program Files``): read-only resources come from
  ``sys._MEIPASS`` and every writable file goes to ``%LOCALAPPDATA%\\Tacticfy\\``.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

APP_NAME = "Tacticfy"
APP_VERSION = "1.0.1"
APP_ID = "Tacticfy.Tacticfy.Desktop"  # Windows AppUserModelID (taskbar icon grouping)
GITHUB_REPO_URL = "https://github.com/tacticfyhelp/Tacticfy"
GITHUB_ISSUES_NEW_URL = f"{GITHUB_REPO_URL}/issues/new"
ICON_RELATIVE_PATH = ("assets", "Tacticfy.ico")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Directory holding the read-only bundled resources (``config/``, ``assets/``)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _PROJECT_ROOT


def resource_path(*parts: str) -> Path:
    """Absolute path of a bundled, read-only resource, e.g. ``resource_path("config", "formations.json")``."""
    return bundle_root().joinpath(*parts)


def icon_path() -> Path:
    return resource_path(*ICON_RELATIVE_PATH)


def user_data_dir() -> Path:
    """Writable per-user directory (created on demand).

    Frozen: ``%LOCALAPPDATA%\\Tacticfy``. Source checkout: the project root, so a developer's
    logs and overrides stay next to the code (both are git-ignored).
    """
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME
    else:
        path = _PROJECT_ROOT
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return log_dir() / "app.log"


def bundled_offsets_path() -> Path:
    """Offsets shipped with this release (read-only when installed)."""
    return resource_path("config", "offsets.json")


def user_offsets_path() -> Path:
    """User-calibrated offsets overlay, merged on top of the bundled offsets.json."""
    if is_frozen():
        return user_data_dir() / "offsets.json"
    return _PROJECT_ROOT / "config" / "offsets.user.json"
