"""Local HTTP server for the Tacticfy web app (standard library only).

Security model: the server binds to 127.0.0.1 only. Because it can read fm.exe memory, it also
refuses requests a hostile web page could make from the user's browser:

* the Host header must be ``127.0.0.1:<port>`` or ``localhost:<port>`` (blocks DNS rebinding);
* every POST must be ``application/json`` and carry ``X-Tacticfy: 1`` (a cross-site page cannot
  send a custom header without a CORS preflight, which this server never approves);
* an ``Origin`` header, when present, must be this server's own origin.

Lifecycle: open pages send a heartbeat; when no page has been seen for ``idle_timeout`` seconds
(or the user clicks Quit) the server shuts itself down, so no invisible process is left behind.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

from src import app_paths, i18n
from src.bug_report import build_issue_url
from src.web.service import ApiError, TacticfyService

log = logging.getLogger("tacticfy.server")

DEFAULT_PORT = 8527
MAX_BODY_BYTES = 32 * 1024 * 1024
CLIENT_HEADER = "X-Tacticfy"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".png": "image/png", ".ico": "image/x-icon",
                ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json"}


class TacticfyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # never share the port with another process on Windows

    def __init__(self, address: Tuple[str, int], service: TacticfyService, web_root: Path,
                 idle_timeout: float = 180.0, startup_grace: float = 180.0) -> None:
        super().__init__(address, TacticfyRequestHandler)
        self.service = service
        self.web_root = Path(web_root).resolve()
        self.idle_timeout = idle_timeout
        self.startup_grace = startup_grace
        self.started_at = time.monotonic()
        self.last_seen: Optional[float] = None
        self._stopping = threading.Event()

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def allowed_hosts(self) -> set:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def request_stop(self) -> None:
        """Shut down from any thread (shutdown() must not run on the serve_forever thread)."""
        if not self._stopping.is_set():
            self._stopping.set()
            threading.Thread(target=self.shutdown, name="tacticfy-shutdown", daemon=True).start()

    def watchdog(self, interval: float = 5.0) -> None:
        """Stop when no page has checked in for a while (browser tab closed)."""
        while not self._stopping.wait(interval):
            now = time.monotonic()
            if self.last_seen is None:
                idle = now - self.started_at > self.startup_grace
            else:
                idle = now - self.last_seen > self.idle_timeout
            if idle:
                log.info("No open Tacticfy page; shutting down")
                self.request_stop()


class TacticfyRequestHandler(BaseHTTPRequestHandler):
    server: TacticfyHTTPServer
    server_version = "Tacticfy"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ plumbing
    def log_message(self, fmt: str, *args: Any) -> None:  # route access logs to app.log at debug level
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, key: str, **args: Any) -> None:
        self._json(status, {"error": {"key": key, "args": args}})

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "").lower() in self.server.allowed_hosts()

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        allowed = {f"http://{h}" for h in self.server.allowed_hosts()}
        return origin.lower() in allowed

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ApiError("dialog.import_error.title", status=413)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("web.error.title")
        if not isinstance(data, dict):
            raise ApiError("web.error.title")
        return data

    # ------------------------------------------------------------------ routing
    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._error(HTTPStatus.FORBIDDEN, "web.error.title")
            return
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self._api_get(path)
        else:
            self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok() or not self._origin_ok() or self.headers.get(CLIENT_HEADER) != "1" \
                or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._error(HTTPStatus.FORBIDDEN, "web.error.title")
            return
        path = urlparse(self.path).path
        routes: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "/api/load/live": lambda body: self.server.service.load_live(),
            "/api/load/sample": lambda body: self.server.service.load_sample(),
            "/api/import": lambda body: self.server.service.import_file(body.get("filename", ""),
                                                                        body.get("data", "")),
            "/api/settings": lambda body: self.server.service.update_settings(body),
            "/api/lock": lambda body: self.server.service.set_lock(int(body.get("player_id", -1)),
                                                                   bool(body.get("locked"))),
            "/api/calibrate": lambda body: self.server.service.calibrate(body),
            "/api/heartbeat": lambda body: {"ok": True},
            "/api/quit": self._quit,
        }
        handler = routes.get(path)
        if handler is None:
            self._error(HTTPStatus.NOT_FOUND, "web.error.title")
            return
        self.server.touch()
        try:
            self._json(HTTPStatus.OK, handler(self._read_json()))
        except ApiError as exc:
            self._error(exc.status, exc.key, **exc.args_)
        except Exception:  # noqa: BLE001 - log the traceback, return a generic error
            log.exception("API %s failed", path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "web.error.title")

    def _quit(self, _body: Dict[str, Any]) -> Dict[str, Any]:
        log.info("Quit requested from the browser")
        self.server.request_stop()
        return {"ok": True}

    def _api_get(self, path: str) -> None:
        service = self.server.service
        try:
            if path == "/api/ping":
                self._json(HTTPStatus.OK, {"app": app_paths.APP_NAME, "version": app_paths.APP_VERSION})
            elif path == "/api/meta":
                self._json(HTTPStatus.OK, service.meta())
            elif path == "/api/state":
                self.server.touch()
                self._json(HTTPStatus.OK, service.state())
            elif path.startswith("/api/i18n/"):
                lang = path.rsplit("/", 1)[-1]
                if lang not in i18n.LANGUAGES:
                    self._error(HTTPStatus.NOT_FOUND, "web.error.title")
                else:
                    self._json(HTTPStatus.OK, i18n.client_bundle(lang))
            elif path == "/api/bug-url":
                self._json(HTTPStatus.OK, {"url": build_issue_url()})
            else:
                self._error(HTTPStatus.NOT_FOUND, "web.error.title")
        except Exception:  # noqa: BLE001
            log.exception("API %s failed", path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "web.error.title")

    def _static(self, path: str) -> None:
        rel = unquote(path).lstrip("/") or "index.html"
        target = (self.server.web_root / rel).resolve()
        root = self.server.web_root
        if root not in target.parents and target != root or not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "web.error.title")
            return
        ctype = STATIC_TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] \
            or "application/octet-stream"
        extra = {}
        if target.suffix.lower() == ".html":
            extra["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            )
        self._send(HTTPStatus.OK, target.read_bytes(), ctype, extra)


def create_server(port: int = DEFAULT_PORT, service: Optional[TacticfyService] = None,
                  web_root: Optional[Path] = None, **kwargs: Any) -> TacticfyHTTPServer:
    """Bind on 127.0.0.1:``port`` (``0`` = any free port)."""
    return TacticfyHTTPServer(
        ("127.0.0.1", port),
        service or TacticfyService(),
        web_root or app_paths.resource_path("web"),
        **kwargs,
    )
