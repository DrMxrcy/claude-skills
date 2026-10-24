"""Dashboard lane board (plan 37): #/board columns per lane, cards, copy-command
lines and the filter chips shared with the list. The page JS runs in node
against a tiny fake DOM; the board stays read-only (no write endpoint)."""
import json
import shlex
import shutil
import subprocess
import urllib.error
import urllib.request

import pytest

# A fake DOM just big enough for the dashboard's builders: elements carry
# className / text / kids / properties, and getElementById hands out one
# element per id.
_DOM = r"""
class Node { constructor(tag){ this.tag=tag; this.kids=[]; this.className="";
    this._t=""; this.title=""; this.dataset={}; this.style={}; this.attrs={};
    this.listeners={}; this.value=""; this.hidden=false; }
  appendChild(c){ this.kids.push(c); return c; }
  append(...cs){ for(const c of cs) this.kids.push(c); }
  replaceChildren(...cs){ this.kids = cs; this._t = ""; }
  get childNodes(){ return this.kids; }
  get firstChild(){ return this.kids[0]; }
  get lastChild(){ return this.kids[this.kids.length-1]; }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  addEventListener(ev,f){ (this.listeners[ev] ||= []).push(f); }
  get classList(){ const n=this; const has = c => n.className.split(/\s+/).includes(c);
    return { contains: has,
      add(c){ if(!has(c)) n.className = (n.className+" "+c).trim(); },
      toggle(c,on){ if(on === undefined) on = !has(c);
        n.className = n.className.split(/\s+/).filter(x => x && x !== c)
          .concat(on ? [c] : []).join(" "); return on; } }; }
  set textContent(s){ this._t=String(s); this.kids=[]; }
  get textContent(){ return this._t + this.kids.map(k=>k.textContent).join(""); }
  all(){ return [this, ...this.kids.flatMap(k => k.all ? k.all() : [])]; }
  find(cls){ return this.all().filter(n => (n.className||"").split(/\s+/).includes(cls)); }
  querySelector(sel){ return this.find(sel.replace(/^\./,""))[0] || null; } }
const IDS = {};
const document = { createElement: t => new Node(t), createElementNS: (ns,t) => new Node(t),
  createTextNode: s => { const n = new Node("#text"); n._t = String(s); return n; },
  getElementById: id => IDS[id] ||= new Node("div"), body: new Node("body"),
  documentElement: new Node("html"), title: "", hidden: false,
  addEventListener(){}, querySelector: () => null };
const window = { addEventListener(){}, scrollTo(){}, scrollY: 0 };
const location = { hash: "", search: "", pathname: "/" };
const history = { replaceState(){} };
const setInterval = () => 0;
const LS = {};
const localStorage = { getItem: k => k in LS ? LS[k] : null,
  setItem: (k,v) => { LS[k] = String(v); }, removeItem: k => { delete LS[k]; } };
"""


def _script(dashboard):
    """The whole page script minus its start-up calls (no route, no SSE)."""
    body = dashboard._dashboard_html()
    # The main page script is the last inline block (plan 50 added a tiny
    # pre-paint theme script in <head> before it).
    js = body[body.rindex("<script>") + len("<script>"):body.rindex("</script>")]
    boot = js.rindex("onRoute();")
    return js[:boot] + js[boot:].replace("onRoute();", "").replace("connect();", "")


def _run(dashboard, tmp_path, js, pre=""):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    f = tmp_path / "board.js"
    f.write_text(_DOM + pre + _script(dashboard) + "\nROUTE = {name:'board'};\n" + js)
    out = subprocess.run([node, str(f)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _item(i, lane, **kw):
    return {"id": i, "title": f"Item {i}", "type": "feature", "version": "0.1.0",
            "status": "done" if lane == "done" else "planned", "lane": lane,
            "done": 0, "total": 2, "pct": 0, **kw}


ALL_LANES = ["planned", "active", "building", "review", "fixing", "gate-ready",
             "gating", "landed", "waiting", "done", "blocked", "stale"]


def test_board_puts_each_item_in_exactly_its_lane_column(dashboard, tmp_path):
    items = [_item(i + 1, lane) for i, lane in enumerate(ALL_LANES)]
    items.append(_item(99, "someday"))         # unknown lane: own column at the end
    res = _run(dashboard, tmp_path, f"""
const items = {json.dumps(items)};
const cols = boardColumns(items, "");
console.log(JSON.stringify(cols.map(c => [c.lane, c.flagged, c.items.map(i => i.id)])));
""")
    lanes = [c[0] for c in res]
    assert lanes == ALL_LANES + ["someday"]
    placed = [i for c in res for i in c[2]]
    assert sorted(placed) == sorted(it["id"] for it in items)     # exactly once each
    for lane, _, ids in res:
        assert all(next(x for x in items if x["id"] == i)["lane"] == lane for i in ids)
    assert [c[0] for c in res if c[1]] == ["blocked", "stale"]


def test_board_hides_empty_optional_columns_and_honours_lane_filter(dashboard, tmp_path):
    items = [_item(1, "planned"), _item(2, "review")]
    res = _run(dashboard, tmp_path, f"""
const items = {json.dumps(items)};
console.log(JSON.stringify([boardColumns(items, "").map(c => c.lane),
  boardColumns(items.filter(i => i.lane === "review"), "review").map(c => c.lane)]));
""")
    assert res[0] == ["planned", "building", "review", "fixing", "gate-ready",
                      "gating", "landed", "done"]
    assert res[1] == ["review"]


def test_board_done_column_shows_last_20_with_show_all(dashboard, tmp_path):
    items = [_item(i, "done") for i in range(1, 26)]
    res = _run(dashboard, tmp_path, f"""
const d = {{items: {json.dumps(items)}}};
renderBoard(d);
const col = () => IDS.board.find("bcol").find(c => c.dataset.lane === "done");
const cards = () => col().find("bcard").map(c => c.find("num")[0].textContent);
const more = () => col().find("lnk")[0];
const first = [cards(), more().textContent];
more().onclick();
LAST = d; renderBoard(d);
console.log(JSON.stringify([first, cards().length, more().textContent]));
""")
    (first, label), n_all, label_all = res
    assert first == [f"#{i}" for i in range(25, 5, -1)]           # newest 20
    assert label == "show all 25" and n_all == 25 and label_all == "show last 20"


def test_dashboard_html_has_board_route_and_tab(dashboard):
    body = dashboard._dashboard_html()
    for hook in ('["board","Board"]', 'id="board"', "renderBoard(d)",
                 'head === "board"', "on-board", "// ---- lane board (plan 37)",
                 "// ---- end lane board (plan 37)"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
    assert "outerHTML" not in body


# --- cards and copy commands (step 2) --------------------------------------

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def proj(roadmap, repo, monkeypatch):
    """Item 1 on `roadmap/1` (two tagged commits ahead of main), item 2 untouched."""
    import importlib
    monkeypatch.chdir(repo)
    monkeypatch.setenv("ROADMAP_OWNER", "alice")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(repo, "commit", "--allow-empty", "-qm", "init")
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])
    roadmap.main(["new", "--type", "bug", "--title", "Second thing"])
    importlib.import_module("rmlib.branches")._CACHE.clear()
    _git(repo, "checkout", "-qb", "roadmap/1")
    for msg in ("build a (plan 1)", "build b (plan 1)"):
        _git(repo, "commit", "--allow-empty", "-qm", msg)
    _git(repo, "checkout", "-q", "main")
    return roadmap, repo


def _status(roadmap, repo):
    import importlib
    importlib.import_module("rmlib.branches")._CACHE.clear()
    return roadmap.status(repo)


def _card(dashboard, tmp_path, status, item_id):
    return _run(dashboard, tmp_path, f"""
const d = {json.dumps(status)};
const it = d.items.find(i => i.id === {item_id});
const c = boardCard(it, d);
const one = cls => (c.find(cls)[0] || {{textContent:null}}).textContent;
console.log(JSON.stringify({{text: c.textContent, num: one("num"), bname: one("bname"),
  sha: one("sha"), verdict: one("verdict"), owner: one("owner"), note: one("bnote"),
  cmd: one("bcmd"), opts: c.find("bmove").flatMap(s => s.kids.map(o => o.value)),
  badges: c.find("badge").map(b => b.textContent), href: c.find("bt")[0].kids[0].href}}));
""")


def test_card_fields_match_api_status(dashboard, proj, tmp_path):
    roadmap, repo = proj
    roadmap.main(["claim", "1", "--stage", "review", "--verdict", "PARTIAL",
                  "--note", "<b>fix</b> the & edge"])
    st = _status(roadmap, repo)
    it = next(i for i in st["items"] if i["id"] == 1)
    card = _card(dashboard, tmp_path, st, 1)
    assert card["num"] == it["displayId"]
    assert card["bname"] == it["branch"]["name"] == "roadmap/1"
    assert card["sha"] == it["branch"]["lastCommit"] == it["branch"]["sha"][:7]
    assert card["verdict"] == it["claim"]["verdict"] == "PARTIAL"
    assert card["owner"] == "owner " + it["claim"]["owner"] == "owner alice"
    assert card["note"].startswith("<b>fix</b> the & edge · claimed ")  # text, not HTML
    assert card["href"] == "#/plan/1"
    assert card["badges"][:2] == ["feature", "v" + it["version"]]
    # review with a PARTIAL verdict: the suggested move is back to fixing
    assert card["cmd"] == "roadmap.py claim 1 --stage fixing"


def test_card_badges_slot_waiting_acceptance_found_in(dashboard, tmp_path):
    item = _item(7, "waiting", foundIn=3, acceptance={"met": 2, "failed": 0, "total": 5},
                 waitingSteps=[{"step": 2, "text": "soak", "until": "2000-01-01"}])
    d = {"items": [item], "slots": {"kinds": [{"kind": "migration", "reservations": [
        {"plan": 7, "numbers": ["0269"], "value": "0269_x", "state": "ok",
         "detail": "free"}]}]}}
    card = _card(dashboard, tmp_path, d, 7)
    assert "waiting · " in card["text"] and "overdue" in card["text"]
    assert "migration 0269" in card["text"]
    assert "2/5 accepted" in card["badges"] and "from #3" in card["badges"]
    assert card["cmd"] is None and card["opts"] == []     # waiting: no claim move


def test_board_moves_cover_every_lane(dashboard, tmp_path):
    rows = [_item(1, "building"), _item(2, "review", claim={"stage": "review"}),
            _item(3, "review", claim={"stage": "review", "verdict": "CONFIRMED"}),
            _item(4, "fixing", claim={"stage": "fixing"}),
            _item(5, "gate-ready", claim={"stage": "gate-ready"}),
            _item(6, "gating", claim={"stage": "gating"}),
            _item(7, "blocked", claim={"stage": "blocked"}),
            _item(8, "done"), _item(9, "stale")]
    res = _run(dashboard, tmp_path, f"""
console.log(JSON.stringify({json.dumps(rows)}.map(i => boardMoves(i).map(m => m.cmd))));
""")
    first = [m[0] if m else None for m in res]
    assert first == ["roadmap.py claim 1 --stage review",
                     "roadmap.py claim 2 --stage gate-ready --verdict CONFIRMED",
                     "roadmap.py claim 3 --stage gate-ready",
                     "roadmap.py claim 4 --stage review",
                     "roadmap.py claim 5 --stage gating",
                     "roadmap.py claim 6 --stage landed",
                     "roadmap.py claim 7 --clear",
                     None,
                     "roadmap.py claim 9 --stage review"]
    for moves in res:
        assert len(moves) == len(set(moves))
    # never offers the stage the card is already in
    assert not any("--stage fixing" in m for m in res[3])


def test_board_stages_mirror_cli(dashboard, tmp_path, roadmap):
    from rmlib.parse import CLAIM_STAGES
    assert _run(dashboard, tmp_path, "console.log(JSON.stringify(BOARD_STAGES));") \
        == list(CLAIM_STAGES)


def test_copied_claim_lines_run_and_move_the_card(dashboard, proj, tmp_path):
    """Following the suggested line from each column walks the item through
    the pipeline; every alternative line from one card is a valid claim too."""
    roadmap, repo = proj

    def moves(item_id):
        st = _status(roadmap, repo)
        return st, _run(dashboard, tmp_path, f"""
const d = {json.dumps(st)};
console.log(JSON.stringify(boardMoves(d.items.find(i => i.id === {item_id}))));
""")

    def run(cmd):
        argv = shlex.split(cmd)
        assert argv[:2] == ["roadmap.py", "claim"]
        roadmap.main(argv[1:])

    lane = lambda: next(i for i in _status(roadmap, repo)["items"] if i["id"] == 1)["lane"]
    assert lane() == "building"
    for expect in ("review", "gate-ready", "gating", "landed"):
        _, ms = moves(1)
        run(ms[0]["cmd"])
        assert lane() == expect, ms[0]
    _, ms = moves(1)
    for m in ms:                            # each alternative from 'landed'
        run(m["cmd"])
        target = m["cmd"].split("--stage ")[1] if "--stage" in m["cmd"] else "building"
        assert lane() == target, m
        roadmap.main(["claim", "1", "--stage", "landed"])


def test_no_endpoint_accepts_writes(roadmap, repo, monkeypatch, dashboard):
    import http.server
    import threading
    import time
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "First thing"])
    holder = {}
    orig = http.server.ThreadingHTTPServer

    class Capturing(orig):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            holder["srv"] = self

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capturing)
    threading.Thread(target=lambda: roadmap.serve(repo, port=None, open_browser=False),
                     daemon=True).start()
    for _ in range(100):
        if "srv" in holder:
            break
        time.sleep(0.02)
    base = f"http://127.0.0.1:{holder['srv'].server_address[1]}"
    try:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in ("/", "/api/status", "/api/item?id=1", "/api/claim"):
                req = urllib.request.Request(base + path, data=b"{}", method=method)
                with pytest.raises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(req, timeout=3)
                assert e.value.code == 501, (method, path)
    finally:
        holder["srv"].shutdown()
    src = (dashboard.__file__)
    handlers = [ln.strip() for ln in open(src) if ln.strip().startswith("def do_")]
    assert [h.split("(")[0] for h in handlers] == ["def do_GET"]


# --- shared filter chips (step 3) ------------------------------------------

def _chip_items():
    return [
        _item(1, "review", type="bug", claim={"stage": "review", "verdict": "PARTIAL"},
              branch={"name": "roadmap/1", "lastCommit": "aaaaaaa"}),
        _item(2, "review", claim={"stage": "review", "verdict": "CONFIRMED"},
              branch={"name": "roadmap/2", "lastCommit": "bbbbbbb"}),
        _item(3, "planned", type="bug", version="0.2.0"),
        _item(4, "done", version="0.2.0"),
        _item(5, "building", type="bug", branch={"name": "fix/x", "lastCommit": "ccccccc"}),
    ]


# Ids shown by the list (rendered rows) and by the board (cards) for one payload.
_SHOWN = r"""
const d = {items: ITEMS, currentVersion: "0.1.0"};
const ids = (root, cls, numCls) => IDS[root].find(cls)
  .map(n => n.find(numCls)[0].textContent);
function shown(){
  ROUTE = {name:"roadmap"}; render(d);
  const list = ids("app", "item", "num");
  ROUTE = {name:"board"}; render(d);
  return [list, ids("board", "bcard", "num")];
}
"""


def test_chips_filter_list_and_board_alike(dashboard, tmp_path):
    js = _SHOWN.replace("ITEMS", json.dumps(_chip_items())) + r"""
const out = [shown()];
chipToggle("type", "bug");             out.push(shown());
chipToggle("verdict", "");             // bugs with no verdict
out.push(shown());
chipToggle("verdict", "PARTIAL");      // OR within a group
out.push(shown());
chipToggle("branch", "roadmap/1");     // AND across groups
out.push(shown());
chipToggle("lane", "review");          out.push([shown(), FILT.lane]);
chipToggle("lane", "review");          // second click clears the lane
out.push(FILT.lane);
const chipText = IDS.chips.find("fchip").filter(b => b.className.includes("on"))
  .map(b => [b.textContent, b.attrs["aria-pressed"]]);
console.log(JSON.stringify([out, chipText, JSON.parse(LS["rm-filters"])]));
"""
    out, on, saved = _run(dashboard, tmp_path, js)
    every, bugs, bugs_unreviewed, bugs_or_partial, on_branch, (lane_only, lane), cleared = out
    for lst, board in (every, bugs, bugs_unreviewed, bugs_or_partial, on_branch):
        assert sorted(lst) == sorted(board)                  # list and board agree
    assert sorted(every[0]) == ["#1", "#2", "#3", "#4", "#5"]
    assert sorted(bugs[0]) == ["#1", "#3", "#5"]
    assert sorted(bugs_unreviewed[0]) == ["#3", "#5"]
    assert sorted(bugs_or_partial[0]) == ["#1", "#3", "#5"]
    assert on_branch[0] == ["#1"] and on_branch[1] == ["#1"]
    assert lane_only == [["#1"], ["#1"]] and lane == "review" and cleared == ""
    assert ["bug 3", "true"] in on and ["no verdict 3", "true"] in on
    assert ["roadmap/1 1", "true"] in on
    assert saved["type"] == ["bug"] and saved["verdict"] == ["", "PARTIAL"]
    assert saved["branch"] == ["roadmap/1"] and saved["lane"] == ""


def test_chips_persist_per_viewer_across_reload(dashboard, tmp_path):
    pre = 'LS["rm-filters"] = ' + json.dumps(json.dumps(
        {"open": False, "lane": "", "version": ["0.2.0"], "verdict": "junk"})) + ";\n"
    js = _SHOWN.replace("ITEMS", json.dumps(_chip_items())) + r"""
console.log(JSON.stringify([shown(), chipsActive(),
  IDS.chips.find("fchip").filter(b => b.className.includes("on")).map(b => b.textContent),
  IDS.chips.find("fchip").filter(b => b.textContent.startsWith("v")).map(b => b.textContent)]));
"""
    (lst, board), active, on, versions = _run(dashboard, tmp_path, js, pre=pre)
    assert sorted(lst) == sorted(board) == ["#3", "#4"]      # a non-array is ignored
    assert active is True and on == ["v0.2.0 2"]
    assert versions == ["v0.2.0 2", "v0.1.0 3"]              # newest version first


def test_chips_and_board_share_search_and_open_only(dashboard, tmp_path):
    js = _SHOWN.replace("ITEMS", json.dumps(_chip_items())) + r"""
FILT.open = true; const a = shown();
QUERY = "roadmap/"; const b = shown();
console.log(JSON.stringify([a, b]));
"""
    (a_list, a_board), (b_list, b_board) = _run(dashboard, tmp_path, js)
    assert sorted(a_list) == sorted(a_board) == ["#1", "#2", "#3", "#5"]
    assert sorted(b_list) == sorted(b_board) == ["#1", "#2"]


def test_dashboard_html_has_chip_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ('id="chips"', "if(!chipMatch(it)) return false;", "syncChips(items);",
                 'name !== "roadmap" && name !== "board"'):
        assert hook in body, hook
