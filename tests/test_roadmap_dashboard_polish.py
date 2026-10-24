"""Plan 50 — dashboard resilience and polish: fast first payload with a server
instance id, the needs-attention count behind the tab title, the reconnect
banner, opt-in notifications, light/dark theme tokens with a contrast check."""
import json
import threading
import time
import urllib.request

import pytest


def _start_serve(dashboard, api, repo, monkeypatch, holder_thread=None):
    """Run dashboard.serve(api, repo) in a daemon thread on a free port; return
    (base_url, shutdown). `holder_thread` (a dict) receives the serving thread
    under "t" before it starts."""
    import http.server
    holder = {}
    orig = http.server.ThreadingHTTPServer

    class Capturing(orig):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            holder["srv"] = self

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capturing)
    t = threading.Thread(target=lambda: dashboard.serve(
        api, repo, port=0, open_browser=False), daemon=True)
    if holder_thread is not None:
        holder_thread["t"] = t
    t.start()
    for _ in range(250):
        if "srv" in holder:
            break
        time.sleep(0.02)
    assert "srv" in holder, "server did not start"
    port = holder["srv"].server_address[1]
    return f"http://127.0.0.1:{port}", holder["srv"].shutdown


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.headers, json.loads(r.read())


def _init(roadmap, repo, monkeypatch, n=1):
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    for i in range(n):
        roadmap.main(["new", "--type", "feature", "--title", f"Thing {i + 1}"])


def _fake_roots(repo, n):
    return [(repo.resolve(), "main")] + [
        (repo.resolve(), f"roadmap/{i}") for i in range(1, n)]


# ---- step 1: instance id + incremental first payload -----------------------

def test_payload_carries_instance_id_and_updated(roadmap, dashboard, repo,
                                                  monkeypatch):
    _init(roadmap, repo, monkeypatch)
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo)
    d = json.loads(bc.snapshot()[1])
    assert isinstance(d["instance"], str) and len(d["instance"]) == 12
    assert isinstance(d["updated"], int) and d["updated"] > 0
    # another server process -> another instance id
    other = dashboard._Broadcaster(roadmap._dashboard_api(), repo)
    assert json.loads(other.snapshot()[1])["instance"] != d["instance"]
    # an unchanged tick neither bumps the version nor moves `updated`
    ver = bc.snapshot()[0]
    bc._tick()
    assert bc.snapshot()[0] == ver
    assert json.loads(bc.snapshot()[1])["updated"] == d["updated"]
    # a real change does, and the instance id stays put
    roadmap.main(["check", "--plan", "1", "--all-done"])
    bc._tick()
    d2 = json.loads(bc.snapshot()[1])
    assert bc.snapshot()[0] == ver + 1
    assert d2["instance"] == d["instance"] and d2["updated"] >= d["updated"]


def test_http_responses_carry_instance_header(roadmap, dashboard, repo, monkeypatch):
    _init(roadmap, repo, monkeypatch)
    base, stop = _start_serve(dashboard, roadmap._dashboard_api(), repo,
                              monkeypatch)
    try:
        headers, d = _get(base + "/api/status")
        assert headers.get("X-Roadmap-Instance") == d["instance"]
        req = urllib.request.urlopen(base + "/events", timeout=5)
        assert req.headers.get("X-Roadmap-Instance") == d["instance"]
        line = b""
        while not line.startswith(b"data: "):
            line = req.readline()
        assert json.loads(line[6:])["instance"] == d["instance"]
        req.close()
    finally:
        stop()


def test_first_status_answers_before_worktree_scan_finishes(
        roadmap, dashboard, repo, monkeypatch):
    """13 checkouts: /api/status answers with the trunk checkout while the
    other 12 are still being scanned, then fills them in."""
    _init(roadmap, repo, monkeypatch, n=2)
    monkeypatch.setattr(dashboard, "_discover_roots",
                        lambda rm, root: _fake_roots(repo, 13))
    api = roadmap._dashboard_api()
    real_status = api.status
    gate = threading.Event()
    serve_thread = {}

    def gated_status(root, *a, **k):
        # The serving thread computes the first payload; every other thread
        # (the broadcaster's scan) waits for the test to open the gate.
        if threading.current_thread() is not serve_thread.get("t"):
            gate.wait(20)
        return real_status(root, *a, **k)

    api.status = gated_status
    stop = None
    try:
        base, stop = _start_serve(dashboard, api, repo, monkeypatch, serve_thread)
        _, d = _get(base + "/api/status")
        assert not gate.is_set()
        assert d["scanning"] == {"done": 1, "total": 13}
        tr = d["trunkRoot"]
        assert [i["title"] for i in d["statuses"][tr]["items"]] == ["Thing 1", "Thing 2"]
        pending = [s for i, s in enumerate(d["statuses"]) if i != tr]
        assert len(pending) == 12 and all(s.get("scanning") for s in pending)
        assert "worktrees" not in d and "conflicts" not in d
        assert d["attention"] == []
        gate.set()
        deadline = time.time() + 20
        while time.time() < deadline:
            _, d = _get(base + "/api/status")
            if "scanning" not in d:
                break
            time.sleep(0.1)
        assert "scanning" not in d, "scan never finished"
        assert all(len(s["items"]) == 2 for s in d["statuses"])
        assert not any(s.get("scanning") for s in d["statuses"])
    finally:
        gate.set()
        if stop:
            stop()


def test_single_checkout_first_payload_is_complete(roadmap, dashboard, repo,
                                                   monkeypatch):
    _init(roadmap, repo, monkeypatch)
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo, fast_start=True)
    d = json.loads(bc.snapshot()[1])
    assert "scanning" not in d and bc._partial is None


def test_fast_start_scan_publishes_each_checkout(roadmap, dashboard, repo,
                                                 monkeypatch):
    _init(roadmap, repo, monkeypatch)
    monkeypatch.setattr(dashboard, "_discover_roots",
                        lambda rm, root: _fake_roots(repo, 4))
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo, fast_start=True)
    seen = []
    real = bc._publish
    monkeypatch.setattr(bc, "_publish", lambda core: (
        seen.append(json.loads(core).get("scanning")), real(core))[1])
    bc._finish_scan()
    assert seen == [{"done": 2, "total": 4}, {"done": 3, "total": 4}, None]
    d = json.loads(bc.snapshot()[1])
    assert "scanning" not in d and len(d["statuses"]) == 4
    assert bc._partial is None


# ---- needs-attention count (tab title / favicon) ---------------------------

def test_attention_counts_refuted_claim_and_clears(roadmap, dashboard, repo,
                                                   monkeypatch):
    _init(roadmap, repo, monkeypatch, n=2)
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), repo)
    assert json.loads(bc.snapshot()[1])["attention"] == []
    roadmap.set_claim(repo, 1, stage="fixing", verdict="REFUTED")
    bc._tick()
    att = json.loads(bc.snapshot()[1])["attention"]
    assert [a["kind"] for a in att] == ["refuted"] and att[0]["id"] == 1
    # same checks as the CLI digest: the dashboard and `digest` agree
    import rmlib.digest as rmdigest
    st = roadmap.status(repo)
    assert att == rmdigest.attention(repo, st)
    roadmap.set_claim(repo, 1, stage="review", verdict="CONFIRMED")
    bc._tick()
    assert json.loads(bc.snapshot()[1])["attention"] == []


def test_attention_degrades_without_hook(roadmap, dashboard, repo, monkeypatch):
    _init(roadmap, repo, monkeypatch)
    api = roadmap._dashboard_api()
    del api.attention
    bc = dashboard._Broadcaster(api, repo)
    assert json.loads(bc.snapshot()[1])["attention"] == []
    api.attention = lambda root, st: 1 / 0
    assert dashboard._safe_attention(api, repo, roadmap.status(repo), None) == []
