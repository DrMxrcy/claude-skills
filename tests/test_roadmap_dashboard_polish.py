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


# ---- step 2: connection banner + reconnect ---------------------------------

def _script(dashboard):
    import re
    body = dashboard._dashboard_html()
    return body, "\n".join(re.findall(r"<script>(.*?)</script>", body, re.S))


def test_dashboard_html_has_connection_banner(dashboard):
    body, js = _script(dashboard)
    assert 'id="connbanner"' in body and "claude-roadmap serve" in body
    assert 'id="cbcopy"' in body and "navigator.clipboard" in js
    # our own backoff replaces EventSource's retry; the last data stays drawn
    assert "BACKOFF = [1000, 2000, 4000, 8000]" in js
    onerror = js[js.index("es.onerror"):js.index("function onPayload")]
    assert "es.close()" in onerror and "scheduleRetry()" in onerror
    assert "replaceChildren" not in onerror and "render(" not in onerror
    # the banner shows well inside the 5 s acceptance window
    import re
    grace = int(re.search(r"DOWN_GRACE = (\d+)", js).group(1))
    assert grace <= 2000
    # a restarted server (new instance id) reloads the open route in place
    on = js[js.index("function onPayload"):]
    assert "P.instance !== INSTANCE" in on and "refreshRoute()" in on
    assert "location.reload" not in js
    # manual refresh + scanning hint + last-updated stamp
    for hook in ('id="refreshBtn"', 'id="scanhint"', 'id="stamp"',
                 "scanning this worktree"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node not installed")
def test_dashboard_script_parses(dashboard, tmp_path):
    import subprocess
    _, js = _script(dashboard)
    f = tmp_path / "d.js"
    f.write_text(js)
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ---- step 3: tab title, favicon dot, opt-in notifications ------------------

def _pure_block(js):
    a = js.index("// <plan50-pure>")
    return js[a:js.index("// </plan50-pure>", a)]


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node not installed")
def test_title_favicon_and_notify_logic_in_node(dashboard, tmp_path):
    import subprocess
    _, js = _script(dashboard)
    harness = _pure_block(js) + r"""
const assert = require("assert");
const one = {attention: [{kind: "refuted", id: 1, text: "#1 x — verdict REFUTED"}]};
assert.strictEqual(attnCount(one), 1);
assert.strictEqual(titleFor("Demo", attnCount(one)), "(1) Demo — roadmap");
// resolving it clears both the count and the dot
assert.strictEqual(titleFor("Demo", attnCount({attention: []})), "Demo — roadmap");
assert.strictEqual(attnCount({}), 0);
assert.strictEqual(titleFor(null, 0), "roadmap");
const dot = decodeURIComponent(FAVICON(true)), plain = decodeURIComponent(FAVICON(false));
assert.ok(dot.includes("<circle") && dot.includes("#f85149"));
assert.ok(!plain.includes("<circle"));
assert.ok(FAVICON(true).startsWith("data:image/svg+xml,"));
// never without the page opt-in, even when the browser already granted it
assert.strictEqual(shouldNotify(0, 1, false, "granted"), false);
assert.strictEqual(shouldNotify(0, 1, undefined, "granted"), false);
assert.strictEqual(shouldNotify(0, 1, true, "default"), false);
assert.strictEqual(shouldNotify(0, 1, true, "denied"), false);
// only on a rise against a settled baseline
assert.strictEqual(shouldNotify(null, 3, true, "granted"), false);
assert.strictEqual(shouldNotify(2, 2, true, "granted"), false);
assert.strictEqual(shouldNotify(2, 1, true, "granted"), false);
assert.strictEqual(shouldNotify(1, 2, true, "granted"), true);
console.log("ok");
"""
    f = tmp_path / "t.js"
    f.write_text(harness)
    r = subprocess.run(["node", str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_notifications_only_after_page_opt_in(dashboard):
    body, js = _script(dashboard)
    assert 'id="favicon"' in body and 'id="notifyBtn"' in body
    # exactly one place builds a notification, and it is only reached through
    # shouldNotify(..., NOTIFY_ON, ...)
    assert js.count("new Notification(") == 1
    assert js.count("notifyRise(") == 2          # definition + one guarded call
    assert "if(shouldNotify(ATTN_PREV, n, NOTIFY_ON, notifyPerm())) notifyRise(P, n);" in js
    # permission is only requested from the opt-in button's click handler
    assert js.count("requestPermission") == 1
    click = js[js.index('getElementById("notifyBtn").onclick'):]
    assert "requestPermission" in click[:click.index("syncNotifyBtn();\nfunction")]
    # the opt-in defaults off and is only true when stored true
    assert 'NOTIFY_ON = store.get("rm-notify", false) === true' in js
    # mid-scan payloads never notify or settle the baseline
    hook = js[js.index("PAYLOAD_HOOKS.push((P, restarted)"):]
    assert hook.index("if(P.scanning) return;") < hook.index("shouldNotify(")
    assert "document.title = titleFor(" in js
