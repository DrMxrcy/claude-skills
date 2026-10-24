"""Plan 49: dashboard navigation — full-text search, version pages, dependency
graph, keyboard shortcuts / palette and copy-command buttons."""
import json
import shutil
import subprocess

import pytest

import test_roadmap_serve as srv
from test_roadmap_serve import served  # noqa: F401  (fixture)


def _body(dashboard):
    return dashboard._dashboard_html()


def _slice(body, start, end):
    i = body.index(start)
    return body[i:body.index(end, i)]


# A tiny DOM stand-in so page builders run under node: elements record tag,
# class, kids, text and the properties the page sets.
_DOM = r"""
class Node { constructor(tag){ this.tag=tag; this.kids=[]; this.className="";
  this._t=""; this.href=""; this.value=""; this.title=""; this.attrs={};
  this.dataset={}; this.style={}; this.type=""; this.placeholder=""; }
  appendChild(c){ this.kids.push(c); return c; }
  append(...cs){ cs.forEach(c => this.appendChild(c)); }
  addEventListener(){}
  setAttribute(k,v){ this.attrs[k]=String(v); }
  getAttribute(k){ return k in this.attrs ? this.attrs[k] : null; }
  get lastChild(){ return this.kids[this.kids.length-1]; }
  get childNodes(){ return this.kids; }
  set textContent(s){ this._t=String(s); this.kids=[]; }
  get textContent(){ return this._t + this.kids.map(k=>k.textContent).join(""); } }
const document = { createTextNode: s => { const n=new Node("#text"); n._t=String(s); return n; },
  createElement: t => new Node(t), createElementNS: (ns,t) => new Node(t) };
const el = (tag,cls) => { const e=new Node(tag); if(cls) e.className=cls; return e; };
const txt = (tag,cls,s) => { const e=el(tag,cls); e.textContent=s; return e; };
const link = (href,text,cls) => { const a=txt("a",cls||null,text); a.href=href; return a; };
const crumb = (h,l,p) => txt("div","crumb","← "+l+(p?" "+p:""));
const noteHref = p => "#/notes/" + encodeURIComponent(p).replace(/%2F/g, "/");
const find = (n, pred, out=[]) => { if(pred(n)) out.push(n); n.kids.forEach(k => find(k, pred, out)); return out; };
"""


def _node(tmp_path, name, js):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    f = tmp_path / name
    f.write_text(js)
    out = subprocess.run([node, str(f)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- step 1: full-text search ------------------------------------------------

def _fill(repo):
    pf = srv._plan_file(repo)
    pf.write_text(pf.read_text() + "\nThe frobnicator must stay idempotent.\n")


def test_api_search_finds_word_only_in_plan_body(served):
    base, roadmap, repo = served
    _fill(repo)
    code, d = srv._get_json(base + "/api/search?q=FROBNICATOR")
    assert code == 200 and d["q"] == "FROBNICATOR"
    assert d["total"] == 1 and not d["truncated"]
    h = d["hits"][0]
    assert h["kind"] == "plan" and h["id"] == 1 and h["title"] == "First thing"
    assert h["path"].startswith(".roadmap/plans/001-")
    assert h["snippet"] == "The frobnicator must stay idempotent."
    a, b = h["match"]
    assert h["snippet"][a:b].lower() == "frobnicator"
    assert h["version"] and h["type"] == "feature"


def test_api_search_covers_titles_ideas_and_notes(served):
    base, roadmap, repo = served
    roadmap.main(["idea", "--title", "a zebra-striped dashboard"])
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "design.md").write_text("# Design\n\nzebra crossing ahead\n")
    roadmap.main(["new", "--type", "feature", "--title", "Zebra mode"])
    code, d = srv._get_json(base + "/api/search?q=zebra")
    assert code == 200
    kinds = {(h["kind"], h.get("id"), h.get("idea"), h.get("path")) for h in d["hits"]}
    assert ("item", 2, None, None) in kinds
    assert ("note", None, None, ".roadmap/notes/design.md") in kinds
    idea = next(h for h in d["hits"] if h["kind"] == "idea")
    ideas = srv._get_json(base + "/api/ideas")[1]["bullets"]
    assert any(b["index"] == idea["idea"] and "zebra" in b["body"] for b in ideas)


def test_api_search_long_line_snippet_is_windowed(served):
    base, roadmap, repo = served
    pf = srv._plan_file(repo)
    pf.write_text(pf.read_text() + "\n" + "x" * 300 + " needle " + "y" * 300 + "\n")
    h = srv._get_json(base + "/api/search?q=needle")[1]["hits"][0]
    assert h["snippet"].startswith("…") and h["snippet"].endswith("…")
    assert len(h["snippet"]) < 200
    assert h["snippet"][h["match"][0]:h["match"][1]] == "needle"


def test_api_search_rejects_empty_and_long_queries(served):
    base, _, _ = served
    assert srv._get_json(base + "/api/search?q=")[1]["error"] == "empty query"
    assert srv._get_json(base + "/api/search")[1]["error"] == "empty query"
    assert srv._get_json(base + "/api/search?q=" + "a" * 300)[1]["error"] == "query too long"


def test_api_search_skips_symlinked_note_escape(served, tmp_path_factory):
    base, _, repo = served
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("topsecret value\n")
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "leak.md").symlink_to(outside)
    d = srv._get_json(base + "/api/search?q=topsecret")[1]
    assert d["hits"] == []


def test_api_search_does_not_write(served):
    base, _, repo = served
    _fill(repo)
    before = {p: p.read_bytes() for p in (repo / ".roadmap").rglob("*") if p.is_file()}
    srv._get_json(base + "/api/search?q=frobnicator")
    after = {p: p.read_bytes() for p in (repo / ".roadmap").rglob("*") if p.is_file()}
    assert before == after


def test_cli_search_scope_unchanged(roadmap, repo, monkeypatch):
    """The CLI keeps its scope; only the dashboard asks for notes files."""
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    notes = repo / ".roadmap" / "notes"
    notes.mkdir(exist_ok=True)
    (notes / "n.md").write_text("quokka\n")
    assert roadmap.search(repo, "quokka") == []
    assert [h["kind"] for h in roadmap.search(repo, "quokka", notes=True)] == ["note"]


def test_dashboard_search_page_hooks(dashboard):
    body = _body(dashboard)
    for hook in ('head === "search"', "function searchPage", "/api/search?q=",
                 'r.name === "search" ? searchPage(r)', "searchHref(e.target.value)"):
        assert hook in body, hook


def test_dashboard_search_nodes_group_and_highlight(dashboard, tmp_path):
    body = _body(dashboard)
    js = _DOM + _slice(body, "const searchHref", "function searchPage") + r"""
const d = {total:4, truncated:false, hits:[
  {kind:"plan", id:1, title:"First", path:".roadmap/plans/001-a.md", line:9,
   snippet:"say frob twice", match:[4,8]},
  {kind:"item", id:1, field:"note", title:"First", snippet:"frob it", match:[0,4]},
  {kind:"idea", idea:3, line:12, snippet:"…a frob idea", match:[3,7]},
  {kind:"note", path:".roadmap/notes/x.md", line:2, snippet:"frob", match:[0,4]}]};
const out = searchNodes(d, "frob", [{id:1, displayId:"FEAT-1", title:"First"}]);
const grps = out.filter(n => n.className === "hitgrp");
const marks = find({kids:out, tag:"", className:""}, n => n.tag === "mark").map(n => n.textContent);
const empty = searchNodes({}, "", []);
console.log(JSON.stringify({
  summary: out[2].textContent,
  heads: grps.map(g => [g.kids[0].kids[0].href, g.kids[0].kids[0].textContent]),
  rows: grps.map(g => g.kids.length - 1),
  marks, emptyLen: empty.length, emptyHint: empty[2].textContent}));
"""
    r = _node(tmp_path, "search.js", js)
    assert r["summary"] == "4 matches in 3 places for “frob”"
    assert r["heads"] == [["#/plan/1", "FEAT-1 First"], ["#/idea/3", "idea 3"],
                          ["#/notes/.roadmap/notes/x.md", ".roadmap/notes/x.md"]]
    assert r["rows"] == [2, 1, 1]
    assert r["marks"] == ["frob"] * 4
    assert r["emptyLen"] == 3 and r["emptyHint"] == "type a word and press Enter"


# --- step 2: version pages ---------------------------------------------------

def test_changelog_block_slices_one_version(dashboard):
    md = ("# Changelog\n\n## v0.2.10 — (in progress)\n\n- ten\n\n"
          "## v0.2.1 — 2026-01-02\n\n### ✨ New\n- one\n\n## v0.1.0\n\n- old\n")
    assert dashboard._changelog_block(md, "0.2.1") == \
        "## v0.2.1 — 2026-01-02\n\n### ✨ New\n- one"
    assert dashboard._changelog_block(md, "0.2.10").endswith("- ten")
    assert dashboard._changelog_block(md, "0.1.0") == "## v0.1.0\n\n- old"
    assert dashboard._changelog_block(md, "0.3.0") is None


def test_api_version_lists_items_and_changelog_preview(served):
    base, roadmap, repo = served
    roadmap.main(["new", "--type", "bug", "--title", "Second thing"])
    assert roadmap.main(["audience", "--plan", "1", "--to", "public"]) == 0
    assert roadmap.main(["note", "--plan", "1", "--text", "Shiny new thing"]) == 0
    v = roadmap.status(repo)["items"][0]["version"]
    code, d = srv._get_json(base + "/api/version?v=" + v)
    assert code == 200 and d["version"] == v and "error" not in d
    assert [i["id"] for i in d["items"]] == [1, 2]
    assert all(i.get("lane") for i in d["items"])
    assert d["total"] >= 2 and d["done"] == 0
    assert d["public"].startswith("## v" + v) and "(pending) Shiny new thing" in d["public"]
    assert "Second thing" not in d["public"]
    assert "Shiny new thing" in d["internal"] and "Second thing" in d["internal"]
    # a leading "v" is tolerated
    assert srv._get_json(base + "/api/version?v=v" + v)[1]["version"] == v


def test_api_version_unknown_and_missing(served):
    base, _, _ = served
    assert srv._get_json(base + "/api/version?v=9.9.9")[1]["error"] == "no items target v9.9.9"
    assert srv._get_json(base + "/api/version")[1]["error"] == "missing version"


def test_dashboard_version_page_hooks(dashboard):
    body = _body(dashboard)
    for hook in ('["versions","Versions"]', 'head === "version"', "function versionPage",
                 "/api/version?v=", 'r.name === "version" ? versionPage(r)',
                 '"#/version/"+v', "versionsPage()", "function cmdBlock",
                 "navigator.clipboard"):
        assert hook in body, hook


_VERSION_STUBS = r"""
const LANES = ["building","review","fixing","gate-ready","gating","landed","blocked",
  "stale","waiting","active","planned","done"];
const LANE_GROUP = {done:"done", review:"review", planned:"plan", waiting:"wait"};
const laneOf = it => it.lane || "planned";
const forecastTag = f => txt("span","vfc","forecast "+f.date);
const burnDown = f => null;
const itemRow = it => { const w = el("div","item-wrap"); w.appendChild(txt("div","item", "#"+it.id)); return w; };
const md = (s, p) => txt("div","md", s);
const getJSON = () => Promise.resolve({});
const rootParam = () => "root=0";
let LAST = null;
"""


def test_dashboard_version_nodes_group_by_lane(dashboard, tmp_path):
    body = _body(dashboard)
    js = _DOM + _VERSION_STUBS + _slice(body, "// Copy-command buttons", "function versionPage") + r"""
const d = {version:"0.21.0", currentVersion:"0.21.0", done:3, total:8,
  forecast:{date:"2026-11-02"}, items:[
    {id:3, version:"0.21.0", lane:"review", done:1, total:2},
    {id:1, version:"0.21.0", lane:"done", done:2, total:2},
    {id:2, version:"0.21.0", lane:"review", done:0, total:2},
    {id:4, version:"0.21.0", lane:"waiting", done:0, total:2}],
  public:"## v0.21.0 — (in progress)\n\n- (pending) x", internal:null};
const out = versionNodes(d);
const groups = out.filter(n => n.className === "lanegrp").map(g =>
  [g.kids[0].kids[0].textContent, g.kids.slice(1).map(k => k.textContent)]);
const cmds = find({kids:out}, n => n.tag === "code").map(n => n.textContent);
const prev = out.filter(n => n.className === "clprev").map(n => n.textContent);
const rows = versionRows([{version:"0.9.0", done:1, total:1, lane:"done"},
  {version:"0.10.0", done:0, total:2}, {version:"0.10.0", done:1, total:2}], "0.10.0", {});
console.log(JSON.stringify({groups, cmds, prev, head: out[1].textContent,
  rows: rows.map(r => [r.v, r.n, r.pct, r.open, r.current]),
  err: versionNodes({error:"no items target v1"}).map(n => n.textContent),
  quoted: sh("a b'c"), plain: sh("0.21.0")}));
"""
    r = _node(tmp_path, "ver.js", js)
    assert r["groups"] == [["review", ["#2", "#3"]], ["waiting", ["#4"]], ["done", ["#1"]]]
    assert r["cmds"] == ["roadmap.py next --version 0.21.0",
                         "roadmap.py release --version 0.21.0",
                         "roadmap.py release --version 0.21.0 --with-waiting"]
    assert r["prev"][0].startswith("changelog preview — public") and "(pending) x" in r["prev"][0]
    assert r["prev"][1].endswith("no internal entries")
    assert r["head"].startswith("v0.21.0current") and "38% · 3/8" in r["head"]
    assert r["rows"] == [["0.10.0", 2, 25, 2, True], ["0.9.0", 1, 100, 0, False]]
    assert r["err"] == ["← versions", "no items target v1"]
    assert r["quoted"] == "'a b'\\''c'" and r["plain"] == "0.21.0"


# --- step 3: dependency graph ------------------------------------------------

_GRAPH_STUBS = r"""
const LANE_GROUP = {done:"done", review:"review", planned:"plan", building:"build", blocked:"hold"};
const laneOf = it => it.lane || "planned";
const vkeyOf = v => String(v).split(".").map(n => parseInt(n,10)||0);
function vcmpDesc(a, b){ const A = vkeyOf(a), B = vkeyOf(b);
  for(let i = 0; i < Math.max(A.length, B.length); i++){ const d = (B[i]||0)-(A[i]||0); if(d) return d; }
  return 0; }
let LAST = null;
const location = {hash:""};
"""


def _graph_js(body):
    return _DOM + _GRAPH_STUBS + _slice(body, "const GRAPH = {", "function graphPage()")


def test_dashboard_graph_model_matches_depends_on(dashboard, tmp_path):
    js = _graph_js(_body(dashboard)) + r"""
const items = [
  {id:1, version:"0.1.0", lane:"done", title:"old base"},
  {id:2, version:"0.2.0", lane:"building", title:"core", dependsOn:[1]},
  {id:3, version:"0.2.0", lane:"planned", title:"ui", dependsOn:[2], blockedBy:[2]},
  {id:4, version:"0.2.0", lane:"planned", title:"docs", dependsOn:[2,3], blockedBy:[2,3]},
  {id:5, version:"0.2.0", lane:"planned", title:"loose"},
  {id:6, version:"0.2.0", lane:"done", title:"done dep"},
  {id:7, version:"0.2.0", lane:"review", title:"after done", dependsOn:[6]},
  {id:8, version:"0.3.0", lane:"planned", title:"cyc a", dependsOn:[9]},
  {id:9, version:"0.3.0", lane:"planned", title:"cyc b", dependsOn:[8]}];
const m = graphModel(items);
const nodes = m.nodes.map(n => [n.id, n.layer, n.cls, n.blocked, n.context]);
const edges = m.edges.map(e => [e.from, e.to, e.blocking, e.x1 < e.x2]);
const svg = graphSvg(m);
const gs = svg.kids.filter(k => k.tag === "g");
const ps = svg.kids.filter(k => k.tag === "path");
console.log(JSON.stringify({nodes, edges, loose:m.loose, versions:m.versions,
  w:m.width > 0, h:m.height > 0,
  svgNodes: gs.map(g => [g.attrs["data-id"], g.attrs["class"], g.attrs.tabindex]),
  svgEdges: ps.map(p => [p.attrs["data-from"], p.attrs["data-to"], p.attrs["class"]]),
  label: gs[0].kids.filter(k => k.tag === "text").map(k => k.textContent),
  empty: graphNodes([{id:1, version:"1", lane:"planned"}]).map(n => n.textContent)}));
"""
    r = _node(tmp_path, "graph.js", js)
    # Every dependsOn link of an open-version item is one edge, left to right.
    # A hand-edited cycle (8 <-> 9) is cut, not looped: 9 lands left of 8.
    assert sorted(r["edges"]) == sorted([
        [1, 2, False, True], [2, 3, True, True], [2, 4, True, True],
        [3, 4, True, True], [6, 7, False, True], [9, 8, True, True],
        [8, 9, True, False]])
    layers = {n[0]: n[1] for n in r["nodes"]}
    assert layers[1] == 0 and layers[2] == 1 and layers[3] == 2 and layers[4] == 3
    assert layers[6] == 0 and layers[7] == 1
    by = {n[0]: n for n in r["nodes"]}
    assert 5 not in by and r["loose"] == 1          # no edges: not drawn, counted
    assert by[1][4] is True and by[2][4] is False    # done dep in an older version: context
    assert by[3][3] is True and by[3][2] == "lg-plan" and by[2][2] == "lg-build"
    assert r["versions"] == ["0.3.0", "0.2.0"]
    assert r["w"] and r["h"]
    assert [n[0] for n in r["svgNodes"]] == [str(n[0]) for n in r["nodes"]]
    assert ["3", "gnode lg-plan blocked", "0"] in r["svgNodes"]
    assert ["2", "3", "gedge blocking"] in r["svgEdges"] and ["1", "2", "gedge"] in r["svgEdges"]
    assert r["label"] == ["#1 · done", "old base"]
    assert r["empty"][-1] == "no dependencies between open items"


def test_dashboard_graph_node_click_opens_plan(dashboard, tmp_path):
    js = _graph_js(_body(dashboard)).replace(
        "  addEventListener(){}",
        "  addEventListener(t,f){ (this.ev ||= {})[t] = f; }") + r"""
const m = graphModel([{id:2, version:"1", lane:"planned", title:"a"},
                      {id:3, version:"1", lane:"planned", title:"b", dependsOn:[2]}]);
const g = graphSvg(m).kids.filter(k => k.tag === "g")[1];
g.ev.click();
const a = location.hash;
location.hash = "";
let prevented = false;
g.ev.keydown({key:"Enter", preventDefault(){ prevented = true; }});
console.log(JSON.stringify([a, location.hash, prevented, g.attrs.role]));
"""
    assert _node(tmp_path, "gclick.js", js) == ["#/plan/3", "#/plan/3", True, "link"]


def test_dashboard_graph_page_hooks(dashboard):
    body = _body(dashboard)
    for hook in ('["graph","Graph"]', 'head === "graph"', 'r.name === "graph" ? graphPage()',
                 "function graphModel", "function graphSvg", "createElementNS(NS, tag)",
                 ".graph { overflow:auto; max-width:100%;"):
        assert hook in body, hook
    # the graph is drawn in-page: no chart/graph library is loaded
    assert "<script src" not in body
