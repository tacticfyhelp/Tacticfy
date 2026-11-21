"""Builds the pre-filled GitHub "new issue" URL used by the in-app Report Bug button."""

from __future__ import annotations

import platform
from typing import List, Optional
from urllib.parse import urlencode

from src.app_logging import tail_for_report
from src.app_paths import APP_VERSION, GITHUB_ISSUES_NEW_URL, is_frozen

LOG_LINES = 20
# GitHub rejects very long query strings; keep well under its ~8 KB limit.
MAX_URL_LENGTH = 7000


def system_summary() -> str:
    release = platform.release()
    version = platform.version()
    return f"{platform.system()} {release} (build {version}), {platform.machine()}"


def build_issue_body(log_lines: List[str]) -> str:
    log_block = "\n".join(log_lines) if log_lines else "(log is empty)"
    return (
        "**Describe the bug**\n<!-- What happened, and what did you expect? -->\n\n"
        "**Steps to reproduce**\n1. \n2. \n3. \n\n"
        "**FM27 version / patch**\n<!-- e.g. 27.1.2 - Steam > FM27 > Properties > Betas -->\n\n"
        "**Environment (filled in by Tacticfy)**\n"
        f"- Tacticfy: {APP_VERSION} ({'installer' if is_frozen() else 'source'})\n"
        f"- OS: {system_summary()}\n\n"
        f"**Last {LOG_LINES} log lines** (no player or save data is logged)\n"
        f"```\n{log_block}\n```\n\n"
        "**Screenshot**\n<!-- Drag a screenshot here if it helps. -->\n"
    )


def build_issue_url(log_lines: Optional[List[str]] = None) -> str:
    """Issue URL with title, label and body pre-filled; trims the log tail if the URL gets too long."""
    lines = tail_for_report(LOG_LINES) if log_lines is None else list(log_lines)
    while True:
        query = urlencode({
            "labels": "bug",
            "title": f"[Bug] Tacticfy {APP_VERSION}: ",
            "body": build_issue_body(lines),
        })
        url = f"{GITHUB_ISSUES_NEW_URL}?{query}"
        if len(url) <= MAX_URL_LENGTH or not lines:
            return url
        lines = lines[1:]  # drop the oldest line first
