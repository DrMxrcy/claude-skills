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
import subprocess
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


def _discover_roots(rm, root: Path) -> list[tuple[Path, str | None]]:
    """All git checkouts of this repo (main + linked worktrees) that have a
    `.roadmap/`, as (path, branch) with the main checkout first. Outside git,
    or on any git failure, falls back to just [(root, None)].
    """
    roots: list[tuple[Path, str | None]] = []
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            path: Path | None = None
            branch: str | None = None
            entries: list[tuple[Path, str | None]] = []
            for line in out.stdout.splitlines() + [""]:
                if line.startswith("worktree "):
                    path, branch = Path(line[len("worktree "):]), None
                elif line.startswith("branch "):
                    branch = line[len("branch "):].removeprefix("refs/heads/")
                elif not line.strip() and path is not None:
                    entries.append((path, branch))
                    path = None
            # git lists the main checkout first; keep that order.
            roots = [(p.resolve(), b) for p, b in entries
                     if rm.roadmap_dir(p).exists()]
    except (OSError, subprocess.SubprocessError):
        pass
    cur = root.resolve()
    if not any(p == cur for p, _ in roots):
        roots.insert(0, (cur, None))
    return roots


def _merge_status(statuses: list[dict], roots_meta: list[dict]) -> dict:
    """Merge per-checkout status payloads into one 'all worktrees' view: items
    merged by id, the copy with the most steps done wins and is tagged with the
    branch it lives on; currentVersion is the highest across checkouts.
    ponytail: same id with different meaning across branches → most-progressed
    copy wins; per-branch views remain in the dropdown for the exact picture.
    """
    items: dict[int, dict] = {}
    for i, st in enumerate(statuses):
        branch = roots_meta[i].get("branch") or roots_meta[i]["name"]
        for it in st.get("items", []):
            cand = {**it, "_root": i, "branch": branch}
            cur = items.get(it["id"])
            if cur is None or ((cand.get("done", 0), cand.get("pct", 0))
                               > (cur.get("done", 0), cur.get("pct", 0))):
                items[it["id"]] = cand
    def vkey(v):
        return [int(x) if x.isdigit() else 0 for x in str(v).split(".")]
    vers = [st["currentVersion"] for st in statuses if st.get("currentVersion")]
    return {"project": next((st.get("project") for st in statuses
                             if st.get("project")), None),
            "currentVersion": max(vers, key=vkey) if vers else None,
            "items": sorted(items.values(), key=lambda x: x["id"])}


class _CombinedBroadcaster:
    """Same snapshot()/wait() surface as _Broadcaster, but derives its payload
    by merging every per-root broadcaster and wakes when any of them does."""

    def __init__(self, bcasts: list, roots_meta: list[dict]):
        self.bcasts, self.meta = bcasts, roots_meta
        self.label = "[all] "
        self.cond = threading.Condition()
        self.version = 0
        self._child_vers = [b.snapshot()[0] for b in bcasts]
        self.json = self._dump()

    def _dump(self) -> str:
        stats = [json.loads(b.snapshot()[1]) for b in self.bcasts]
        return json.dumps({**_merge_status(stats, self.meta),
                           "_root": "all", "_roots": self.meta})

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            time.sleep(1)
            vers = [b.snapshot()[0] for b in self.bcasts]
            if vers == self._child_vers:
                continue
            self._child_vers = vers
            snap = self._dump()
            with self.cond:
                self.json = snap
                self.version += 1
                self.cond.notify_all()

    def snapshot(self):
        with self.cond:
            return self.version, self.json

    def wait(self, last_version: int, timeout: float):
        with self.cond:
            if self.version == last_version:
                self.cond.wait(timeout)
            return self.version, self.json


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


class _Broadcaster:
    """Single background watcher shared by every SSE client and the terminal.

    Scans the roadmap change-signature once per second total (not once per
    client), recomputes the status snapshot only when it actually changes, and
    wakes all waiting clients. Clients block on the condition instead of each
    polling the filesystem, so N open tabs cost the same as one.
    """

    def __init__(self, rm, root: Path, extra: dict | None = None,
                 label: str = ""):
        self.rm, self.root = rm, root
        self.extra = extra or {}   # merged into every payload (worktree info)
        self.label = label         # terminal prefix when serving several roots
        self.cond = threading.Condition()
        self.version = 0
        self.json = self._dump()
        self._sig = _roadmap_signature(rm, root)

    def _dump(self) -> str:
        return json.dumps({**_safe_status(self.rm, self.root), **self.extra})

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            time.sleep(1)
            sig = _roadmap_signature(self.rm, self.root)
            if sig == self._sig:
                continue
            self._sig = sig
            snap = self._dump()
            with self.cond:
                self.json = snap
                self.version += 1
                self.cond.notify_all()
            print(f"  ↻ {self.label}{_status_line(json.loads(snap))}",
                  flush=True)

    def snapshot(self):
        with self.cond:
            return self.version, self.json

    def wait(self, last_version: int, timeout: float):
        with self.cond:
            if self.version == last_version:
                self.cond.wait(timeout)
            return self.version, self.json


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

    # One instance serves the main checkout AND every linked git worktree that
    # has a .roadmap/. Port + dedupe key on the primary (main-checkout) root, so
    # `roadmap serve` from any checkout converges on the same dashboard.
    # ponytail: roots snapshot at startup — restart serve to pick up new worktrees.
    roots = _discover_roots(rm, root)
    roots_meta = [{"path": str(p), "branch": b, "name": p.name}
                  for p, b in roots]
    primary = roots[0][0]
    root_id = str(primary)
    dashboard_html = _dashboard_html()
    bcasts: list[_Broadcaster] = []
    combined: _CombinedBroadcaster | None = None

    def _root_ix(query: str) -> int:
        for pair in query.split("&"):
            k, _, v = pair.partition("=")
            if k == "root" and v.isdigit() and int(v) < len(roots):
                return int(v)
        return 0

    def _pick(query: str):
        """Broadcaster for this request: explicit root=N, else the combined
        all-worktrees view when several checkouts exist."""
        for pair in query.split("&"):
            k, _, v = pair.partition("=")
            if k == "root" and v.isdigit() and int(v) < len(roots):
                return bcasts[int(v)]
        return combined or bcasts[0]

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            self.wfile.write(body)

        def _sse(self, bcast: _Broadcaster) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Roadmap-Root", root_id)
            self.end_headers()
            ver, snap = bcast.snapshot()
            try:
                self.wfile.write(("data: " + snap + "\n\n").encode("utf-8"))
                self.wfile.flush()
                while True:
                    # Block until the shared watcher reports a change (or 15s
                    # keepalive). No per-client filesystem polling.
                    new_ver, new_snap = bcast.wait(ver, 15)
                    if new_ver != ver:
                        ver = new_ver
                        self.wfile.write(("data: " + new_snap + "\n\n").encode("utf-8"))
                    else:
                        self.wfile.write(b": ping\n\n")   # keepalive / disconnect probe
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            rroot = roots[_root_ix(query)][0]
            if path == "/":
                self._send(200, dashboard_html.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/events":
                self._sse(_pick(query))
            elif path == "/api/status":
                self._send(200, _pick(query).snapshot()[1].encode("utf-8"),
                           "application/json")
            elif path == "/api/item":
                iid = None
                for pair in query.split("&"):
                    k, _, v = pair.partition("=")
                    if k == "id" and v.isdigit():
                        iid = int(v)
                payload = ({"error": "missing id"} if iid is None
                           else _item_detail(rm, rroot, iid))
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            elif path == "/api/changelog":
                try:
                    payload = rm.changelog_json(rroot)
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
        preferred = _project_port(primary)
        # Already serving THIS project in another terminal? Point at it, don't
        # start a duplicate. Scan the span in case it landed on a fallback port.
        for candidate in range(preferred, preferred + PORT_SPAN):
            existing = _running_dashboard(primary, candidate)
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

    # One shared watcher per root drives every SSE client and mirrors progress
    # to this terminal — a single filesystem scan per second per checkout.
    for i, (p, b) in enumerate(roots):
        label = f"[{b or p.name}] " if len(roots) > 1 else ""
        bc = _Broadcaster(rm, p, extra={"_root": i, "_roots": roots_meta},
                          label=label)
        bc.start()
        bcasts.append(bc)
    if len(roots) > 1:
        combined = _CombinedBroadcaster(bcasts, roots_meta)
        combined.start()

    url = f"http://127.0.0.1:{port}"
    print(f"roadmap dashboard → {url}  (Ctrl-C to stop)")
    for (p, b), bc in zip(roots, bcasts):
        print(f"  {bc.label}{_status_line(json.loads(bc.json))}", flush=True)
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
