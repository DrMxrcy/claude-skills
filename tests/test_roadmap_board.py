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
  getElementById: id => IDS[id] ||= new Node("div"), body: new Node("body") };
"""


def _script(dashboard):
    body = dashboard._dashboard_html()
    s = body.index("// All text goes in via textContent")
    e = body.index('document.getElementById("search").addEventListener', s)
    ls = body.index("const SAFE_HREF")
    le = body.index("function renderTabs", ls)
    return body[s:e] + body[ls:le]


def _run(dashboard, tmp_path, js):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    f = tmp_path / "board.js"
    f.write_text(_DOM + _script(dashboard) + "\nlet ROUTE = {name:'board'};\n" + js)
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
