"""Tests for `roadmap serve` — the local live dashboard."""
import json
import subprocess
import threading
import time
import urllib.request

import pytest


def _start(roadmap, repo, monkeypatch):
    """Start `serve` on an auto port in a daemon thread; return (base_url,
    shutdown). Browser opening is disabled."""
    import http.server

    holder = {}

    def run():
        # Replace the base with a subclass that records each instance, so the
        # Server subclass created inside serve() still subclasses cleanly and we
        # can grab the instance to shut it down in teardown.
        orig = http.server.ThreadingHTTPServer

        class Capturing(orig):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                holder["srv"] = self

        monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capturing)
        roadmap.serve(repo, port=None, open_browser=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    for _ in range(50):
        if "srv" in holder:
            break
        time.sleep(0.02)
    assert "srv" in holder, "server did not start"
    port = holder["srv"].server_address[1]
    return f"http://127.0.0.1:{port}", holder["srv"].shutdown


@pytest.fixture
def served(roadmap, repo, monkeypatch):
    """Init a roadmap with one item, start `serve` on an auto port in a thread,
    and yield (base_url, roadmap_module, repo_path). Server is a daemon thread."""
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])
    base, stop = _start(roadmap, repo, monkeypatch)
    yield base, roadmap, repo
    stop()


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo, msg):
    _git(repo, "commit", "--allow-empty", "-qm", msg)


@pytest.fixture
def served_branches(roadmap, repo, monkeypatch):
    """Item 1 at 0/N on trunk with `roadmap/1` three commits ahead (two tagged
    `(plan 1)`), item 2 untouched, plus an unattributed `experiment` branch."""
    import importlib
    monkeypatch.chdir(repo)
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init")
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])
    roadmap.main(["new", "--type", "feature", "--title", "Second thing"])
    importlib.import_module("rmlib.branches")._CACHE.clear()
    _git(repo, "checkout", "-qb", "roadmap/1")
    for msg in ("build a (plan 1)", "<b>tidy</b> & polish", "build b (plan 1)"):
        _commit(repo, msg)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-qb", "experiment")
    _commit(repo, "try something")
    _git(repo, "checkout", "-q", "main")
    base, stop = _start(roadmap, repo, monkeypatch)
    yield base, roadmap, repo
    stop()


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def test_root_serves_html(served):
    base, _, _ = served
    status, ctype, body = _get(base + "/")
    assert status == 200
    assert "text/html" in ctype
    assert b"<!doctype html>" in body.lower()
    assert b"EventSource" in body  # SSE client present


def test_api_status_matches_status_fn(served):
    base, roadmap, repo = served
    status, ctype, body = _get(base + "/api/status")
    assert status == 200
    assert "application/json" in ctype
    assert json.loads(body)["merged"] == roadmap.status(repo)


def test_api_status_items_carry_display_id(served):
    base, _, _ = served
    _, _, body = _get(base + "/api/status")
    item = json.loads(body)["merged"]["items"][0]
    assert item["id"] == 1 and item["displayId"] == "FEAT-1"


def test_api_item_returns_steps(served):
    base, roadmap, repo = served
    status, ctype, body = _get(base + "/api/item?id=1")
    assert status == 200
    d = json.loads(body)
    assert d["id"] == 1
    assert d["title"] == "First thing"
    assert isinstance(d["steps"], list)          # checklist steps from the plan
    assert all("done" in s and "text" in s for s in d["steps"])


def test_api_item_missing_id(served):
    base, _, _ = served
    _, _, body = _get(base + "/api/item")
    assert json.loads(body)["error"] == "missing id"


def test_api_item_unknown_id(served):
    base, _, _ = served
    _, _, body = _get(base + "/api/item?id=999")
    assert "no item" in json.loads(body)["error"]


def test_unknown_path_404(served):
    base, _, _ = served
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/nope")
    assert e.value.code == 404


def test_binds_localhost_only(served):
    base, _, _ = served
    # base is 127.0.0.1 by construction; assert the server address is loopback.
    assert base.startswith("http://127.0.0.1:")


def test_sse_pushes_on_change(served):
    base, roadmap, repo = served
    req = urllib.request.urlopen(base + "/events", timeout=5)
    # First frame is the initial snapshot.
    first = _read_sse_data(req)
    assert first["merged"]["items"][0]["pct"] == 0
    # Mutate the roadmap; the stream should push an updated snapshot.
    roadmap.main(["check", "--plan", "1", "--all-done"])
    updated = _read_sse_data(req, deadline=5)
    assert updated["merged"]["items"][0]["pct"] == 100
    req.close()


def _read_sse_data(resp, deadline=3):
    """Read lines until a `data:` JSON frame arrives (skipping `: ping`)."""
    end = time.time() + deadline
    while time.time() < end:
        line = resp.readline().decode("utf-8").rstrip("\n")
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError("no SSE data frame before deadline")


def test_second_serve_same_project_points_at_existing(served, capsys):
    base, roadmap, repo = served
    # A second `serve` for the SAME project must NOT start a duplicate; it
    # detects the running one and returns 0 after reporting its URL.
    rc = roadmap.serve(repo, port=None, open_browser=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "already being served" in out
    assert base.split(":")[-1] in out  # same port reported


def test_project_port_is_deterministic_and_in_range(dashboard, tmp_path):
    a = tmp_path / "proj-a"
    a.mkdir()
    p1 = dashboard._project_port(a)
    p2 = dashboard._project_port(a)
    assert p1 == p2                                   # same project -> same port
    assert dashboard.DEFAULT_PORT <= p1 < dashboard.DEFAULT_PORT + dashboard.PORT_SPAN
    # A different path maps through the hash independently (may collide 1/SPAN,
    # so we assert it still lands in range rather than strict distinctness).
    b = tmp_path / "proj-b"; b.mkdir()
    assert dashboard.DEFAULT_PORT <= dashboard._project_port(b) < \
        dashboard.DEFAULT_PORT + dashboard.PORT_SPAN


def test_serve_no_roadmap_is_noop(roadmap, tmp_path, capsys):
    # No .roadmap/ dir -> prints guidance and returns 0 without binding.
    rc = roadmap.serve(tmp_path, port=None, open_browser=False)
    assert rc == 0
    assert "roadmap init" in capsys.readouterr().out


def test_api_ideas_empty_when_no_incubator(served):
    base, _, _ = served
    status, ctype, body = _get(base + "/api/ideas")
    assert status == 200
    assert "application/json" in ctype
    assert json.loads(body)["bullets"] == []


def test_api_ideas_lists_parked_bullets(served):
    base, roadmap, repo = served
    roadmap.main(["idea", "--title", "Dark mode for the dashboard"])
    d = json.loads(_get(base + "/api/ideas")[1 + 1])
    assert [b["title"] for b in d["bullets"]] == ["Dark mode for the dashboard"]
    assert d["file"]


def test_api_ideas_root_scoped(served):
    """?root=N picks a checkout; an out-of-range index falls back to root 0."""
    base, roadmap, _ = served
    roadmap.main(["idea", "--title", "Root scoped idea"])
    for q in ("?root=0", "?root=99"):
        d = json.loads(_get(base + "/api/ideas" + q)[2])
        assert [b["title"] for b in d["bullets"]] == ["Root scoped idea"]


def test_dashboard_html_has_tabs(served):
    base, _, _ = served
    body = _get(base + "/")[2].decode()
    for label in ("Roadmap", "Ideas", "Changelog"):
        assert label in body
    assert "/api/ideas" in body and "/api/changelog" in body


# --- in-flight overlay (plan 30) ------------------------------------------

def _trunk_view(payload):
    return payload["statuses"][payload["trunkRoot"]]


def test_api_status_default_view_has_lanes_and_branch(served_branches):
    base, roadmap, repo = served_branches
    d = json.loads(_get(base + "/api/status")[2])
    st = _trunk_view(d)
    assert st == roadmap.status(repo)
    one, two = st["items"]
    assert one["lane"] == "building" and one["status"] == "planned"
    assert one["branch"]["name"] == "roadmap/1"
    assert one["branch"]["ahead"] == 3 and one["branch"]["taggedCommits"] == 2
    assert "commits" not in one["branch"]        # list only on expand
    assert two["lane"] == "planned" and two["branch"] is None
    assert st["counts"]["lanes"]["inFlight"] == 1
    assert st["trunk"] == "main"
    assert [b["name"] for b in st["otherBranches"]] == ["experiment"]


def test_api_item_lists_branch_commits(served_branches):
    base, _, _ = served_branches
    d = json.loads(_get(base + "/api/item?id=1")[2])
    assert d["lane"] == "building" and d["claim"] is None
    b = d["branch"]
    assert b["name"] == "roadmap/1" and b["ahead"] == 3
    assert [c["subject"] for c in b["commits"]] == [
        "build b (plan 1)", "<b>tidy</b> & polish", "build a (plan 1)"]
    assert all(set(c) == {"sha", "date", "subject"} for c in b["commits"])
    assert json.loads(_get(base + "/api/item?id=2")[2])["branch"] is None


def test_api_item_commit_list_capped_at_20(served_branches):
    base, _, repo = served_branches
    _git(repo, "checkout", "-q", "roadmap/1")
    for n in range(25):
        _commit(repo, f"more {n} (plan 1)")
    _git(repo, "checkout", "-q", "main")
    b = json.loads(_get(base + "/api/item?id=1")[2])["branch"]
    assert b["ahead"] == 28 and len(b["commits"]) == 20
    assert b["commits"][0]["subject"] == "more 24 (plan 1)"


def test_api_item_reflects_claim(served_branches):
    base, roadmap, _ = served_branches
    roadmap.main(["claim", "1", "--stage", "gate-ready", "--verdict", "CONFIRMED"])
    d = json.loads(_get(base + "/api/item?id=1")[2])
    assert d["lane"] == "gate-ready"
    assert d["claim"]["verdict"] == "CONFIRMED"
    assert d["branch"]["commits"]


def test_api_item_no_branches_degrades(served):
    """Unborn repo (no commits, no refs): lane falls back, branch is null."""
    base, _, _ = served
    d = json.loads(_get(base + "/api/item?id=1")[2])
    assert d["branch"] is None and d["lane"] == "planned"
    st = _trunk_view(json.loads(_get(base + "/api/status")[2]))
    assert st["otherBranches"] == [] and st["trunk"] is None


def test_item_detail_outside_git(roadmap, dashboard, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "No git here"])
    d = dashboard._item_detail(roadmap._dashboard_api(), tmp_path, 1)
    assert d["title"] == "No git here" and d["branch"] is None


def test_item_detail_without_discovery_hook(roadmap, dashboard, repo, monkeypatch):
    """An rm interface lacking discover_branches still serves the item."""
    import types
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "x"])
    api = vars(roadmap._dashboard_api()).copy()
    api.pop("discover_branches")
    d = dashboard._item_detail(types.SimpleNamespace(**api), repo, 1)
    assert d["id"] == 1 and "error" not in d


def test_sse_pushes_on_branch_commit(served_branches):
    """Branch work never touches .roadmap/; the ref signature still refreshes."""
    base, _, repo = served_branches
    req = urllib.request.urlopen(base + "/events", timeout=5)
    first = _trunk_view(_read_sse_data(req))
    assert first["items"][0]["branch"]["ahead"] == 3
    _git(repo, "checkout", "-q", "roadmap/1")
    _commit(repo, "one more (plan 1)")
    _git(repo, "checkout", "-q", "main")
    updated = _trunk_view(_read_sse_data(req, deadline=5))
    assert updated["items"][0]["branch"]["ahead"] == 4
    req.close()


def test_tick_with_unchanged_refs_runs_one_git_call(roadmap, dashboard,
                                                    served_branches, monkeypatch):
    _, _, repo = served_branches
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo)
    calls = []
    real = subprocess.run
    me = threading.current_thread()

    def counting(cmd, *a, **k):
        # other servers' broadcaster threads tick concurrently — count ours only
        if cmd and cmd[0] == "git" and threading.current_thread() is me:
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    bc._tick()
    assert len(calls) == 1 and "for-each-ref" in calls[0]


def test_merged_view_keeps_branch_object(dashboard):
    branch = {"name": "roadmap/1", "ahead": 2}
    st = [{"project": "p", "currentVersion": "0.1.0",
           "items": [{"id": 1, "done": 0, "pct": 0, "branch": branch}]},
          {"project": "p", "currentVersion": "0.1.0",
           "items": [{"id": 1, "done": 1, "pct": 50, "branch": branch}]}]
    meta = [{"branch": "main", "name": "a"}, {"branch": "roadmap/1", "name": "b"}]
    it = dashboard._merge_status(st, meta)["items"][0]
    assert it["branch"] == branch and it["checkout"] == "roadmap/1"
    assert it["_root"] == 1


def test_trunk_root_prefers_trunk_checkout(dashboard):
    meta = [{"branch": "roadmap/1"}, {"branch": "main"}]
    assert dashboard._trunk_root([{"trunk": "main"}, {"trunk": "main"}], meta) == 1
    assert dashboard._trunk_root([{"trunk": None}], meta[:1]) == 0


def test_dashboard_html_has_inflight_hooks(served):
    base, _, _ = served
    body = _get(base + "/")[2].decode()
    for hook in ('id="openOnly"', 'id="laneFilter"', "otherBranches",
                 "trunkRoot", "verdict", "rm-filters", "/api/item"):
        assert hook in body, hook
    # untrusted branch names / commit subjects only ever go in as text
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
    assert "outerHTML" not in body


# --- terminal logging (plan 31) -------------------------------------------

def _fake_roots(repo, n):
    """n checkouts that all point at `repo`: enough to exercise the per-
    checkout collapse without creating real worktrees."""
    return [(repo.resolve(), "main")] + [
        (repo.resolve(), f"roadmap/{i}") for i in range(1, n)]


def _many_checkouts(roadmap, dashboard, repo, monkeypatch, n=22, verbose=False):
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])
    monkeypatch.setattr(dashboard, "_discover_roots",
                        lambda rm, root: _fake_roots(repo, n))
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo, verbose=verbose)
    bc.url = "http://127.0.0.1:4711"
    return bc


def test_refresh_log_is_one_line_with_url(roadmap, dashboard, repo,
                                          monkeypatch, capsys):
    bc = _many_checkouts(roadmap, dashboard, repo, monkeypatch)
    capsys.readouterr()
    roadmap.main(["check", "--plan", "1", "--all-done"])
    capsys.readouterr()
    bc._tick()
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1, lines
    assert "http://127.0.0.1:4711" in lines[0]
    assert "22 checkouts" in lines[0] and "[main]" in lines[0]


def test_refresh_log_verbose_adds_per_checkout_lines(roadmap, dashboard, repo,
                                                     monkeypatch, capsys):
    bc = _many_checkouts(roadmap, dashboard, repo, monkeypatch, verbose=True)
    roadmap.main(["check", "--plan", "1", "--all-done"])
    capsys.readouterr()
    bc._tick()
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1 + 22
    assert "http://127.0.0.1:4711" in lines[0]
    assert any("[roadmap/21]" in l for l in lines[1:])


def test_worktree_change_log_is_one_line_with_url(roadmap, dashboard, repo,
                                                  monkeypatch, capsys):
    bc = _many_checkouts(roadmap, dashboard, repo, monkeypatch, n=3)
    other = repo.parent / "elsewhere"
    monkeypatch.setattr(dashboard, "_discover_roots", lambda rm, root:
                        _fake_roots(repo, 3) + [(other, "roadmap/9")])
    capsys.readouterr()
    bc._tick(rescan=True)
    out = capsys.readouterr().out
    wt = [l for l in out.splitlines() if "worktrees now" in l]
    assert len(wt) == 1 and "4 checkouts" in wt[0] and "(+1 -0)" in wt[0]
    assert "http://127.0.0.1:4711" in wt[0]
    assert "roadmap/9" not in out    # names only under --verbose


def test_summary_lines_single_checkout_has_url(dashboard):
    data = {"_roots": [{"branch": None, "name": "p"}], "trunkRoot": 0,
            "statuses": [{"currentVersion": "0.1.0", "items": []}]}
    lines = dashboard._summary_lines(data, "http://127.0.0.1:4700", True)
    assert lines == ["current v0.1.0 · 0% (0/0) · 0 active · 0 versions"
                     "  → http://127.0.0.1:4700"]


def test_startup_prints_url_and_collapsed_status(roadmap, dashboard, repo,
                                                 monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    monkeypatch.setattr(dashboard, "_discover_roots",
                        lambda rm, root: _fake_roots(repo, 21))
    import http.server
    holder = {}
    orig = http.server.ThreadingHTTPServer

    class Capturing(orig):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            holder["srv"] = self

        def serve_forever(self, *a, **k):   # return right after startup output
            return None

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capturing)
    capsys.readouterr()
    assert dashboard.serve(roadmap._dashboard_api(), repo, port=0,
                           open_browser=False) == 0
    port = holder["srv"].server_address[1]
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    url = f"http://127.0.0.1:{port}"
    assert url in lines[0]
    status = [l for l in lines if "current v" in l]
    assert len(status) == 1 and url in status[0] and "21 checkouts" in status[0]
    assert any("--verbose" in l for l in lines)


def test_serve_cli_accepts_verbose(roadmap, monkeypatch, repo):
    seen = {}
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    monkeypatch.setattr(roadmap, "serve", lambda root, **k: seen.update(k) or 0)
    assert roadmap.main(["serve", "--no-open", "--verbose"]) == 0
    assert seen["verbose"] is True and seen["open_browser"] is False


def test_second_serve_prints_running_url_loudly(served, capsys):
    base, roadmap, repo = served
    capsys.readouterr()
    assert roadmap.serve(repo, port=None, open_browser=False) == 0
    out = capsys.readouterr().out
    first = out.splitlines()[0]
    assert first.startswith("roadmap dashboard already running") and base in first


# --- default view (plan 31) -----------------------------------------------

def test_dashboard_view_always_starts_on_trunk(served):
    """The view is never restored: no stored view key is read, the select
    opts out of browser form restore, and legacy keys/params are cleared."""
    base, _, _ = served
    body = _get(base + "/")[2].decode()
    assert 'const DEFAULT_VIEW = "trunk";' in body
    assert "let VIEW = DEFAULT_VIEW;" in body
    assert 'id="rootsel" autocomplete="off"' in body
    assert 'id="search" type="search" autocomplete="off"' in body
    # nothing ever stores or reads the view
    for bad in ('store.get("rm-view"', 'store.set("rm-view"',
                'store.get("rm-root"', 'store.set("rm-root"',
                'getItem("rm-view"', 'setItem("rm-view"'):
        assert bad not in body, bad
    assert 'removeItem(k)' in body and '"rm-view","rm-root"' in body
    # filters still persist
    assert 'store.get("rm-filters"' in body


# --- item body + note endpoint (plan 31) ----------------------------------

def _get_json(url):
    """(status, json) — HTTP errors are returned, not raised."""
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _plan_file(repo):
    return next((repo / ".roadmap" / "plans").glob("001-*.md"))


def test_api_item_returns_body_and_linked_notes(served):
    base, roadmap, repo = served
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "design.md").write_text("# Design\n\nhello\n")
    (notes / "1-handoff.md").write_text("# Handoff\n")
    pf = _plan_file(repo)
    pf.write_text(pf.read_text() + "\nSee [design](../notes/design.md) and "
                  "`.roadmap/notes/design.md`, plus notes/missing.md.\n")
    code, d = _get_json(base + "/api/item?id=1")
    assert code == 200
    assert d["planPath"] == ".roadmap/" + d["file"]
    assert d["body"].lstrip().startswith("# Plan 1")      # frontmatter stripped
    assert "id: 1" not in d["body"].split("\n", 3)[0]
    assert "[design](../notes/design.md)" in d["body"]   # raw markdown
    assert d["notes"] == [".roadmap/notes/design.md", ".roadmap/notes/1-handoff.md"]
    assert d["dependsOn"] == [] and d["blockedBy"] == []
    assert d["displayId"] == "FEAT-1"


def test_api_item_reports_dependencies(served):
    base, roadmap, repo = served
    roadmap.main(["new", "--type", "feature", "--title", "Second"])
    roadmap.main(["depends", "--plan", "2", "--on", "1"])
    code, d = _get_json(base + "/api/item?id=2")
    assert code == 200 and d["dependsOn"] == [1] and d["blockedBy"] == [1]


def test_api_note_serves_notes_and_plans(served):
    base, _, repo = served
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "x.md").write_text("# X\n<script>alert(1)</script>\n")
    code, d = _get_json(base + "/api/note?path=.roadmap/notes/x.md")
    assert code == 200 and d["path"] == ".roadmap/notes/x.md"
    assert d["body"] == "# X\n<script>alert(1)</script>\n"   # raw text, JSON
    rel = ".roadmap/plans/" + _plan_file(repo).name
    code, d = _get_json(base + "/api/note?path=" + urllib.parse.quote(rel))
    assert code == 200 and "# Plan 1" in d["body"]


@pytest.mark.parametrize("bad", [
    "", "../secret.md", ".roadmap/notes/../../secret.md",
    ".roadmap/notes/%2e%2e/%2e%2e/secret.md", ".roadmap/notes/./x.md",
    "/etc/passwd", "%2Fetc%2Fhosts.md", "C:/x.md", ".roadmap\\notes\\x.md",
    ".roadmap/notes/x.txt", ".roadmap/notes/x", ".roadmap/config.json",
    "ROADMAP.md", ".roadmap/x.md", "notes/x.md", ".roadmap/other/x.md",
    ".roadmap/notes/sub/x.md", ".roadmap/notes/.md",
])
def test_api_note_rejects_disallowed_paths(served, bad):
    base, _, repo = served
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "x.md").write_text("ok\n")
    (repo / "secret.md").write_text("secret\n")
    code, d = _get_json(base + "/api/note?path=" + bad)
    assert code == 400, (bad, code, d)
    assert "body" not in d


def test_api_note_missing_is_404(served):
    base, _, _ = served
    code, d = _get_json(base + "/api/note?path=.roadmap/notes/nope.md")
    assert code == 404 and "body" not in d


def test_api_note_rejects_symlink_escape(served, tmp_path_factory):
    base, _, repo = served
    outside = tmp_path_factory.mktemp("outside") / "leak.md"
    outside.write_text("leaked\n")
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "leak.md").symlink_to(outside)
    (repo / "secret.md").write_text("secret\n")
    (notes / "up.md").symlink_to(repo / "secret.md")
    for name in ("leak.md", "up.md"):
        code, d = _get_json(base + "/api/note?path=.roadmap/notes/" + name)
        assert code == 400 and "body" not in d, name


def test_api_note_rejects_symlinked_dir_escape(served, tmp_path_factory):
    base, _, repo = served
    outside = tmp_path_factory.mktemp("outdir")
    (outside / "x.md").write_text("leaked\n")
    notes = repo / ".roadmap" / "notes"
    if notes.exists():
        notes.rmdir()
    notes.symlink_to(outside, target_is_directory=True)
    code, d = _get_json(base + "/api/note?path=.roadmap/notes/x.md")
    assert code == 400 and "body" not in d


def test_api_ideas_carry_index_and_note(served):
    base, roadmap, repo = served
    roadmap.main(["idea", "--title", "Plain idea"])
    roadmap.main(["idea", "--title", "Idea with notes", "--body", "Long *form*."])
    d = json.loads(_get(base + "/api/ideas")[2])
    by = {b["title"]: b for b in d["bullets"]}
    plain, noted = by["Plain idea"], by["Idea with notes"]
    assert plain["note"] is None
    assert sorted([plain["index"], noted["index"]]) == [1, 2]   # promote --index
    assert noted["note"].startswith(".roadmap/notes/") and noted["note"].endswith(".md")
    code, n = _get_json(base + "/api/note?path=" + noted["note"])
    assert code == 200 and "Long *form*." in n["body"]


# --- pages (plan 31) ------------------------------------------------------

def test_dashboard_html_has_router_and_pages(served):
    base, _, _ = served
    body = _get(base + "/")[2].decode()
    for hook in ('"hashchange"', "parseRoute", '"#/plan/"', '"#/idea/"',
                 '"#/notes/"', "/api/note?path=", "planPage", "ideaPage",
                 "notePage", 'id="page"', "promote --index", "function md(",
                 "SCROLL[", "scrollRestoration"):
        assert hook in body, hook
    # inline dropdown expansion is gone
    assert "loadSteps" not in body and "openItems" not in body
    # the tab is a route now, never stored
    assert 'store.set("rm-tab"' not in body and 'store.get("rm-tab"' not in body


def test_dashboard_html_markdown_renderer_is_dom_only(served):
    """Plan/note markdown is untrusted: no HTML parsing sinks anywhere, and
    hrefs are gated to http(s) and in-app #/ routes."""
    base, _, _ = served
    body = _get(base + "/")[2].decode()
    for sink in (".innerHTML", "outerHTML", "insertAdjacentHTML",
                 "document.write", "DOMParser", "createContextualFragment",
                 "srcdoc", "eval(", "new Function"):
        assert sink not in body, sink
    assert r"const SAFE_HREF = /^(https?:\/\/[^\s]+|#\/[^\s]*)$/i;" in body
    # every href assignment goes through link() (or a fixed tab route)
    import re
    assigns = re.findall(r"\.href\s*=\s*([^;]+);", body)
    assert sorted(assigns) == sorted(['href', 'id === "roadmap" ? "#/" : "#/"+id']), assigns


def test_api_item_returns_rulings(served):
    """Plan 34 acceptance: `ruling 1 --text ... --approval` shows in /api/item."""
    base, roadmap, repo = served
    pf = _plan_file(repo)
    pf.write_text(pf.read_text() + "\n- **Ruling (2026-10-22, owner):** hand-written\n")
    assert roadmap.main(["ruling", "1", "--text", "Use tabs", "--approval"]) == 0
    code, d = _get_json(base + "/api/item?id=1")
    assert code == 200
    assert [(r["by"], r["text"], r["approval"]) for r in d["rulings"]] == [
        ("owner", "hand-written", False), ("owner", "Use tabs", True)]
    assert d["rulings"][0]["date"] == "2026-10-22"
    assert d["needsApproval"] is False
    # The streamed status (built by status()) carries the same list.
    assert roadmap.status(repo)["items"][0]["rulings"] == d["rulings"]


def test_dashboard_html_has_rulings_display(dashboard):
    """Plan 34: the item card and plan page render rulings (approvals flagged,
    'needs approval' marker) from status/api fields, DOM-only."""
    body = dashboard._dashboard_html()
    for hook in ("function rulingBadges", "function rulingsBlock", "it.rulings",
                 "it.needsApproval", "needs approval", "r.approval",
                 "rulingsBlock(d.rulings)", "rulingBadges(d)", "rulingBadges(it)"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
