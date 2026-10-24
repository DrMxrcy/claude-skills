"""Plan 46: waiting steps, `release --with-waiting`, `retarget --split`."""
import datetime
import json

import pytest

TODAY = datetime.date.today()


def _iso(days: int) -> str:
    return (TODAY + datetime.timedelta(days=days)).isoformat()


def _plan(repo, n=1):
    return next((repo / ".roadmap/plans").glob(f"{n:03d}-*.md"))


def _item(roadmap, repo, steps=3, title="A", version=None, type_="feature"):
    """A new item whose checklist has `steps` plain steps."""
    path = roadmap.new_item(repo, type_, title, version)
    text = path.read_text()
    head, _, _ = text.partition("- [ ] Step 1:")
    body = "\n".join(f"- [ ] Step {k}: do thing {k}" for k in range(1, steps + 1))
    path.write_text(head + body + "\n")
    roadmap.sync(repo)
    return path


# ---- step 1: format, wait, wait --clear, check on a waiting step ------------

def test_wait_marks_step_and_never_counts_done(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    w = roadmap.wait_step(repo, 1, 3, until="7d", reason="soak")
    assert w == {"step": 3, "text": "Step 3: do thing 3", "until": _iso(7),
                 "reason": "soak"}
    assert f"- [~] Step 3: do thing 3 (waiting until {_iso(7)}: soak)" in path.read_text()
    parsed = roadmap.parse_plan(path)
    assert parsed["steps"][2] == (False, "Step 3: do thing 3")      # marker stripped
    assert parsed["waiting"] == {3: {"until": _iso(7), "reason": "soak"}}
    assert roadmap.count_progress(path) == (0, 3)
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.count_progress(path) == (2, 3)                   # waiting kept open
    assert "[~] Step 3" in path.read_text()
    assert roadmap.status(repo)["items"][0]["status"] != "done"


def test_wait_accepts_dates_and_rejects_garbage(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    assert roadmap.wait_step(repo, 1, 1, until="2030-01-02")["until"] == "2030-01-02"
    assert roadmap.wait_step(repo, 1, 2, until="2w")["until"] == _iso(14)
    with pytest.raises(ValueError, match="--until"):
        roadmap.wait_step(repo, 1, 3, until="next week")
    with pytest.raises(ValueError, match="out of range"):
        roadmap.wait_step(repo, 1, 9, until="1d")


def test_wait_redate_keeps_reason_and_clear_reverts(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 2, until="3d", reason="dns propagation")
    roadmap.wait_step(repo, 1, 2, until="5d")
    assert f"(waiting until {_iso(5)}: dns propagation)" in path.read_text()
    roadmap.wait_step(repo, 1, 2, clear=True)
    assert "- [ ] Step 2: do thing 2\n" in path.read_text()
    assert roadmap.parse_plan(path)["waiting"] == {}
    with pytest.raises(ValueError, match="not waiting"):
        roadmap.wait_step(repo, 1, 2, clear=True)


def test_wait_refuses_checked_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.check_step(repo, 1, 1)
    with pytest.raises(ValueError, match="already checked"):
        roadmap.wait_step(repo, 1, 1, until="1d")


def test_check_on_waiting_step_ticks_and_removes_marker(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 3, until="0d", reason="soak")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 1, 3, evidence="soak clean")
    text = path.read_text()
    assert "- [x] Step 3: do thing 3\n" in text and "waiting until" not in text
    assert roadmap.count_progress(path) == (3, 3)
    assert roadmap.status(repo)["items"][0]["lane"] == "done"


def test_undo_on_waiting_step_unticks(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 1, until="1d")
    roadmap.check_step(repo, 1, 1, undo=True)
    assert "- [ ] Step 1: do thing 1\n" in path.read_text()


def test_fenced_waiting_box_is_not_a_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = _item(roadmap, repo, steps=1)
    path.write_text(path.read_text() + "```\n- [~] Step 9: example\n```\n")
    assert roadmap.count_progress(path) == (0, 1)


def test_merge_keeps_waiting_steps(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, title="A")
    _item(roadmap, repo, title="B")
    roadmap.wait_step(repo, 2, 1, until="2030-01-01", reason="soak")
    roadmap.merge_items(repo, 1, [2])
    assert "- [~] Step 1: do thing 1 (waiting until 2030-01-01: soak)" \
        in _plan(repo, 1).read_text()


def test_cli_wait(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    assert roadmap.main(["wait", "1", "--step", "2", "--until", "2030-05-06",
                         "--reason", "soak"]) == 0
    assert "#1 step 2: waiting until 2030-05-06 (soak)" in capsys.readouterr().out
    assert roadmap.main(["wait", "#1", "--step", "2", "--clear"]) == 0
    assert "no longer waiting" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        roadmap.main(["wait", "1", "--step", "2"])


# ---- step 2: waiting lane, progress counts, due reminders -------------------

def _waiting_item(roadmap, repo, days=7, reason="soak", version=None, title="A"):
    """Item with steps 1-2 ticked and step 3 waiting `days` from today."""
    _item(roadmap, repo, title=title, version=version)
    n = roadmap.read_config(repo)["nextId"] - 1
    roadmap.wait_step(repo, n, 3, until=_iso(days), reason=reason)
    roadmap.check_step(repo, n, None, all_done=True)
    return n


def test_waiting_lane_once_other_steps_ticked(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 3, until="7d", reason="soak")
    row = roadmap.status(repo)["items"][0]
    assert row["lane"] != "waiting" and row["waiting"] == 1   # steps 1-2 still open
    roadmap.check_step(repo, 1, 1)
    roadmap.check_step(repo, 1, 2)
    st = roadmap.status(repo)
    row = st["items"][0]
    assert (row["lane"], row["done"], row["total"], row["waiting"]) == ("waiting", 2, 3, 1)
    assert row["status"] == "active" and row["pct"] == 67
    assert row["waitingSteps"] == [{"step": 3, "text": "Step 3: do thing 3",
                                    "until": _iso(7), "reason": "soak", "daysLeft": 7}]
    assert st["counts"]["lanes"]["waiting"] == 1 and st["counts"]["byLane"] == {"waiting": 1}
    assert not roadmap.is_in_flight(row)
    assert roadmap.lane_label(row) == "waiting · step 3 · 7d left"
    assert st["waitingDue"] == [] and not st["versionComplete"]
    roadmap.wait_step(repo, 1, 3, clear=True)
    assert "waitingDue" not in roadmap.status(repo)       # payload unchanged without waits


def test_waiting_lane_outranks_claims_and_landing(roadmap, repo):
    assert roadmap.derive_lane("active", {"stage": "landed"}, None, waiting=True) == "waiting"
    assert roadmap.derive_lane("done", None, None, waiting=True) == "done"
    assert roadmap.derive_lane("active", None, None) == "active"


def test_countdown_text(roadmap):
    assert [roadmap.countdown(d) for d in (4, 1, 0, -2, None)] == \
        ["4d left", "1d left", "due", "2d overdue", "no date"]


def test_roadmap_md_shows_waiting_count(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    text = (repo / "ROADMAP.md").read_text()
    assert "`feature` — 67% (+1 waiting) ([plan]" in text
    assert "- [ ] **#1 A**" in text                        # never rendered done


def test_waiting_step_never_completes_version_or_changelog(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    assert roadmap.uncut_complete_version(repo) is None
    assert "(in progress)" in (repo / "CHANGELOG.internal.md").read_text()
    assert "- (pending) A" in (repo / "CHANGELOG.internal.md").read_text()


def test_forecast_counts_waiting_as_remaining(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    from rmlib import forecast as rmforecast
    assert [c for c, _ in rmforecast.step_dates(_plan(repo))] == [True, True, False]


def test_check_landed_never_ticks_a_waiting_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.wait_step(repo, 1, 3, until="7d")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.set_claim(repo, 1, stage="landed")
    assert roadmap.status(repo)["items"][0]["lane"] == "waiting"


def test_due_waiting_listed_first_in_orient_next_status(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, title="Other")                    # #1: ordinary open item
    _waiting_item(roadmap, repo, days=0, title="Soaked")   # #2: due today
    _waiting_item(roadmap, repo, days=-2, title="Late")    # #3: 2 days overdue
    _waiting_item(roadmap, repo, days=5, title="Later")    # #4: not due
    st = roadmap.status(repo)
    assert [(d["id"], d["daysLeft"]) for d in st["waitingDue"]] == [(3, -2), (2, 0)]
    # next: a due waiting item outranks normal order; a not-yet-due one is skipped
    assert roadmap.next_item(repo, quiet=True)["id"] == 3
    roadmap.check_step(repo, 3, 3)
    roadmap.check_step(repo, 2, 3)
    assert roadmap.next_item(repo, quiet=True)["id"] == 1
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.next_item(repo, quiet=True) is None     # #4 waits, nothing to do
    roadmap.wait_step(repo, 4, 3, until=_iso(-1))
    capsys.readouterr()
    roadmap.main(["orient"])
    out = capsys.readouterr().out.splitlines()
    assert out[2].startswith("⏰ FEAT-4 step 3 (1d overdue: soak) — Step 3: do thing 3 "
                             "→ verify, then: roadmap.py check --plan 4 --step 3")
    roadmap.main(["next"])
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("⏰ FEAT-4 step 3") and out[1].startswith("FEAT-4 Later")
    roadmap.main(["status"])
    out = capsys.readouterr().out.splitlines()
    assert "1 waiting" in out[0] and out[1].startswith("⏰ FEAT-4 step 3")
    assert any("waiting · step 3 · 1d overdue" in l for l in out)
    roadmap.main(["next", "--json"])
    assert json.loads(capsys.readouterr().out)["waitingDue"][0]["step"] == 3


def test_orient_suggests_with_waiting_when_only_waits_remain(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo, days=3)
    payload = roadmap.orient(repo)
    assert payload["waitingOnly"] and payload["next"] is None
    assert "--with-waiting" in roadmap.format_orient(payload)
