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
