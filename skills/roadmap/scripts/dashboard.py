"""Local live progress dashboard for the roadmap CLI.

Kept out of roadmap.py so that module stays focused on the CLI/data layer. This
one owns the HTTP server, SSE stream, and JSON endpoints. It never imports
roadmap at module load — the roadmap module is passed in as `rm`, which both
avoids an import cycle and keeps the data layer the single source of truth.
"""
from __future__ import annotations
import hashlib
import http.server
import json
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_PORT = 4700
PORT_SPAN = 40


def _dashboard_html() -> str:
    return (Path(__file__).resolve().parent / "dashboard.html").read_text(
        encoding="utf-8")


def _status_line(st: dict) -> str:
    items = st.get("items", [])
    td = sum(i.get("done", 0) for i in items)
    tt = sum(i.get("total", 0) for i in items)
    pct = round(100 * td / tt) if tt else 0
    active = sum(1 for i in items if i.get("status") == "active")
    ver = st.get("currentVersion") or "?"
    nvers = len({i.get("version") for i in items})
    return (f"current v{ver} · {pct}% ({td}/{tt}) · {active} active"
            f" · {nvers} version{'s' if nvers != 1 else ''}")


def _roadmap_signature(rm, root: Path):
    """Cheap change token: newest mtime across .roadmap/ and ROADMAP.md."""
    latest = 0.0
    try:
        for f in rm.roadmap_dir(root).rglob("*"):
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass
        md = root / "ROADMAP.md"
        if md.exists():
            latest = max(latest, md.stat().st_mtime)
    except OSError:
        pass
    return latest


def _safe_status(rm, root: Path) -> dict:
    try:
        return rm.status(root)
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"project": None, "currentVersion": None, "items": [],
                "error": str(e)}


def _item_detail(rm, root: Path, item_id: int) -> dict:
    """Full detail for one item: its plan checklist steps + note. Fetched lazily
    by the dashboard when a row is expanded, so status payloads stay small."""
    try:
        cfg = rm.read_config(root)
        item = next((i for i in cfg["items"] if i["id"] == item_id), None)
        if item is None:
            return {"error": f"no item #{item_id}"}
        pp = rm.roadmap_dir(root) / item["file"]
        plan = rm.parse_plan(pp) if pp.exists() else {"steps": [], "meta": {}}
        return {"id": item_id, "title": item["title"], "type": item["type"],
                "version": item["version"], "note": item.get("note"),
                "file": item["file"],
                "steps": [{"done": d, "text": t} for d, t in plan["steps"]]}
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"error": str(e)}


def _project_port(root: Path) -> int:
    """Stable preferred port derived from the project path, so the same project
    always maps to the same port (one dashboard per project) while different
    projects land on different ports and coexist."""
    h = hashlib.md5(str(root.resolve()).encode("utf-8")).hexdigest()
    return DEFAULT_PORT + int(h, 16) % PORT_SPAN


def _running_dashboard(root: Path, port: int):
    """Return the URL if a dashboard for THIS project is already serving on
    `port`, else None. Matched via the X-Roadmap-Root response header."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
        with urllib.request.urlopen(req, timeout=0.4) as r:
            if r.headers.get("X-Roadmap-Root") == str(root.resolve()):
                return f"http://127.0.0.1:{port}"
    except Exception:
        return None
    return None


def serve(rm, root: Path, port: int | None = None,
          open_browser: bool = True) -> int:
    """Run a local, read-only web dashboard that pushes live updates via SSE.

    One dashboard per project: port=None derives a stable port from the project
    path. If this project is already being served (in another terminal), point
    at that instance instead of starting a duplicate. Different projects get
    different ports and run side by side. An explicit port is honored strictly.
    """
    if not rm.roadmap_dir(root).exists():
        print("No .roadmap/ here — run `roadmap init` first, then `roadmap serve`.")
        return 0

    root_id = str(root.resolve())
    dashboard_html = _dashboard_html()

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            self.wfile.write(body)

        def _sse(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            last_sig = None
            try:
                while True:
                    sig = _roadmap_signature(rm, root)
                    if sig != last_sig:
                        last_sig = sig
                        data = "data: " + json.dumps(_safe_status(rm, root)) + "\n\n"
                        self.wfile.write(data.encode("utf-8"))
                    else:
                        self.wfile.write(b": ping\n\n")   # keepalive / disconnect probe
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, dashboard_html.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/events":
                self._sse()
            elif path == "/api/status":
                self._send(200, json.dumps(_safe_status(rm, root)).encode("utf-8"),
                           "application/json")
            elif path == "/api/item":
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                iid = None
                for pair in query.split("&"):
                    k, _, v = pair.partition("=")
                    if k == "id" and v.isdigit():
                        iid = int(v)
                payload = ({"error": "missing id"} if iid is None
                           else _item_detail(rm, root, iid))
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            elif path == "/api/changelog":
                try:
                    payload = rm.changelog_json(root)
                except (ValueError, FileNotFoundError, OSError) as e:
                    payload = {"error": str(e)}
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:  # silence per-request logging
            pass

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True   # worker threads die with the process

        def handle_error(self, request, client_address) -> None:
            # A browser closing an SSE stream resets the socket — that is normal,
            # not an error. Swallow it instead of dumping a traceback.
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError)):
                return
            super().handle_error(request, client_address)

    if port is None:
        preferred = _project_port(root)
        # Already serving THIS project in another terminal? Point at it, don't
        # start a duplicate. Scan the span in case it landed on a fallback port.
        for candidate in range(preferred, preferred + PORT_SPAN):
            existing = _running_dashboard(root, candidate)
            if existing:
                print(f"This project is already being served → {existing}"
                      "  (one dashboard per project)")
                if open_browser:
                    try:
                        webbrowser.open(existing)
                    except Exception:
                        pass
                return 0
        # Bind the project's stable port; if taken by something else, scan up.
        httpd = None
        for candidate in range(preferred, preferred + PORT_SPAN):
            try:
                httpd = Server(("127.0.0.1", candidate), Handler)
                break
            except OSError:
                continue
        if httpd is None:
            print(f"Error: no free port in {preferred}-{preferred + PORT_SPAN - 1} "
                  "(too many dashboards running?)", file=sys.stderr)
            return 1
    else:
        try:
            httpd = Server(("127.0.0.1", port), Handler)
        except OSError as e:
            print(f"Error: cannot bind 127.0.0.1:{port} — {e}", file=sys.stderr)
            return 1
    port = httpd.server_address[1]

    # Mirror live progress into the terminal running `serve`.
    def watch_terminal() -> None:
        last = _roadmap_signature(rm, root)
        while True:
            time.sleep(1)
            sig = _roadmap_signature(rm, root)
            if sig != last:
                last = sig
                print(f"  ↻ {_status_line(_safe_status(rm, root))}", flush=True)

    threading.Thread(target=watch_terminal, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    print(f"roadmap dashboard → {url}  (Ctrl-C to stop)")
    print(f"  {_status_line(_safe_status(rm, root))}", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0
