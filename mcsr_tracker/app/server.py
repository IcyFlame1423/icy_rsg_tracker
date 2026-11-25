"""Local web server for the app (Python standard library only).

Serves the page in static/ and a small JSON API, and runs the Tracker in a background
thread so one program both tracks runs and shows them.

Listens on 127.0.0.1 only, and rejects requests whose Host header isn't localhost (so a
web page in the browser can't reach the API through DNS tricks).
"""

import json
import threading
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from .. import settings
from ..importer import import_records
from ..watch import Tracker, lower_priority
from . import data, player
from .textures import Textures

STATIC_DIR = Path(__file__).parent / "static"
# Explicit types: Windows' registry can map .js to text/plain, which browsers refuse
# to run as a module.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
# GET /api/<name>?instance=&window=&start=&end=&session=
DATA_ENDPOINTS = {
    "/api/summary": data.summary,
    "/api/runs": data.runs,
    "/api/sessions": data.sessions,
}
SERVER_NAME = "MCSRTracker"


class App:
    def __init__(self, cfg, track=True, out=print):
        self.cfg = cfg
        self.store = data.DataStore(cfg)
        self.textures = Textures(lambda: self.cfg)
        self.log = deque(maxlen=200)
        self._out = out
        self.tracker = Tracker(cfg, out=self.say) if track else None
        self.stop = threading.Event()
        self.started_at = datetime.now()
        self._lock = threading.Lock()  # settings/rebuild when there's no tracker

    def say(self, line):
        self.log.append(f"{datetime.now():%H:%M:%S} {line}" if not line[:2].isdigit() else line)
        self._out(line)

    def start_tracker(self):
        if not self.tracker:
            return None
        thread = threading.Thread(target=self.tracker.run, args=(self.stop,),
                                  name="tracker", daemon=True)
        thread.start()
        return thread

    # ---- Settings ----

    def save_settings(self, body):
        values = settings.parse(body)  # raises SettingsError
        lock = self.tracker.lock if self.tracker else self._lock
        with lock:
            settings.apply(self.cfg, values)
            settings.save(self.cfg)
        self.say(f"Settings saved to {self.cfg.path}")
        if self.tracker:
            self.tracker.settings_changed()
        return settings.to_json(self.cfg)

    def rebuild(self):
        if self.tracker:
            result = self.tracker.rebuild()
        else:
            with self._lock:
                if not self.cfg.records_dir.is_dir():
                    raise FileNotFoundError(f"Records folder not found: {self.cfg.records_dir}")
                result = import_records(self.cfg, rebuild=True)
        totals = {name: r.total for name, r in result.instances.items()}
        self.say("Rebuilt from the records folder: " + ", ".join(f"{n} {t} runs" for n, t in totals.items()))
        return {"runs": totals, "ignored": result.ignored}

    def status(self):
        t = self.tracker
        return {
            "tracking": t is not None,
            "version": t.version if t else 0,
            "last_import": t.last_import.isoformat(timespec="seconds") if t and t.last_import else None,
            "warning": t.warning if t else None,
            "records_dir": str(self.cfg.records_dir),
            "instances": [i.name for i in self.cfg.instances],
            "textures": self.textures.jar() is not None,  # icons can be shown
            # No instance has a Minecraft folder: deaths can't be split, no icons or player.
            "setup": None if any(i.minecraft_dir for i in self.cfg.instances) else
                     "Minecraft instance not found. Set its folder in Settings.",
        }


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = SERVER_NAME

        def log_message(self, fmt, *args):  # keep the console for tracker output
            pass

        def _send(self, status, body, content_type, cache="no-store"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(status, json.dumps(obj).encode(), "application/json")

        def _host_ok(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ALLOWED_HOSTS

        def _origin_ok(self):
            """Changes are only accepted from this app's own page: a JSON body (which a
            web page can't send cross-site without permission) and no foreign Origin."""
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in ALLOWED_HOSTS:
                return False
            return (self.headers.get("Content-Type") or "").startswith("application/json")

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 <= length <= 100_000:
                self.close_connection = True
                return self._json({"error": "request too large"}, 413)
            # Read the body before any reply: answering with unread data left in the socket
            # makes Windows reset the connection, so the client never sees the response.
            raw = self.rfile.read(length)
            if not self._host_ok() or not self._origin_ok():
                return self._send(403, b"Forbidden", "text/plain")
            try:
                body = json.loads(raw or b"null")
            except ValueError:
                return self._json({"error": "body must be JSON"}, 400)
            path = urlparse(self.path).path
            try:
                if path == "/api/settings":
                    return self._json(app.save_settings(body))
                if path == "/api/rebuild":
                    return self._json(app.rebuild())
            except settings.SettingsError as e:
                return self._json({"error": "Some settings aren't valid.", "fields": e.errors}, 400)
            except PermissionError as e:  # a CSV open in Excel
                return self._json({"error": str(e)}, 409)
            except FileNotFoundError as e:
                return self._json({"error": str(e)}, 409)
            except OSError as e:
                return self._json({"error": f"Could not save: {e}"}, 500)
            return self._json({"error": "not found"}, 404)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"Forbidden", "text/plain")
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/status":
                    return self._json(app.status())
                if url.path == "/api/settings":
                    return self._json(settings.to_json(app.cfg))
                if url.path == "/api/detect":
                    return self._json({"instances": settings.detect_instances()})
                if url.path == "/api/texture":
                    png = app.textures.get(q.get("name", ""))
                    if png is None:
                        return self._send(404, b"No such texture", "text/plain")
                    return self._send(200, png, "image/png", cache="max-age=86400")
                if url.path in ("/api/player", "/api/skin"):
                    inst = app.store.instance(q.get("instance", app.cfg.instances[0].name))
                    if url.path == "/api/player":
                        return self._json({"player": player.player(inst)})
                    png = player.skin(inst, app.cfg.instance_dir(inst))
                    if png is None:
                        return self._send(404, b"No skin", "text/plain")
                    return self._send(200, png, "image/png")
                if url.path == "/api/run":
                    return self._json(data.run_detail(
                        app.store, q.get("instance", app.cfg.instances[0].name), q.get("run_id", "")))
                if url.path in DATA_ENDPOINTS:
                    return self._json(DATA_ENDPOINTS[url.path](
                        app.store, q.get("instance", app.cfg.instances[0].name),
                        q.get("window", "last_session"), q.get("start"), q.get("end"),
                        session=q.get("session")))
                if url.path.startswith("/api/"):
                    return self._json({"error": "not found"}, 404)
                return self._static(url.path)
            except data.BadRequest as e:
                return self._json({"error": str(e)}, 400)

        def _static(self, path):
            if path == "/":
                path = "/index.html"
            file = (STATIC_DIR / path.lstrip("/")).resolve()
            # No escaping the static folder (e.g. /../../config.toml).
            if STATIC_DIR.resolve() not in file.parents or not file.is_file():
                return self._send(404, b"Not found", "text/plain")
            content_type = CONTENT_TYPES.get(file.suffix, "application/octet-stream")
            return self._send(200, file.read_bytes(), content_type)

    return Handler


class Server(ThreadingHTTPServer):
    # The default (True) sets SO_REUSEADDR, which on Windows lets a second server bind a
    # port that's already in use, and the two then split the requests between them.
    allow_reuse_address = False
    daemon_threads = True


def serve(app, port=8765, tries=10):
    """Bind to the first free port from `port` on."""
    handler = make_handler(app)
    for p in range(port, port + tries):
        try:
            return Server(("127.0.0.1", p), handler)
        except OSError:
            continue
    raise OSError(f"No free port between {port} and {port + tries - 1}")


def running_instance(port):
    """URL of an MCSR Tracker app already running on `port`, or None."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as res:
            if res.headers.get("Server", "").startswith(SERVER_NAME):
                return f"http://127.0.0.1:{port}/"
    except OSError:
        pass
    return None


def run_app(cfg, port=8765, open_browser=True, track=True):
    # Only one copy: a second one would run a second tracker writing the same CSVs.
    if url := running_instance(port):
        print(f"MCSR Tracker is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    lower_priority()  # the game always comes first
    app = App(cfg, track=track)
    httpd = serve(app, port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    app.start_tracker()
    print(f"MCSR Tracker running at {url}  (close this window or press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        app.stop.set()
        httpd.server_close()
