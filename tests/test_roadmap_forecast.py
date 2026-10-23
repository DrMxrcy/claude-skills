"""Version forecast from recent pace (plan 44): rmlib/forecast.py, status payload
and text, dashboard hooks."""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

TODAY = datetime.date(2026, 10, 23)


@pytest.fixture
def fc(roadmap):
    import importlib
    mod = importlib.import_module("rmlib.forecast")
    mod._STEP_CACHE.clear()
    mod._GIT_CACHE.clear()
    return mod


def _ago(n, today=TODAY):
    return (today - datetime.timedelta(days=n)).isoformat()


def _plan_path(roadmap, repo, item_id):
    item = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == item_id)
    return repo / ".roadmap" / item["file"]


def _set_steps(roadmap, repo, item_id, steps):
    """Replace the plan's checklist with `steps`: each is None (open), a date string
    (checked, dated evidence line) or True (checked, no evidence)."""
    path = _plan_path(roadmap, repo, item_id)
    text = path.read_text()
    text = "\n".join(l for l in text.splitlines()
                     if not roadmap.STEP_RE.match(l) and "> evidence:" not in l)
    lines = [text, ""]
    for n, s in enumerate(steps, 1):
        lines.append(f"- [{'x' if s else ' '}] Step {n}: thing {n}")
        if isinstance(s, str):
            lines.append(f"  > evidence: pytest -q: ok ({s}) · tokens: 12")
    path.write_text("\n".join(lines) + "\n")


def _project(roadmap, repo, n_items=1, version=None):
    roadmap.init_project(repo, "P", claude_md=False)
    for k in range(n_items):
        roadmap.new_item(repo, "feature", f"Item {k + 1}", version=version)
    return repo


def _fc(roadmap, fc, repo, today=TODAY):
    cfg = roadmap.read_config(repo)
    return fc.forecast(repo, cfg, roadmap._progress_map(repo, cfg), today=today)


def _twenty_over_ten(today=TODAY):
    """20 ticks over the last 10 days, alternating 1 and 3 a day (mean 2, sd 1)."""
    out = []
    for d in range(10):
        out += [_ago(d, today)] * (1 if d % 2 else 3)
    return out


# ---- step 1: pace, forecast, range ---------------------------------------

def test_step_dates_reads_stamps_latest_wins_and_skips_fences(roadmap, repo, fc):
    _project(roadmap, repo)
    p = _plan_path(roadmap, repo, 1)
    p.write_text("---\nid: 1\n---\n"
                 "- [x] Step 1: a\n"
                 "  > evidence: ran (2026-10-01) (2026-10-02)\n"
                 "  > evidence: re-checked (2026-10-05) · tokens: 900\n"
                 "- [x] Step 2: b\n"
                 "- [ ] Step 3: c\n"
                 "  > evidence: stale from an undo (2026-10-04)\n"
                 "```\n- [x] fenced, not a step\n```\n"
                 "- [X] Step 4: d\n  > evidence: no stamp here\n")
    assert fc.step_dates(p) == [
        (True, datetime.date(2026, 10, 5)), (True, None),
        (False, datetime.date(2026, 10, 4)), (True, None)]


def test_twenty_ticks_over_ten_days_forecasts_fifteen_days_with_range(
        roadmap, repo, fc):
    _project(roadmap, repo)
    _set_steps(roadmap, repo, 1, _twenty_over_ten() + [None] * 30)
    ver = roadmap.read_config(repo)["currentVersion"]
    f = _fc(roadmap, fc, repo)[ver]
    assert f["state"] == "forecast" and f["remaining"] == 30
    assert (f["ticks"], f["windowDays"], f["pace"], f["sd"]) == (20, 10, 2.0, 1.0)
    assert f["days"] == 15 and f["date"] == _ago(-15)
    assert f["range"] == [_ago(-10), _ago(-30)]          # 30/(2+1) .. 30/(2-1)
    assert f["burndown"][0] == 50 and f["burndown"][-1] == 30
    assert len(f["burndown"]) == 11
    assert "30 steps left · 2/day · forecast" in fc.summary(f)


def test_window_caps_at_forecast_days_and_drops_older_ticks(roadmap, repo, fc):
    _project(roadmap, repo)
    old = [_ago(40)] * 10                       # long history: window is the full 14
    recent = [_ago(d) for d in range(7)]        # 7 ticks in the window
    _set_steps(roadmap, repo, 1, old + recent + [None] * 7)
    ver = roadmap.read_config(repo)["currentVersion"]
    f = _fc(roadmap, fc, repo)[ver]
    assert (f["ticks"], f["windowDays"], f["pace"]) == (7, 14, 0.5)
    assert f["days"] == 14
    cfg = roadmap.read_config(repo)
    cfg["settings"]["forecastDays"] = 3
    roadmap.write_config(repo, cfg)
    f = _fc(roadmap, fc, repo)[ver]
    assert (f["ticks"], f["windowDays"]) == (3, 3)
    assert f["state"] == "insufficient"
    cfg["settings"]["forecastDays"] = "junk"            # invalid → default 14
    roadmap.write_config(repo, cfg)
    assert _fc(roadmap, fc, repo)[ver]["windowDays"] == 14


def test_fewer_than_five_ticks_is_not_enough_history(roadmap, repo, fc):
    _project(roadmap, repo)
    _set_steps(roadmap, repo, 1, [_ago(0), _ago(1), _ago(2), _ago(3), None, None])
    ver = roadmap.read_config(repo)["currentVersion"]
    f = _fc(roadmap, fc, repo)[ver]
    assert f["state"] == "insufficient" and f["message"] == "not enough history"
    assert f["date"] is None and f["range"] is None and f["days"] is None
    assert "not enough history (4 ticks in 4d)" in fc.summary(f)


def test_zero_remaining_is_done_not_a_forecast(roadmap, repo, fc):
    _project(roadmap, repo, n_items=2)
    cfg = roadmap.read_config(repo)
    ver = cfg["currentVersion"]
    roadmap.retarget(repo, "9.0.0", plan_ids=[2])
    _set_steps(roadmap, repo, 1, _twenty_over_ten())             # fully ticked
    _set_steps(roadmap, repo, 2, [None] * 4)
    out = _fc(roadmap, fc, repo)
    assert out[ver]["state"] == "done" and out[ver]["date"] is None
    assert out[ver]["range"] is None and fc.summary(out[ver]) == "done"
    assert out["9.0.0"]["state"] == "forecast" and out["9.0.0"]["ahead"] == 0


def test_later_versions_queue_behind_earlier_open_ones(roadmap, repo, fc):
    _project(roadmap, repo, n_items=2)
    ver = roadmap.read_config(repo)["currentVersion"]
    roadmap.retarget(repo, "9.0.0", plan_ids=[2])
    _set_steps(roadmap, repo, 1, _twenty_over_ten() + [None] * 10)
    _set_steps(roadmap, repo, 2, [None] * 20)
    out = _fc(roadmap, fc, repo)
    assert list(out) == [ver, "9.0.0"]
    assert (out[ver]["days"], out["9.0.0"]["ahead"], out["9.0.0"]["days"]) == (5, 10, 15)
    assert "20 steps left (+10 ahead)" in fc.summary(out["9.0.0"])


def test_shipped_versions_below_current_are_omitted(roadmap, repo, fc):
    _project(roadmap, repo)
    roadmap.new_item(repo, "chore", "Old", version="0.0.0")    # below current 0.0.1
    _set_steps(roadmap, repo, 2, [_ago(1)])
    out = _fc(roadmap, fc, repo)
    assert "0.0.0" not in out and out["0.0.1"]["ticks"] == 1   # its ticks still count


@pytest.mark.parametrize("target_days,expect", [
    (20, "on track"),       # expected finish (15) before the target
    (12, "at risk"),        # expected after, fast end (10) still makes it
    (8, "late"),            # even the fast end misses
    (-1, "late"),           # target already passed with work left
])
def test_target_dates_grade_the_forecast(roadmap, repo, fc, target_days, expect):
    _project(roadmap, repo)
    _set_steps(roadmap, repo, 1, _twenty_over_ten() + [None] * 30)
    cfg = roadmap.read_config(repo)
    ver = cfg["currentVersion"]
    cfg["settings"]["versionTargets"] = {"v" + ver: _ago(-target_days)}
    roadmap.write_config(repo, cfg)
    f = _fc(roadmap, fc, repo)[ver]
    assert f["target"] == _ago(-target_days) and f["targetStatus"] == expect
    assert fc.summary(f).endswith(f"target {_ago(-target_days)}: {expect}")


def test_target_without_history_is_ungraded_until_it_passes(roadmap, repo, fc):
    _project(roadmap, repo)
    _set_steps(roadmap, repo, 1, [None] * 3)
    cfg = roadmap.read_config(repo)
    ver = cfg["currentVersion"]
    cfg["settings"]["versionTargets"] = {ver: _ago(-5), "bogus": "not-a-date"}
    roadmap.write_config(repo, cfg)
    assert _fc(roadmap, fc, repo)[ver]["targetStatus"] is None
    cfg["settings"]["versionTargets"] = {ver: _ago(2)}
    roadmap.write_config(repo, cfg)
    assert _fc(roadmap, fc, repo)[ver]["targetStatus"] == "late"


def _git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env.update(GIT_AUTHOR_DATE=f"{date}T12:00:00", GIT_COMMITTER_DATE=f"{date}T12:00:00")
    return subprocess.run(["git", *args], cwd=repo, check=True, env=env,
                          capture_output=True, text=True).stdout


def test_git_fallback_dates_undated_ticks_and_caches_on_head(roadmap, repo, fc,
                                                            monkeypatch):
    today = datetime.date.today()
    _project(roadmap, repo)
    path = _plan_path(roadmap, repo, 1)
    _set_steps(roadmap, repo, 1, [None] * 10)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "plan", date=_ago(30, today))
    # Tick 6 boxes over three commits with no evidence lines; reword a checked one.
    for k, n in ((5, 2), (3, 4), (1, 6)):
        _set_steps(roadmap, repo, 1, [True] * n + [None] * (10 - n))
        _git(repo, "commit", "-qam", f"tick {n}", date=_ago(k, today))
    path.write_text(path.read_text().replace("thing 1", "thing one"))
    _git(repo, "commit", "-qam", "reword", date=_ago(0, today))
    # One more tick, dated by evidence and committed the same day: counted once.
    text = path.read_text().replace("- [ ] Step 7: thing 7",
                                    f"- [x] Step 7: thing 7\n  > evidence: ok ({_ago(0, today)})")
    path.write_text(text)
    _git(repo, "commit", "-qam", "tick 7", date=_ago(0, today))

    calls = []
    real = fc._git
    monkeypatch.setattr(fc, "_git", lambda root, *a: calls.append(a[0]) or real(root, *a))
    ver = roadmap.read_config(repo)["currentVersion"]
    f = _fc(roadmap, fc, repo, today=today)[ver]
    assert (f["ticks"], f["remaining"], f["windowDays"]) == (7, 3, 6)
    assert f["state"] == "forecast"
    assert calls == ["rev-parse", "log"]
    _fc(roadmap, fc, repo, today=today)
    assert calls == ["rev-parse", "log", "rev-parse"]     # same HEAD: cached
    _git(repo, "commit", "-q", "--allow-empty", "-m", "moved")
    _fc(roadmap, fc, repo, today=today)
    assert calls[-2:] == ["rev-parse", "log"]               # HEAD moved: re-read


def test_no_git_no_undated_steps_never_shells_out(roadmap, tmp_path, fc, monkeypatch):
    _project(roadmap, tmp_path)                              # not a git repo
    _set_steps(roadmap, tmp_path, 1, _twenty_over_ten() + [True, None])
    calls = []
    monkeypatch.setattr(fc, "_git", lambda root, *a: calls.append(a) or None)
    ver = roadmap.read_config(tmp_path)["currentVersion"]
    assert _fc(roadmap, fc, tmp_path)[ver]["ticks"] == 20  # undated tick: no git → skipped
    assert calls == [("rev-parse", "HEAD")]
    _set_steps(roadmap, tmp_path, 1, _twenty_over_ten() + [None])
    calls.clear()
    _fc(roadmap, fc, tmp_path)
    assert calls == []


def test_plan_file_older_than_window_skips_git(roadmap, repo, fc, monkeypatch):
    _project(roadmap, repo)
    path = _plan_path(roadmap, repo, 1)
    _set_steps(roadmap, repo, 1, _twenty_over_ten() + [True, None])
    old = datetime.datetime(2020, 1, 1).timestamp()
    os.utime(path, (old, old))
    calls = []
    monkeypatch.setattr(fc, "_git", lambda root, *a: calls.append(a) or None)
    ver = roadmap.read_config(repo)["currentVersion"]
    assert _fc(roadmap, fc, repo)[ver]["ticks"] == 20
    assert calls == []

# ---- step 2: status payload and text ---------------------------------------

def test_status_payload_carries_forecast_per_open_version(roadmap, repo, fc):
    today = datetime.date.today()
    _project(roadmap, repo, n_items=2)
    ver = roadmap.read_config(repo)["currentVersion"]
    roadmap.retarget(repo, "9.0.0", plan_ids=[2])
    _set_steps(roadmap, repo, 1, _twenty_over_ten(today) + [None] * 30)
    _set_steps(roadmap, repo, 2, [None] * 3)
    cfg = roadmap.read_config(repo)
    cfg["settings"]["versionTargets"] = {ver: _ago(-60, today)}
    roadmap.write_config(repo, cfg)
    st = roadmap.status(repo)
    assert list(st["forecast"]) == [ver, "9.0.0"]
    f = st["forecast"][ver]
    assert (f["state"], f["remaining"], f["days"]) == ("forecast", 30, 15)
    assert f["targetStatus"] == "on track"
    assert st["forecast"]["9.0.0"]["ahead"] == 30


def test_status_text_prints_forecast_on_version_headers(roadmap, repo, fc,
                                                        monkeypatch, capsys):
    today = datetime.date.today()
    monkeypatch.chdir(repo)
    _project(roadmap, repo, n_items=2)
    ver = roadmap.read_config(repo)["currentVersion"]
    roadmap.retarget(repo, "9.0.0", plan_ids=[2])
    _set_steps(roadmap, repo, 1, _twenty_over_ten(today) + [None] * 30)
    _set_steps(roadmap, repo, 2, [None, None])
    cfg = roadmap.read_config(repo)
    cfg["settings"]["versionTargets"] = {"9.0.0": _ago(-3, today)}
    roadmap.write_config(repo, cfg)
    capsys.readouterr()
    assert roadmap.main(["status"]) == 0
    lines = capsys.readouterr().out.splitlines()
    head = {l.split()[0]: l for l in lines if l.startswith("v")}
    assert head[f"v{ver}"] == (f"v{ver} — 30 steps left · 2/day · forecast "
                               f"{_ago(-15, today)} ({_ago(-10, today)}..{_ago(-30, today)})")
    assert head["v9.0.0"].startswith("v9.0.0 — 2 steps left (+30 ahead) · 2/day")
    assert head["v9.0.0"].endswith(f"target {_ago(-3, today)}: late")
    assert lines.index(f"v{ver}" + head[f"v{ver}"][len(ver) + 1:]) < \
        next(i for i, l in enumerate(lines) if l.startswith("  FEAT-1 "))

    _set_steps(roadmap, repo, 1, [_ago(0, today)] * 3 + [None])
    assert roadmap.main(["status", "--version", ver]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1] == f"v{ver} — 1 step left · not enough history (3 ticks in 1d)"
    assert out[2].startswith("  FEAT-1 ")

    _set_steps(roadmap, repo, 1, [_ago(0, today)] * 3)
    assert roadmap.main(["status", "--version", ver]) == 0
    assert capsys.readouterr().out.splitlines()[1] == f"v{ver} — done"


# ---- step 3: dashboard -------------------------------------------------------

def test_dashboard_html_has_forecast_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ("LAST.forecast", "forecastTag(fc)", "burnDown(fc)",
                 "createElementNS", '"polyline"', "not enough history"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body


def test_merged_view_carries_trunk_forecast(dashboard):
    fc_main = {"0.1.0": {"state": "forecast", "date": "2026-11-07"}}
    st = [{"project": "p", "currentVersion": "0.1.0", "trunk": "main",
           "items": [], "forecast": {"0.1.0": {"state": "insufficient"}}},
          {"project": "p", "currentVersion": "0.1.0", "trunk": "main",
           "items": [], "forecast": fc_main}]
    meta = [{"branch": "roadmap/1", "name": "a"}, {"branch": "main", "name": "b"}]
    assert dashboard._merge_status(st, meta)["forecast"] == fc_main
    assert "forecast" not in dashboard._merge_status(
        [{"items": []}], [{"branch": "main", "name": "a"}])


_NODE_HARNESS = r"""
class Node { constructor(tag){ this.tag=tag; this.kids=[]; this.attrs={};
  this.className=""; this._t=""; this.title=""; }
  appendChild(c){ this.kids.push(c); return c; }
  setAttribute(k,v){ this.attrs[k]=String(v); }
  set textContent(s){ this._t=String(s); }
  get textContent(){ return this._t + this.kids.map(k=>k.textContent).join(""); } }
const document = { createElement: t => new Node(t),
  createElementNS: (ns,t) => new Node(t),
  createTextNode: s => { const n = new Node("#text"); n._t = String(s); return n; } };
const el = (tag,cls) => { const e=document.createElement(tag); if(cls) e.className=cls; return e; };
const txt = (tag,cls,s) => { const e=el(tag,cls); e.textContent=s; return e; };
"""


def _run_dashboard_js(dashboard, tmp_path, expr):
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    body = dashboard._dashboard_html()
    start = body.index("// Version forecast (plan 44)")
    end = body.index("\n// Unmerged branches", start)
    js = tmp_path / "fc.js"
    js.write_text(_NODE_HARNESS + body[start:end] + "\nconsole.log(JSON.stringify(" +
                  expr + "));\n")
    out = subprocess.run([node, str(js)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_dashboard_header_shows_forecast_and_target(dashboard, tmp_path):
    f = {"state": "forecast", "date": "2026-11-07", "range": ["2026-11-02", None],
         "remaining": 30, "ahead": 0, "pace": 2, "windowDays": 10, "ticks": 20,
         "target": "2026-11-15", "targetStatus": "at risk",
         "burndown": [50, 47, 46, 43, 30]}
    res = _run_dashboard_js(dashboard, tmp_path, """[
      forecastTag(F).textContent, forecastTag(F).kids[1].className,
      forecastTag({state:"insufficient", remaining:3, pace:0.2, windowDays:14,
                   ticks:3}).textContent,
      forecastTag({state:"done"}).textContent,
      burnDown(F).textContent, burnDown(F).kids[0].kids[0].attrs.points,
      burnDown({state:"done", burndown:[1,0]})]""".replace("F", json.dumps(f)))
    assert res[0] == "forecast Nov 7 (Nov 2–?)at risk · Nov 15"
    assert res[1] == "tgt atrisk"
    assert res[2] == "not enough history" and res[3] == "done"
    assert res[4] == "burn-down, last 10d: 50 → 30 left · 2/day"
    assert res[5].startswith("0.0,2.0 ") and res[5].endswith("120.0,10.0")
    assert res[6] is None
