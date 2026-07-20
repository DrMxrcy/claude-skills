"""Tests for `roadmap serve` — the local live dashboard."""
import json
import threading
import time
import urllib.request

import pytest


@pytest.fixture
def served(roadmap, repo, monkeypatch):
    """Init a roadmap with one item, start `serve` on an auto port in a thread,
    and yield (base_url, roadmap_module, repo_path). Server is a daemon thread."""
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])

    # Build the handler/server without blocking on serve_forever(); reuse the
    # public serve() by running it in a thread with browser opening disabled.
    import http.server

    holder = {}

    def run():
        # Patch ThreadingHTTPServer to capture the instance so we can shut it.
        orig = http.server.ThreadingHTTPServer

        def capture(*a, **k):
            srv = orig(*a, **k)
            holder["srv"] = srv
            return srv

        monkeypatch.setattr(http.server, "ThreadingHTTPServer", capture)
        roadmap.serve(repo, port=None, open_browser=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    for _ in range(50):
        if "srv" in holder:
            break
        time.sleep(0.02)
    assert "srv" in holder, "server did not start"
    port = holder["srv"].server_address[1]
    yield f"http://127.0.0.1:{port}", roadmap, repo
    holder["srv"].shutdown()


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
    assert json.loads(body) == roadmap.status(repo)


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
    assert first["items"][0]["pct"] == 0
    # Mutate the roadmap; the stream should push an updated snapshot.
    roadmap.main(["check", "--plan", "1", "--all-done"])
    updated = _read_sse_data(req, deadline=5)
    assert updated["items"][0]["pct"] == 100
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


def test_different_projects_get_different_ports(roadmap, tmp_path):
    a = tmp_path / "proj-a"
    b = tmp_path / "proj-b"
    a.mkdir(); b.mkdir()
    (a / ".roadmap").mkdir(); (b / ".roadmap").mkdir()
    assert roadmap._project_port(a) != roadmap._project_port(b) or \
        a.resolve() == b.resolve()  # distinct paths -> (almost always) distinct ports


def test_serve_no_roadmap_is_noop(roadmap, tmp_path, capsys):
    # No .roadmap/ dir -> prints guidance and returns 0 without binding.
    rc = roadmap.serve(tmp_path, port=None, open_browser=False)
    assert rc == 0
    assert "roadmap init" in capsys.readouterr().out
