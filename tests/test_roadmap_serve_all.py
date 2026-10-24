"""Plan 48: `serve --all` — one server and one home page for every registered
project, each project's dashboard mounted under /p/<slug>/."""
import http.server
import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"


def _cli(cwd, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True)


def _project(path: Path, name: str, items: int, check: int = 0) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    assert _cli(path, "init", "--name", name).returncode == 0
    for n in range(items):
        assert _cli(path, "new", "--type", "feature", "--title",
                    f"{name} item {n + 1}").returncode == 0
    for n in range(check):
        assert _cli(path, "check", "--plan", str(n + 1), "--step", "1",
                    "--force").returncode == 0
    return path


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.headers, r.read()


def _get_json(url):
    return json.loads(_get(url)[2])


def _start_all(roadmap, monkeypatch):
    """Run `serve_all` on an auto port in a daemon thread; (base_url, server)."""
    holder = {}

    def run():
        orig = http.server.ThreadingHTTPServer

        class Capturing(orig):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                holder["srv"] = self

        monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capturing)
        roadmap.serve_all(port=0, open_browser=False)

    threading.Thread(target=run, daemon=True).start()
    for _ in range(250):
        if "srv" in holder:
            break
        time.sleep(0.02)
    assert "srv" in holder, "server did not start"
    return f"http://127.0.0.1:{holder['srv'].server_address[1]}", holder["srv"]


@pytest.fixture
def two_projects(tmp_path):
    a = _project(tmp_path / "alpha", "Alpha", items=2, check=1)
    b = _project(tmp_path / "beta", "Beta", items=1)
    for p in (a, b):
        assert _cli(p, "status").returncode == 0      # registers it
    return a, b


@pytest.fixture
def served_all(roadmap, two_projects, monkeypatch):
    base, srv = _start_all(roadmap, monkeypatch)
    yield base, two_projects, srv
    srv.shutdown()


def test_home_lists_both_projects_with_versions_and_counts(served_all):
    base, (a, b), _ = served_all
    cards = {c["slug"]: c for c in _get_json(base + "/api/projects")["projects"]}
    assert set(cards) == {"alpha", "beta"}
    al, be = cards["alpha"], cards["beta"]
    assert al["version"] == be["version"] == "0.0.1"
    assert al["path"] == str(a.resolve()) and al["exists"] is True
    assert (al["items"], al["done"], al["inFlight"], al["blocked"]) == (2, 1, 0, 0)
    assert al["total"] > al["done"] and 0 < al["pct"] < 100
    assert (be["items"], be["done"], be["pct"]) == (1, 0, 0)
    assert al["lastActivity"] and al["alerts"] == []


def test_home_page_is_the_dashboard_in_all_mode(served_all):
    base, _, _ = served_all
    status, headers, body = _get(base + "/")
    assert status == 200 and b'<meta name="roadmap-mode" content="all">' in body
    assert headers["X-Roadmap-Root"] == "*all-projects*"


def test_project_endpoints_are_mounted_under_prefix(served_all, roadmap):
    base, (a, b), _ = served_all
    st = _get_json(base + "/p/alpha/api/status")
    assert st["statuses"][0]["project"] == "Alpha"
    assert [i["title"] for i in st["merged"]["items"]] == ["Alpha item 1",
                                                           "Alpha item 2"]
    item = _get_json(base + "/p/beta/api/item?id=1")
    assert item["title"] == "Beta item 1" and item["steps"]
    item = _get_json(base + "/p/alpha/api/item?id=2")
    note = _get_json(base + "/p/alpha/api/note?path="
                     + urllib.request.quote(item["planPath"]))
    assert "Alpha item 2" in note["body"]
    assert isinstance(_get_json(base + "/p/alpha/api/ideas")["bullets"], list)


def test_unknown_project_is_404(served_all):
    base, _, _ = served_all
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/p/nope/api/status")
    assert e.value.code == 404


def test_typed_project_url_redirects_to_hash_route(served_all):
    base, _, _ = served_all
    status, headers, body = _get(base + "/p/alpha/")   # urllib follows the 302
    assert status == 200 and b'content="all"' in body


def test_broadcasters_start_lazily(served_all, roadmap, monkeypatch):
    base, _, srv = served_all
    _get_json(base + "/api/projects")
    # nothing mounted until a project is opened
    mounts = _mounts(srv)
    assert mounts == 0
    _get_json(base + "/p/alpha/api/status")
    assert _mounts(srv) == 1
    _get_json(base + "/p/alpha/api/status")
    assert _mounts(srv) == 1
    _get_json(base + "/p/beta/api/status")
    assert _mounts(srv) == 2


def _mounts(srv):
    """Count mounted projects through the handler's closure (the _Home)."""
    do_get = srv.RequestHandlerClass.do_GET
    for cell in do_get.__closure__ or ():
        obj = cell.cell_contents
        if hasattr(obj, "mounted"):
            return obj.mounted()
    raise AssertionError("no _Home in the handler closure")


def test_project_sse_stream_pushes_on_change(served_all):
    base, (a, b), _ = served_all
    resp = urllib.request.urlopen(base + "/p/beta/events", timeout=5)
    first = _sse_data(resp)
    assert first["statuses"][0]["project"] == "Beta"
    assert _cli(b, "new", "--type", "feature", "--title", "Fresh").returncode == 0
    for _ in range(6):
        nxt = _sse_data(resp)
        if any(i["title"] == "Fresh" for i in nxt["statuses"][0]["items"]):
            break
    else:
        raise AssertionError("no push after the change")
    resp.close()


def _sse_data(resp):
    while True:
        line = resp.readline().decode()
        if line.startswith("data: "):
            return json.loads(line[6:])


def test_missing_project_is_greyed_and_not_mounted(served_all):
    base, (a, b), _ = served_all
    shutil.rmtree(b)
    cards = {c["slug"]: c for c in _get_json(base + "/api/projects")["projects"]}
    assert cards["beta"]["exists"] is False and "version" not in cards["beta"]
    assert cards["alpha"]["exists"] is True
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/p/beta/api/status")
    assert e.value.code == 404


def test_broken_registry_serves_empty_home(roadmap, monkeypatch, _registry_home):
    (_registry_home / "projects.json").write_text("][")
    base, srv = _start_all(roadmap, monkeypatch)
    try:
        assert _get_json(base + "/api/projects") == {"projects": []}
    finally:
        srv.shutdown()


def test_home_cards_are_cached(roadmap, dashboard, two_projects, monkeypatch):
    calls = []
    api = roadmap._dashboard_api()
    real = api.status
    api.status = lambda root, **k: calls.append(root) or real(root, **k)
    home = dashboard._Home(api)
    home.cards()
    assert len(calls) == 2
    home.cards()
    assert len(calls) == 2                     # within HOME_TTL: no status()
    monkeypatch.setattr(dashboard, "HOME_TTL", 0.0)
    home.cards()
    assert len(calls) == 4


def test_card_alerts(dashboard):
    st = {"slots": {"clashes": 2}, "wip": {"count": 4, "limit": 3, "over": True},
          "waitingDue": [{"daysLeft": -2}, {"daysLeft": 0}],
          "trunkHealth": {"green": False, "shards": [
              {"shard": "unit", "result": "fail"}, {"shard": "e2e", "result": "pass"}]}}
    items = [{"id": 3, "displayId": "#3", "lane": "review",
              "claim": {"verdict": "REFUTED"}},
             {"id": 4, "displayId": "#4", "lane": "done",
              "claim": {"verdict": "REFUTED"}}]
    kinds = {a["kind"]: a["text"] for a in dashboard._card_alerts(st, items)}
    assert kinds == {"refuted": "1 REFUTED: #3", "slots": "2 slot clashes",
                     "wip": "4 in flight (WIP limit 3)",
                     "waiting": "1 waiting step overdue",
                     "trunk": "trunk suite failing (unit)"}
    assert dashboard._card_alerts({}, []) == []


def test_lazy_broadcaster_idles_without_clients(roadmap, dashboard, tmp_path):
    p = _project(tmp_path / "solo", "Solo", items=1)
    b = dashboard._LazyBroadcaster(roadmap._dashboard_api(), p)
    ticks = []
    b._tick = lambda rescan=False: ticks.append(rescan)
    t = threading.Thread(target=b._run, daemon=True)
    t.start()
    time.sleep(1.3)
    assert ticks == []                       # nobody watching: no tick
    b.clients = 1
    time.sleep(1.2)
    assert ticks                             # watched: the 1 s tick runs


def test_serve_cli_all_flag_and_outside_project_default(roadmap, monkeypatch,
                                                        tmp_path):
    seen = []
    monkeypatch.setattr(roadmap, "serve_all", lambda **k: seen.append(k) or 0)
    monkeypatch.setattr(roadmap, "serve", lambda root, **k: seen.append("one") or 0)
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    assert roadmap.main(["serve", "--no-open"]) == 0          # outside a project
    assert seen[-1] == {"port": None, "open_browser": False, "verbose": False}
    proj = _project(tmp_path / "p", "P", items=0)
    monkeypatch.chdir(proj)
    assert roadmap.main(["serve", "--no-open"]) == 0
    assert seen[-1] == "one"
    assert roadmap.main(["serve", "--all", "--port", "4999"]) == 0
    assert seen[-1]["port"] == 4999


def test_second_serve_all_points_at_running_one(roadmap, dashboard, monkeypatch,
                                                capsys):
    monkeypatch.setattr(dashboard, "_running_all",
                        lambda port: "http://127.0.0.1:%d" % port)
    rc = dashboard.serve_all(roadmap._dashboard_api(), open_browser=False)
    assert rc == 0
    assert "roadmap home already running" in capsys.readouterr().out


# --- the page: home cards and #/p/<slug>/ routing (step 3) -------------------

_DOM = r"""
class Node { constructor(tag){ this.tag=tag; this.kids=[]; this.className="";
  this._t=""; this.href=""; this.title=""; this.style={}; }
  appendChild(c){ this.kids.push(c); return c; }
  set textContent(s){ this._t=String(s); this.kids=[]; }
  get textContent(){ return this._t + this.kids.map(k=>k.textContent).join(""); } }
const el = (tag,cls) => { const e=new Node(tag); if(cls) e.className=cls; return e; };
const txt = (tag,cls,s) => { const e=el(tag,cls); e.textContent=s; return e; };
const age = iso => iso ? "2h ago" : "";
const document = {querySelector: () => ({content: "all"})};
"""


def _run_page_js(dashboard, tmp_path, tail):
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    body = dashboard._dashboard_html()
    start = body.index("const ALLMODE")
    end = body.index("function loadHome", start)
    js = tmp_path / "home.js"
    js.write_text(_DOM + body[start:end] + tail)
    return json.loads(subprocess.run([node, str(js)], capture_output=True, text=True,
                                     check=True).stdout)


def test_page_routes_and_prefixes(dashboard, tmp_path):
    res = _run_page_js(dashboard, tmp_path, """
const out = {};
out.home = [projOf(""), projOf("#/"), projOf("#/projects"), projOf("#/plan/3")];
out.proj = [projOf("#/p/alpha/plan/3"), projOf("#/p/alpha"), projOf("#/p/my%20app/notes/.roadmap/notes/x.md"),
            projOf("#/p/%E0%A4%A/"), projOf("#/p/alpha/digest/1w")];
out.noProj = [R("#/plan/3"), API()];
PROJ = "alpha";
out.withProj = [R("#/plan/3"), R("#/"), R("#/ideas"), R("#/projects"),
                R("#/p/alpha/plan/3"), R("https://x.test/a"), API()];
console.log(JSON.stringify(out));
""")
    home = {"slug": None, "hash": "#/projects"}
    assert res["home"] == [home] * 4
    assert res["proj"] == [
        {"slug": "alpha", "hash": "#/plan/3"}, {"slug": "alpha", "hash": "#/"},
        {"slug": "my app", "hash": "#/notes/.roadmap/notes/x.md"}, home,
        {"slug": "alpha", "hash": "#/digest/1w"}]
    assert res["noProj"] == ["#/plan/3", ""]
    assert res["withProj"] == ["#/p/alpha/plan/3", "#/p/alpha/", "#/p/alpha/ideas",
                               "#/projects", "#/p/alpha/plan/3", "https://x.test/a",
                               "/p/alpha"]


def test_page_home_cards(dashboard, tmp_path):
    res = _run_page_js(dashboard, tmp_path, """
const d = {projects: [
  {slug:"gone", name:"Gone", path:"/old/gone", exists:false, lastSeen:"2026-01-01T00:00:00Z"},
  {slug:"alpha", name:"Alpha", project:"Alpha", path:"/w/alpha", exists:true, version:"1.2.0",
   items:3, done:2, total:4, pct:50, inFlight:1, blocked:0, waiting:0,
   lastActivity:"2026-10-01T00:00:00Z", alerts:[{kind:"trunk", text:"trunk suite failing"}]},
  {slug:"beta", name:"Beta", project:"Beta", path:"/w/beta", exists:true, version:"0.1.0",
   items:1, done:0, total:2, pct:0, inFlight:0, blocked:0, waiting:0,
   lastActivity:"2026-10-20T00:00:00Z", alerts:[]}]};
const cards = homeNodes(d);
console.log(JSON.stringify({
  order: cards.map(c => c.kids[0].kids[0].textContent),
  tags: cards.map(c => [c.tag, c.className, c.href]),
  alpha: cards[1].textContent, gone: cards[2].textContent,
  empty: homeNodes({projects: []})[0].textContent}));
""")
    assert res["order"] == ["Beta", "Alpha", "Gone"]     # recent first, missing last
    assert res["tags"] == [["a", "pcard", "#/p/beta/"], ["a", "pcard", "#/p/alpha/"],
                           ["div", "pcard gone", ""]]
    assert "v1.2.0" in res["alpha"] and "50% (2/4)" in res["alpha"]
    assert "1 in flight" in res["alpha"] and "trunk suite failing" in res["alpha"]
    assert "projects --forget gone" in res["gone"]
    assert "no projects registered" in res["empty"]


def test_page_hooks_present(dashboard):
    body = dashboard._dashboard_html()
    assert '<meta name="roadmap-mode" content="project">' in body
    for hook in ('<div id="projects" hidden>', 'id="homelink"',
                 "parseRoute(enterProject(location.hash))",
                 'if(ROUTE.name === "projects"){ showHome(); return; }',
                 "href = R(href)", "fetch(API()+url", 'new EventSource(API()+"/events")',
                 'location.hash = R(href)', 'location.hash = R("#/digest/"'):
        assert hook in body, hook
    assert ".innerHTML" not in body
