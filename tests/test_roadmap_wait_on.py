"""Plan 53: waits in hours (`--until 24h`) and open-ended waits on a person
(`--on "dispatch team"`), on top of plan 46's waiting steps."""
import datetime
import json

import pytest

TODAY = datetime.date.today()
UTC = datetime.timezone.utc


def _iso(days: int) -> str:
    return (TODAY + datetime.timedelta(days=days)).isoformat()


def _at(hours: float, now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now(UTC)
    return (now + datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")


def _plan(repo, n=1):
    return next((repo / ".roadmap/plans").glob(f"{n:03d}-*.md"))


def _item(roadmap, repo, steps=3, title="A", version=None):
    path = roadmap.new_item(repo, "feature", title, version)
    head, _, _ = path.read_text().partition("- [ ] Step 1:")
    body = "\n".join(f"- [ ] Step {k}: do thing {k}" for k in range(1, steps + 1))
    path.write_text(head + body + "\n")
    roadmap.sync(repo)
    return path


# ---- step 1: hours in --until, time-of-day due, hour countdowns ---------------

def test_parse_until_hours_and_utc_time(roadmap):
    now = datetime.datetime(2026, 10, 24, 9, 30, 45, tzinfo=UTC)
    assert roadmap.parse_until("24h", now=now) == "2026-10-25T09:30Z"
    assert roadmap.parse_until("72H", now=now) == "2026-10-27T09:30Z"
    assert roadmap.parse_until("0h", now=now) == "2026-10-24T09:30Z"
    assert roadmap.parse_until("2026-10-30T14:00Z") == "2026-10-30T14:00Z"
    # days, weeks and dates are unchanged (plan 46)
    today = datetime.date(2026, 10, 24)
    assert roadmap.parse_until("7d", today=today) == "2026-10-31"
    assert roadmap.parse_until("2w", today=today) == "2026-11-07"
    assert roadmap.parse_until("2026-10-30") == "2026-10-30"
    for bad in ("24", "3m", "2026-10-30T25:00Z", "2026-10-30 14:00", "tomorrow"):
        with pytest.raises(ValueError, match="--until"):
            roadmap.parse_until(bad)


def test_wait_24h_stores_utc_time_and_counts_in_hours(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    before = datetime.datetime.now(UTC)
    w = roadmap.wait_step(repo, 1, 2, until="24h", reason="soak")
    assert w["until"] in (_at(24, before), _at(24))
    assert f"- [~] Step 2: do thing 2 (waiting until {w['until']}: soak)" in path.read_text()
    parsed = roadmap.parse_plan(path)
    assert parsed["steps"][1] == (False, "Step 2: do thing 2")
    assert parsed["waiting"] == {2: {"until": w["until"], "reason": "soak"}}
    assert roadmap.count_progress(path) == (0, 3)
    roadmap.check_step(repo, 1, 1)
    roadmap.check_step(repo, 1, 3)
    st = roadmap.status(repo)
    row = st["items"][0]
    assert row["lane"] == "waiting" and row["status"] != "done"
    assert row["waitingSteps"][0]["hoursLeft"] == 24
    assert row["waitingSteps"][0]["daysLeft"] == 1
    assert roadmap.lane_label(row) == "waiting · step 2 · 24h left"
    assert st["waitingDue"] == []


def test_wait_left_hours_and_days(roadmap):
    now = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    today = datetime.date(2026, 10, 24)
    left = lambda until: roadmap.wait_left(until, today, now)
    assert left("2026-10-24T17:00Z") == (1, 5)          # 5h away: not due
    assert left("2026-10-24T12:01Z") == (1, 1)          # never "0h left"
    assert left("2026-10-24T12:00Z") == (0, 0)          # due
    assert left("2026-10-24T11:30Z") == (0, 0)          # first hour past: due
    assert left("2026-10-24T09:00Z") == (0, -3)         # 3h overdue
    assert left("2026-10-23T06:00Z") == (-1, -30)
    assert left("2026-10-27T12:00Z") == (3, 72)
    assert left("2026-10-31") == (7, None)              # dates: plan 46 unchanged
    assert left(None) == (None, None) and left("garbage") == (None, None)


def test_countdown_hours_under_two_days(roadmap):
    c = roadmap.countdown
    assert [c(1, 5), c(1, 1), c(0, 0), c(0, -3), c(1, 47), c(-1, -47)] == \
        ["5h left", "1h left", "due", "3h overdue", "47h left", "47h overdue"]
    assert [c(2, 48), c(3, 72), c(-2, -50)] == ["2d left", "3d left", "2d overdue"]
    # plan 46 calls (no hours) read exactly as before
    assert [c(d) for d in (4, 1, 0, -2, None)] == \
        ["4d left", "1d left", "due", "2d overdue", "no date"]


def test_hours_wait_due_and_overdue_in_reminders(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.check_step(repo, 1, 1)
    roadmap.check_step(repo, 1, 2)
    path = _plan(repo)
    path.write_text(path.read_text().replace(
        "- [ ] Step 3: do thing 3",
        f"- [~] Step 3: do thing 3 (waiting until {_at(-3.5)}: 24h soak)"))
    st = roadmap.status(repo)
    due = st["waitingDue"]
    assert [(d["id"], d["step"], d["daysLeft"], d["hoursLeft"]) for d in due] == \
        [(1, 3, 0, -3)]
    assert roadmap.next_item(repo, quiet=True)["id"] == 1        # due wait comes first
    roadmap.main(["orient"])
    out = capsys.readouterr().out
    assert "⏰ FEAT-1 step 3 (3h overdue: 24h soak) — Step 3: do thing 3" in out
    from rmlib import digest as rmdigest
    att = rmdigest.attention(repo, st)
    assert att[0]["kind"] == "waiting" and "3h overdue" in att[0]["text"]


def test_check_ends_an_hours_wait(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 3, until="24h")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.count_progress(path) == (2, 3)                 # never done early
    roadmap.check_step(repo, 1, 3, evidence="soak clean")
    assert "- [x] Step 3: do thing 3\n" in path.read_text()
    assert roadmap.status(repo)["items"][0]["lane"] == "done"


def test_old_style_markers_parse_and_count_as_before(roadmap, repo):
    """Marker strings exactly as plan 46 wrote them (tests/test_roadmap_waiting.py)."""
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo, steps=4)
    path.write_text(path.read_text()
                    .replace("- [ ] Step 1: do thing 1",
                             "- [x] Step 1: do thing 1")
                    .replace("- [ ] Step 2: do thing 2",
                             "- [~] Step 2: do thing 2 (waiting until 2030-01-02: soak)")
                    .replace("- [ ] Step 3: do thing 3",
                             "- [~] Step 3: do thing 3 (waiting until 2030-01-01: a: b (c))")
                    .replace("- [ ] Step 4: do thing 4",
                             "- [~] Step 4: do thing 4"))
    parsed = roadmap.parse_plan(path)
    assert parsed["steps"] == [(True, "Step 1: do thing 1"), (False, "Step 2: do thing 2"),
                               (False, "Step 3: do thing 3"), (False, "Step 4: do thing 4")]
    assert parsed["waiting"] == {2: {"until": "2030-01-02", "reason": "soak"},
                                 3: {"until": "2030-01-01", "reason": "a: b (c)"},
                                 4: {"until": None, "reason": None}}
    assert roadmap.count_progress(path) == (1, 4)
    row = roadmap.status(repo)["items"][0]
    days = (datetime.date(2030, 1, 2) - TODAY).days
    assert row["waitingSteps"][0] == {"step": 2, "text": "Step 2: do thing 2",
                                      "until": "2030-01-02", "reason": "soak",
                                      "daysLeft": days}
    assert row["waitingSteps"][2] == {"step": 4, "text": "Step 4: do thing 4",
                                      "until": None, "reason": None, "daysLeft": None}
    assert (row["done"], row["total"], row["waiting"], row["lane"]) == (1, 4, 3, "waiting")
    # text that only looks like a marker stays in the step, as before
    path.write_text(path.read_text().replace("- [x] Step 1: do thing 1",
                                             "- [ ] Step 1: do thing 1 (waiting)"))
    assert roadmap.parse_plan(path)["steps"][0] == (False, "Step 1: do thing 1 (waiting)")


# ---- step 2: --on open-ended waits, reminders, attention after waitNudgeDays --

def _awaiting_item(roadmap, repo, since_days=0, title="A", reason="user testing",
                   who="dispatch team"):
    """Item with steps 1-2 ticked and step 3 waiting on `who`, begun
    `since_days` ago (the marker's since-date is rewritten to simulate time)."""
    path = _item(roadmap, repo, title=title)
    n = roadmap.read_config(repo)["nextId"] - 1
    roadmap.wait_step(repo, n, 3, on=who, reason=reason)
    roadmap.check_step(repo, n, None, all_done=True)
    if since_days:
        path.write_text(path.read_text().replace(f"since: {_iso(0)}",
                                                 f"since: {_iso(-since_days)}"))
    return n


def test_wait_on_marks_open_ended_wait(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    w = roadmap.wait_step(repo, 1, 3, on="  dispatch   team ", reason="user testing")
    assert w == {"step": 3, "text": "Step 3: do thing 3", "until": None,
                 "reason": "user testing", "on": "dispatch team", "since": _iso(0)}
    assert (f"- [~] Step 3: do thing 3 (waiting on: dispatch team; since: {_iso(0)}: "
            f"user testing)") in path.read_text()
    parsed = roadmap.parse_plan(path)
    assert parsed["steps"][2] == (False, "Step 3: do thing 3")
    assert parsed["waiting"] == {3: {"until": None, "reason": "user testing",
                                     "on": "dispatch team", "since": _iso(0)}}
    assert roadmap.count_progress(path) == (0, 3)
    roadmap.check_step(repo, 1, None, all_done=True)                # never ticks the wait
    assert roadmap.count_progress(path) == (2, 3)
    st = roadmap.status(repo)
    row = st["items"][0]
    assert (row["lane"], row["status"]) == ("waiting", "active")
    assert row["waitingSteps"][0]["daysLeft"] is None               # never due
    assert row["waitingSteps"][0]["waitingDays"] == 0
    assert roadmap.lane_label(row) == "waiting · step 3 · awaiting dispatch team · 0d"
    assert st["waitingDue"] == [] and not st["versionComplete"]
    assert [(d["id"], d["step"], d["on"]) for d in st["waitingOn"]] == \
        [(1, 3, "dispatch team")]
    assert roadmap.next_item(repo, quiet=True) is None              # nothing to do yet
    assert roadmap.uncut_complete_version(repo) is None


def test_wait_on_with_until_is_a_dated_wait_naming_who(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    w = roadmap.wait_step(repo, 1, 3, until="2d", on="QA", reason="sign-off")
    assert (w["until"], w["on"], w["since"]) == (_iso(2), "QA", _iso(0))
    assert (f"(waiting until {_iso(2)}; on: QA; since: {_iso(0)}: sign-off)"
            in path.read_text())
    roadmap.check_step(repo, 1, None, all_done=True)
    st = roadmap.status(repo)
    assert roadmap.lane_label(st["items"][0]) == "waiting · step 3 · 2d left · awaiting QA"
    assert st["waitingOn"] == []                                    # dated: not open-ended
    path.write_text(path.read_text().replace(f"until {_iso(2)};", f"until {_iso(-1)};"))
    due = roadmap.status(repo)["waitingDue"]
    assert roadmap.format_due(due)[0].startswith(
        "⏰ FEAT-1 step 3 (1d overdue, awaiting QA: sign-off) — Step 3: do thing 3")


def test_wait_on_rerun_keeps_since_and_fields(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 2, on="dispatch team", reason="user testing")
    path.write_text(path.read_text().replace(f"since: {_iso(0)}", f"since: {_iso(-3)}"))
    w = roadmap.wait_step(repo, 1, 2, until="7d")                   # add a date
    assert (w["until"], w["on"], w["since"], w["reason"]) == \
        (_iso(7), "dispatch team", _iso(-3), "user testing")
    w = roadmap.wait_step(repo, 1, 2, on="dispatch team")           # same who: since kept
    assert (w["until"], w["since"]) == (_iso(7), _iso(-3))
    w = roadmap.wait_step(repo, 1, 2, on="ops")                     # new who: since restarts
    assert (w["on"], w["since"]) == ("ops", _iso(0))
    roadmap.wait_step(repo, 1, 2, clear=True)
    assert "- [ ] Step 2: do thing 2\n" in path.read_text()


def test_wait_on_refusals(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    for bad in ("", "   ", "team; qa", "team: qa"):
        with pytest.raises(ValueError, match="--on"):
            roadmap.wait_step(repo, 1, 1, on=bad)
    with pytest.raises(ValueError, match="--until .* or --on"):
        roadmap.wait_step(repo, 1, 1)


def test_awaiting_listed_in_orient_status_and_digest_never_overdue(roadmap, repo,
                                                                    monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _awaiting_item(roadmap, repo, since_days=3)
    st = roadmap.status(repo)
    assert st["waitingDue"] == [] and st["waitingOn"][0]["waitingDays"] == 3
    capsys.readouterr()
    roadmap.main(["orient"])
    out = capsys.readouterr().out
    line = (f"⏳ FEAT-1 step 3 awaiting dispatch team (since {_iso(-3)}, 3 days): "
            f"user testing — Step 3: do thing 3 → once they report back: "
            f"roadmap.py check --plan 1 --step 3")
    assert line in out and "overdue" not in out and "⏰" not in out
    roadmap.main(["status"])
    assert line in capsys.readouterr().out
    from rmlib import digest as rmdigest
    d = rmdigest.collect(repo, datetime.datetime.now(UTC) - datetime.timedelta(days=1))
    assert [r["text"] for r in d["awaiting"]] == [
        f"FEAT-1 A — step 3 awaiting dispatch team (since {_iso(-3)}, 3 days): user testing"]
    assert d["attention"] == []                                     # under waitNudgeDays
    assert "Awaiting (1)" in rmdigest.format_digest(d)
    assert any(s["key"] == "awaiting" for s in rmdigest.sections(d))


def test_awaiting_needs_attention_after_wait_nudge_days(roadmap, repo):
    roadmap.init_project(repo, "P")
    _awaiting_item(roadmap, repo, since_days=6, title="Six")
    _awaiting_item(roadmap, repo, since_days=7, title="Seven", who="QA", reason=None)
    from rmlib import digest as rmdigest
    st = roadmap.status(repo)
    assert [d["id"] for d in st["waitingOn"]] == [2, 1]            # longest first
    att = rmdigest.attention(repo, st)
    assert [(a["kind"], a["id"]) for a in att] == [("awaiting", 2)]
    assert att[0]["text"] == f"FEAT-2 Seven — step 3 awaiting QA (since {_iso(-7)}, 7 days)"
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {})["waitNudgeDays"] = 3
    roadmap.write_config(repo, cfg)
    assert [a["id"] for a in rmdigest.attention(repo, roadmap.status(repo))] == [2, 1]
    assert roadmap.wait_nudge_days({"settings": {"waitNudgeDays": "x"}}) == 7
    assert roadmap.wait_nudge_days({}) == 7


def test_check_ends_an_open_ended_wait(roadmap, repo):
    roadmap.init_project(repo, "P")
    _awaiting_item(roadmap, repo, since_days=9)
    roadmap.check_step(repo, 1, 3, evidence="dispatch team signed off")
    text = _plan(repo).read_text()
    assert "- [x] Step 3: do thing 3\n" in text and "waiting on" not in text
    st = roadmap.status(repo)
    assert st["items"][0]["lane"] == "done" and st.get("waitingOn", []) == []


def test_cli_wait_on(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    assert roadmap.main(["wait", "1", "--step", "3", "--on", "dispatch team",
                         "--reason", "user testing"]) == 0
    assert (f"#1 step 3: awaiting dispatch team since {_iso(0)} (user testing)"
            in capsys.readouterr().out)
    assert roadmap.main(["wait", "1", "--step", "2", "--until", "24h"]) == 0
    assert "#1 step 2: waiting until " in capsys.readouterr().out
    with pytest.raises(SystemExit):
        roadmap.main(["wait", "1", "--step", "3", "--clear", "--on", "x"])
    with pytest.raises(SystemExit):
        roadmap.main(["wait", "1", "--step", "1"])
    roadmap.main(["status", "--json"])
    st = json.loads(capsys.readouterr().out)
    assert st["waitingOn"][0]["on"] == "dispatch team"


# ---- step 3: follow-ups carry --on waits, dashboard badge and board ----------

def test_release_with_waiting_carries_on_wait_into_follow_up(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    _awaiting_item(roadmap, repo, since_days=4, title="Dispatch", reason=None)
    marker = f"(waiting on: dispatch team; since: {_iso(-4)})"
    with pytest.raises(ValueError, match="#1 step 3 \\(awaiting dispatch team\\)"):
        roadmap.release(repo, "0.0.2")
    made = roadmap.release(repo, "0.0.2", with_waiting=True)
    assert [(m["id"], m["title"], m["version"]) for m in made] == \
        [(2, "Follow-up: Dispatch — awaiting dispatch team", "0.0.2")]
    assert "→ follow-up #2 in v0.0.2" in capsys.readouterr().out
    fu = _plan(repo, 2).read_text()
    assert f"- [~] Step 1: do thing 3 {marker}\n" in fu
    assert "or on dispatch team" in fu
    w = roadmap.parse_plan(_plan(repo, 2))["waiting"][1]
    assert (w["on"], w["since"], w["until"]) == ("dispatch team", _iso(-4), None)
    st = roadmap.status(repo)
    assert st["items"][0]["lane"] == "done"
    assert [(d["id"], d["step"], d["waitingDays"]) for d in st["waitingOn"]] == [(2, 1, 4)]
    roadmap.check_step(repo, 2, 1, evidence="dispatch team signed off")
    assert roadmap.status(repo)["items"][1]["lane"] == "done"


def test_retarget_split_and_merge_carry_on_waits(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, title="A")
    roadmap.check_step(repo, 1, 1)
    roadmap.wait_step(repo, 1, 3, until="2030-01-01", on="QA", reason="sign-off")
    made = roadmap.retarget(repo, "0.0.2", plan_ids=[1], split=True)
    fu = _plan(repo, made[0]["id"]).read_text()
    assert (f"- [~] Step 2: do thing 3 (waiting until 2030-01-01; on: QA; since: "
            f"{_iso(0)}: sign-off)") in fu
    _item(roadmap, repo, title="B")
    roadmap.wait_step(repo, 3, 1, on="ops")
    roadmap.merge_items(repo, 2, [3])
    assert f"- [~] Step 1: do thing 1 (waiting on: ops; since: {_iso(0)})" \
        in _plan(repo, 2).read_text()


def test_dashboard_detail_carries_on_and_since(roadmap, repo, dashboard):
    roadmap.init_project(repo, "P")
    _awaiting_item(roadmap, repo, since_days=3)
    d = dashboard._item_detail(roadmap._dashboard_api(), repo, 1)
    assert d["steps"][2]["waiting"] == {"until": None, "reason": "user testing",
                                        "on": "dispatch team", "since": _iso(-3)}
    assert d["lane"] == "waiting"
    assert (d["waitingSteps"][0]["on"], d["waitingSteps"][0]["waitingDays"]) == \
        ("dispatch team", 3)


def test_dashboard_html_has_awaiting_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ("const hoursLeft", "const openEnded", "const awaitText",
                 '"awaiting "+w.on', "const waitText", 'h+"h left"',
                 '"waiting · "+countdown'):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node not installed")
def test_dashboard_wait_helpers_in_node(dashboard, tmp_path):
    import re
    import subprocess
    js = "\n".join(re.findall(r"<script>(.*?)</script>", dashboard._dashboard_html(), re.S))
    a = js.index("// <plan53-pure>")
    block = js[a:js.index("// </plan53-pure>", a)]
    at = lambda h: _at(h)
    harness = block + f"""
const assert = require("assert");
// plan 46 date waits read as before
assert.strictEqual(daysLeft({{until: "{_iso(4)}"}}), 4);
assert.strictEqual(countdown(4), "4d left");
assert.strictEqual(countdown(0), "due");
assert.strictEqual(countdown(-2), "2d overdue");
assert.strictEqual(countdown(null), "no date");
assert.strictEqual(hoursLeft({{until: "{_iso(4)}"}}), null);
// plan 53 hour waits
const soon = {{until: "{at(5.5)}"}}, late = {{until: "{at(-3.5)}"}}, far = {{until: "{at(80)}"}};
assert.strictEqual(hoursLeft(soon), 6);
assert.strictEqual(waitText(soon), "6h left");
assert.strictEqual(daysLeft(soon), 1);
assert.strictEqual(hoursLeft(late), -3);
assert.strictEqual(daysLeft(late), 0);
assert.strictEqual(waitText(late), "3h overdue");
assert.strictEqual(waitText(far), "3d left");
// open-ended waits on someone
const open = {{on: "dispatch team", since: "{_iso(-3)}"}};
assert.ok(openEnded(open) && !openEnded({{on: "x", until: "{_iso(1)}"}}));
assert.strictEqual(daysLeft(open), null);
assert.strictEqual(waitText(open), "awaiting dispatch team · 3d");
assert.strictEqual(waitText({{until: "{_iso(2)}", on: "QA"}}), "2d left · awaiting QA");
// badge pick: the soonest dated wait, else the longest-open wait on someone
assert.strictEqual(nextWait({{waitingSteps: [far, late, open]}}), late);
assert.strictEqual(nextWait({{waitingSteps: [open, {{on: "QA", since: "{_iso(-9)}"}}]}}).on, "QA");
assert.strictEqual(nextWait({{waitingSteps: []}}), null);
console.log("ok");
"""
    f = tmp_path / "t.js"
    f.write_text(harness)
    r = subprocess.run(["node", str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
