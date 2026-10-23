"""Claim owners and the work-in-progress limit (plan 40)."""
import datetime
import json
import re
import shutil
import subprocess

import pytest


def _repo(roadmap, repo, monkeypatch, n=1, settings=None):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    for i in range(n):
        roadmap.new_item(repo, "feature", f"Item {i + 1}")
    if settings:
        cfg = roadmap.read_config(repo)
        cfg.setdefault("settings", {}).update(settings)
        roadmap.write_config(repo, cfg)
    return repo


def _plan(repo, plan_id):
    return next((repo / ".roadmap/plans").glob(f"{plan_id:03d}-*.md"))


def _age_claim(repo, plan_id, hours):
    """Rewrite the claim's refresh stamp to `hours` ago (a fixture-level edit)."""
    path = _plan(repo, plan_id)
    when = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = re.sub(r"^claim_refreshed: .*$", f"claim_refreshed: {when}",
                  path.read_text(), flags=re.M)
    path.write_text(text)


def _as(monkeypatch, owner):
    monkeypatch.setenv("ROADMAP_OWNER", owner)


# --- step 1: claim_owner, held check, --take, TTL ---------------------------

def test_held_claim_refuses_other_owner_until_take_or_ttl(roadmap, repo, monkeypatch,
                                                         capsys):
    _repo(roadmap, repo, monkeypatch, n=5)
    assert roadmap.main(["claim", "5", "--owner", "alice", "--stage", "review"]) == 0
    claim = roadmap.read_claim(_plan(repo, 5))
    assert claim["owner"] == "alice" and claim["refreshed"].endswith("Z")
    capsys.readouterr()

    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "5", "--stage", "review"]) == 1
    err = capsys.readouterr().err
    assert "held by alice" in err and "claimed" in err and "--take" in err
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "alice"     # untouched

    assert roadmap.main(["claim", "5", "--stage", "review", "--take"]) == 0
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "bob"

    _age_claim(repo, 5, 13)                                  # past the 12h default
    _as(monkeypatch, "carol")
    assert roadmap.main(["claim", "5", "--stage", "fixing"]) == 0
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "carol"


def test_claim_ttl_setting_and_zero_disables_holds(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch, settings={"claimTtlHours": 2})
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    _age_claim(repo, 1, 3)
    roadmap.set_claim(repo, 1, stage="fixing", owner="bob")     # 3h > 2h TTL
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "bob"
    cfg = roadmap.read_config(repo)
    cfg["settings"]["claimTtlHours"] = 0
    roadmap.write_config(repo, cfg)
    roadmap.set_claim(repo, 1, stage="gating", owner="carol")   # holds off
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "carol"


def test_same_owner_refreshes_case_insensitively(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="Alice")
    _age_claim(repo, 1, 5)
    before = roadmap.read_claim(_plan(repo, 1))["refreshed"]
    roadmap.set_claim(repo, 1, verdict="CONFIRMED", owner="alice")
    after = roadmap.read_claim(_plan(repo, 1))
    assert after["refreshed"] > before and after["verdict"] == "CONFIRMED"


def test_ownerless_claim_stays_claimable(roadmap, repo, monkeypatch):
    """Fails-if guard: a claim written before plan 40 (no owner) is never held."""
    _repo(roadmap, repo, monkeypatch)
    path = _plan(repo, 1)
    path.write_text(path.read_text().replace(
        "---\n", "---\nclaim_stage: review\nclaim_updated: 2026-10-23\n", 1))
    assert roadmap.read_claim(path)["owner"] is None
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "--stage", "fixing"]) == 0
    assert roadmap.read_claim(path)["owner"] == "bob"


def test_default_owner_is_git_user_name(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review")
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "t"    # fixture user.name


def test_default_owner_order(repo, monkeypatch):
    from rmlib import owners
    assert owners.default_owner(repo) == "t"
    monkeypatch.setenv("ROADMAP_OWNER", "  ci   bot ")
    assert owners.default_owner(repo) == "ci bot"
    monkeypatch.delenv("ROADMAP_OWNER")

    def no_git(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(owners.subprocess, "run", no_git)
    assert owners.default_owner(repo) is None
    monkeypatch.setenv("CLAUDECODE", "1")
    assert owners.default_owner(repo) == "claude"


def test_owner_only_claim_holds_without_a_stage(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    assert roadmap.main(["claim", "1", "--owner", "alice"]) == 0
    claim = roadmap.read_claim(_plan(repo, 1))
    assert claim["owner"] == "alice" and claim["stage"] is None
    row = roadmap.status(repo)["items"][0]
    assert row["lane"] == "planned" and roadmap.is_in_flight(row)
    capsys.readouterr()
    # Without --owner a new claim still needs a stage.
    roadmap.new_item(repo, "feature", "B")
    assert roadmap.main(["claim", "2", "--verdict", "CONFIRMED"]) == 1
    assert "--stage" in capsys.readouterr().err


def test_clear_refuses_other_owner_until_take(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "--clear"]) == 1
    assert "held by alice" in capsys.readouterr().err
    assert roadmap.read_claim(_plan(repo, 1)) is not None
    assert roadmap.main(["claim", "1", "--clear", "--take"]) == 0
    assert roadmap.read_claim(_plan(repo, 1)) is None
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    assert roadmap.main(["claim", "1", "--clear", "--owner", "alice"]) == 0


def test_multi_id_claim_all_or_nothing_on_hold(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=2)
    roadmap.set_claim(repo, 2, stage="review", owner="alice")
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "2", "--stage", "gating"]) == 1
    assert "#2 is held by alice" in capsys.readouterr().err
    assert roadmap.read_claim(_plan(repo, 1)) is None              # nothing written


def test_landed_and_take_flags_are_exclusive(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    for extra in (["--owner", "a"], ["--take"]):
        with pytest.raises(SystemExit):
            roadmap.main(["claim", "--landed", "HEAD", *extra])
    with pytest.raises(SystemExit):
        roadmap.main(["claim", "1", "--clear", "--stage", "review"])


def test_owner_round_trips_in_status_json(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    capsys.readouterr()
    assert roadmap.main(["status", "--json"]) == 0
    item = json.loads(capsys.readouterr().out)["items"][0]
    assert item["claim"]["owner"] == "alice"


# --- step 2: next skips held items, orient lists own holds -----------------

def test_next_skips_item_held_by_another_owner(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=2)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    _as(monkeypatch, "bob")
    capsys.readouterr()
    assert roadmap.main(["next"]) == 0
    out = capsys.readouterr()
    assert out.out.startswith("FEAT-2 ") and "skipping FEAT-1 (held by alice" in out.err
    assert roadmap.main(["next", "--force"]) == 0          # --force: deps only
    assert capsys.readouterr().out.startswith("FEAT-2 ")
    _as(monkeypatch, "alice")                              # own hold: not skipped
    assert roadmap.main(["next"]) == 0
    assert capsys.readouterr().out.startswith("FEAT-1 ")
    _as(monkeypatch, "bob")
    _age_claim(repo, 1, 13)                                # expired: free again
    assert roadmap.main(["next"]) == 0
    assert capsys.readouterr().out.startswith("FEAT-1 ")


def test_next_none_when_only_held_items_remain(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, owner="alice")
    assert roadmap.next_item(repo, owner="bob", quiet=True) is None
    assert roadmap.next_item(repo, owner="alice", quiet=True)["id"] == 1


def test_orient_lists_own_held_items(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=3)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    roadmap.set_claim(repo, 2, owner="alice")
    roadmap.set_claim(repo, 3, stage="fixing", owner="bob")
    _as(monkeypatch, "alice")
    payload = roadmap.orient(repo)
    assert payload["owner"] == "alice"
    assert [h["id"] for h in payload["held"]] == [1, 2]
    assert payload["next"]["id"] == 1                      # own hold is not skipped
    text = roadmap.format_orient(payload)
    assert "Held by you (alice): FEAT-1 Item 1 (review) · FEAT-2 Item 2 (planned)" in text
    assert "FEAT-3" not in text.split("Held by you")[1].splitlines()[0]
    _as(monkeypatch, "bob")
    payload = roadmap.orient(repo)
    assert [h["id"] for h in payload["held"]] == [3]
    assert payload["next"]["id"] == 3                      # 1 and 2 held by alice


def test_orient_without_holds_prints_no_line(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    payload = roadmap.orient(repo)
    assert payload["held"] == [] and "Held by you" not in roadmap.format_orient(payload)


# --- step 3: settings.wipLimit warning in CLI and dashboard -----------------

def _in_flight(roadmap, repo, n):
    for i in range(1, n + 1):
        roadmap.set_claim(repo, i, owner="alice")      # owner-only claim: in-flight


def test_status_warns_over_wip_limit(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=5, settings={"wipLimit": 3})
    _in_flight(roadmap, repo, 3)
    capsys.readouterr()
    assert roadmap.main(["status"]) == 0
    assert "wipLimit" not in capsys.readouterr().err        # at the limit: quiet
    roadmap.set_claim(repo, 4, stage="review", owner="alice")
    capsys.readouterr()
    assert roadmap.main(["status"]) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and err.startswith("warning: work in progress: 4 "
                                                   "in-flight items, over "
                                                   "settings.wipLimit (3)")
    assert roadmap.main(["status", "--json"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["wip"] == {"count": 4, "limit": 3, "over": True}
    assert out.err == ""


def test_next_and_orient_warn_over_wip_limit(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=5, settings={"wipLimit": 3})
    _in_flight(roadmap, repo, 4)
    _as(monkeypatch, "alice")
    capsys.readouterr()
    assert roadmap.main(["next"]) == 0
    assert capsys.readouterr().err.count("over settings.wipLimit (3)") == 1
    assert roadmap.main(["orient"]) == 0
    out = capsys.readouterr().out
    assert out.count("⚠ work in progress: 4 in-flight items") == 1
    assert roadmap.orient(repo)["wip"]["over"] is True
    assert roadmap.next_item(repo, quiet=True)["id"] == 1   # a warning, not a refusal


def test_no_wip_limit_means_no_payload_and_no_warning(roadmap, repo, monkeypatch,
                                                      capsys):
    _repo(roadmap, repo, monkeypatch, n=4)
    _in_flight(roadmap, repo, 4)
    assert "wip" not in roadmap.status(repo)
    assert "wip" not in roadmap.orient(repo)
    capsys.readouterr()
    assert roadmap.main(["status"]) == 0
    assert "wipLimit" not in capsys.readouterr().err
    for junk in (0, -2, "x", True):
        cfg = roadmap.read_config(repo)
        cfg.setdefault("settings", {})["wipLimit"] = junk
        roadmap.write_config(repo, cfg)
        assert "wip" not in roadmap.status(repo)


def test_merged_view_carries_trunk_wip(dashboard):
    wip = {"count": 4, "limit": 3, "over": True}
    st = [{"project": "p", "currentVersion": "0.1.0", "trunk": "main", "items": []},
          {"project": "p", "currentVersion": "0.1.0", "trunk": "main", "items": [],
           "wip": wip}]
    meta = [{"branch": "roadmap/1", "name": "a"}, {"branch": "main", "name": "b"}]
    assert dashboard._merge_status(st, meta)["wip"] == wip
    assert "wip" not in dashboard._merge_status(
        [{"items": []}], [{"branch": "main", "name": "a"}])


def test_dashboard_html_has_owner_and_wip_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ("function wipFlag", "wipFlag(chip(k.fly", "d.wip", ".chip.over",
                 '"owner "+c.owner', "c.refreshed"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body


_HARNESS = r"""
class Node { constructor(tag){ this.tag=tag; this.kids=[]; this.className="";
  this._t=""; this.title=""; }
  appendChild(c){ this.kids.push(c); return c; }
  get lastChild(){ return this.kids[this.kids.length-1]; }
  set textContent(s){ this._t=String(s); this.kids=[]; }
  get textContent(){ return this._t + this.kids.map(k=>k.textContent).join(""); } }
const el = (tag,cls) => { const e=new Node(tag); if(cls) e.className=cls; return e; };
const txt = (tag,cls,s) => { const e=el(tag,cls); e.textContent=s; return e; };
const chip = (n,label,cls) => { const c = el("span","chip");
  c.appendChild(el("span","cdot"+(cls?" "+cls:""))); c.appendChild(txt("span",null, n+" "+label));
  return c; };
"""


def test_dashboard_header_flags_wip_over_limit(dashboard, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    body = dashboard._dashboard_html()
    start = body.index("// settings.wipLimit (plan 40)")
    end = body.index("// ---- plan page", start)
    js = tmp_path / "wip.js"
    js.write_text(_HARNESS + body[start:end] + """
const show = c => [c.className, c.textContent, c.title];
console.log(JSON.stringify([
  show(wipFlag(chip(4,"in flight","lg-build"), 4, {count:4, limit:3, over:true})),
  show(wipFlag(chip(3,"in flight","lg-build"), 3, {count:3, limit:3, over:false})),
  show(wipFlag(chip(9,"in flight","lg-build"), 9, undefined)),
]));
""")
    out = subprocess.run([node, str(js)], capture_output=True, text=True, check=True)
    over, at, none = json.loads(out.stdout)
    assert over == ["chip over", "4 in flight (limit 3)",
                    "over settings.wipLimit (3) — finish or land one first"]
    assert at == ["chip", "3 in flight", ""] and none == ["chip", "9 in flight", ""]
