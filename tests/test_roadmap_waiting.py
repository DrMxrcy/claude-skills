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


# ---- step 3: follow-up items with two-way links -----------------------------

def test_follow_up_moves_steps_with_two_way_links(roadmap, repo, template_gate):
    roadmap.init_project(repo, "P")
    src = _item(roadmap, repo, steps=4, title="Soak me")
    roadmap.check_step(repo, 1, 1, force=True)
    roadmap.wait_step(repo, 1, 3, until="2030-01-02", reason="soak")
    src.write_text(src.read_text().replace(
        "(waiting until 2030-01-02: soak)",
        "(waiting until 2030-01-02: soak)\n  > evidence: deployed (2026-10-01)"))
    item = roadmap.create_follow_up(repo, 1, [3, 4], "0.0.2", why="split for test",
                                    suffix="verify after soak")
    roadmap.sync(repo)
    cfg = roadmap.read_config(repo)
    assert item == {"id": 2, "slug": item["slug"], "type": "feature", "version": "0.0.2",
                    "title": "Follow-up: Soak me — verify after soak",
                    "file": f"plans/002-{item['slug']}.md", "followUpOf": 1}
    assert cfg["nextId"] == 3 and cfg["items"][0]["followUps"] == [2]
    src_text = src.read_text()
    assert "follow_ups: 2" in src_text
    assert "- ↪ Moved to follow-up #2 (v0.0.2): Step 3: do thing 3\n" in src_text
    assert "- ↪ Moved to follow-up #2 (v0.0.2): Step 4: do thing 4\n" in src_text
    assert "evidence: deployed" not in src_text
    assert roadmap.count_progress(src) == (1, 2)
    fu = repo / ".roadmap" / item["file"]
    fu_text = fu.read_text()
    assert "follow_up_of: 1" in fu_text and "Follow-up of #1" in fu_text
    assert "- [~] Step 1: do thing 3 (waiting until 2030-01-02: soak)\n" \
           "  > evidence: deployed (2026-10-01)\n- [ ] Step 2: do thing 4\n" in fu_text
    assert roadmap.parse_plan(fu)["waiting"] == {1: {"until": "2030-01-02",
                                                      "reason": "soak"}}
    # the follow-up passes the template gate: it can be checked without --force
    roadmap.check_step(repo, 2, 2)
    row = {i["id"]: i for i in roadmap.status(repo)["items"]}
    assert row[2]["followUpOf"] == 1 and row[1]["followUps"] == [2]
    assert "**#2 Follow-up: Soak me — verify after soak**" in (repo / "ROADMAP.md").read_text()


def test_follow_up_of_a_bug_passes_the_bug_gate(roadmap, repo, template_gate):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, type_="bug")
    item = roadmap.create_follow_up(repo, 1, [2], "0.0.2", why="w", suffix="s")
    roadmap.sync(repo)
    roadmap.check_step(repo, item["id"], 1)


def test_follow_up_refuses_checked_or_missing_steps(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.check_step(repo, 1, 1)
    with pytest.raises(ValueError, match="is checked"):
        roadmap.create_follow_up(repo, 1, [1], "0.0.2", why="w", suffix="s")
    with pytest.raises(ValueError, match="no step"):
        roadmap.create_follow_up(repo, 1, [7], "0.0.2", why="w", suffix="s")
    assert roadmap.read_config(repo)["nextId"] == 2           # nothing written
    assert len(list((repo / ".roadmap/plans").glob("*.md"))) == 1


# ---- step 4: release --with-waiting and retarget --split ---------------------

def test_release_refuses_waiting_steps_naming_them(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo, days=7)
    with pytest.raises(ValueError) as exc:
        roadmap.release(repo, "0.0.2")
    msg = str(exc.value)
    assert f"#1 step 3 (waiting until {_iso(7)}: soak)" in msg and "--with-waiting" in msg
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.1"


def test_release_names_waits_beside_other_incomplete_items(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    _item(roadmap, repo, title="Open")
    with pytest.raises(ValueError, match=r"incomplete items: #2 Open.*#1 step 3"):
        roadmap.release(repo, "0.0.2", with_waiting=True)
    assert roadmap.read_config(repo)["nextId"] == 3          # nothing split off


def test_release_with_waiting_ships_and_creates_follow_up(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo, days=7, title="Payments")
    made = roadmap.release(repo, "0.0.2", with_waiting=True)
    assert [m["id"] for m in made] == [2]
    cfg = roadmap.read_config(repo)
    assert cfg["currentVersion"] == "0.0.2" and "0.0.1" in cfg["versionDates"]
    fu = cfg["items"][1]
    assert (fu["title"], fu["version"], fu["followUpOf"]) == \
        ("Follow-up: Payments — verify after soak", "0.0.2", 1)
    assert cfg["items"][0]["followUps"] == [2]
    assert roadmap.count_progress(_plan(repo, 1)) == (2, 2)
    fu_path = _plan(repo, 2)
    assert f"- [~] Step 1: do thing 3 (waiting until {_iso(7)}: soak)" in fu_path.read_text()
    st = {i["id"]: i for i in roadmap.status(repo)["items"]}
    assert st[1]["lane"] == "done" and st[2]["waiting"] == 1
    internal = (repo / "CHANGELOG.internal.md").read_text()
    v1 = internal.split("## v0.0.1")[1]
    assert "- Payments" in v1 and "(pending)" not in v1 and "in progress" not in v1
    assert "#1: shipped in v0.0.1; #1 step 3" in capsys.readouterr().out


def test_release_with_waiting_leaves_all_waiting_item_alone(roadmap, repo):
    """An item with nothing ticked has shipped nothing: it is not waiting-only."""
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, steps=1)
    roadmap.wait_step(repo, 1, 1, until="1d")
    with pytest.raises(ValueError, match="incomplete items: #1"):
        roadmap.release(repo, "0.0.2", with_waiting=True)


def test_release_force_without_flag_is_unchanged(roadmap, repo):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    assert roadmap.release(repo, "0.0.2", force=True) == []
    cfg = roadmap.read_config(repo)
    assert cfg["currentVersion"] == "0.0.2" and len(cfg["items"]) == 1


def test_retarget_split_keeps_ticked_steps_and_moves_open_ones(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo, steps=6, title="Nine")
    for n in (1, 2, 4, 5):
        roadmap.check_step(repo, 1, n)
    roadmap.wait_step(repo, 1, 6, until="2030-01-01", reason="soak")
    roadmap.set_claim(repo, 1, stage="review")
    made = roadmap.retarget(repo, "0.0.3", plan_ids=[1], split=True)
    cfg = roadmap.read_config(repo)
    src, fu = cfg["items"]
    assert [m["id"] for m in made] == [2]
    assert src["version"] == "0.0.1" and fu["version"] == "0.0.3"
    assert (fu["title"], fu["followUpOf"], src["followUps"]) == \
        ("Follow-up: Nine — remaining steps", 1, [2])
    assert roadmap.count_progress(_plan(repo, 1)) == (4, 4)
    fu_text = _plan(repo, 2).read_text()
    assert "- [ ] Step 1: do thing 3\n- [~] Step 2: do thing 6 (waiting until " \
           "2030-01-01: soak)\n" in fu_text
    assert roadmap.count_progress(_plan(repo, 2)) == (0, 2)
    st = {i["id"]: i for i in roadmap.status(repo)["items"]}
    assert st[1]["lane"] == "done" and st[1]["claim"] is None


def test_retarget_split_refusals(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    with pytest.raises(ValueError, match="no ticked steps"):
        roadmap.retarget(repo, "0.0.2", plan_ids=[1], split=True)
    roadmap.check_step(repo, 1, None, all_done=True)
    with pytest.raises(ValueError, match="no open steps"):
        roadmap.retarget(repo, "0.0.2", plan_ids=[1], split=True)
    with pytest.raises(ValueError, match="item ids"):
        roadmap.retarget(repo, "0.0.2", from_versions=["0.0.1"], split=True)


def test_plain_retarget_unchanged(roadmap, repo):
    roadmap.init_project(repo, "P")
    _item(roadmap, repo)
    roadmap.check_step(repo, 1, 1)
    assert roadmap.retarget(repo, "0.0.2", plan_ids=[1]) == []
    cfg = roadmap.read_config(repo)
    assert len(cfg["items"]) == 1 and cfg["items"][0]["version"] == "0.0.2"
    assert roadmap.count_progress(_plan(repo)) == (1, 3)


def test_cli_release_with_waiting_and_retarget_split(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo)
    assert roadmap.main(["release", "--version", "0.0.2"]) == 1
    assert "--with-waiting" in capsys.readouterr().err
    assert roadmap.main(["release", "--version", "0.0.2", "--with-waiting"]) == 0
    assert "follow-up #2 in v0.0.2" in capsys.readouterr().out
    _item(roadmap, repo, title="Nine", version="0.0.2")
    roadmap.check_step(repo, 3, 1)
    assert roadmap.main(["retarget", "3", "--version", "0.0.3", "--split"]) == 0
    assert "#3: open steps → follow-up #4 in v0.0.3" in capsys.readouterr().out
    assert roadmap.main(["retarget", "--plan", "4", "--to", "0.0.4"]) == 0
    assert roadmap.read_config(repo)["items"][3]["version"] == "0.0.4"


# ---- step 5: dashboard countdown, plan-page highlight, follow-up links -------

def test_dashboard_item_detail_carries_waits_and_follow_up_links(roadmap, repo, dashboard):
    roadmap.init_project(repo, "P")
    _waiting_item(roadmap, repo, days=4, title="Payments")
    d = dashboard._item_detail(roadmap._dashboard_api(), repo, 1)
    assert d["steps"][2] == {"done": False, "text": "Step 3: do thing 3",
                             "waiting": {"until": _iso(4), "reason": "soak"}}
    assert "waiting" not in d["steps"][0]
    assert d["lane"] == "waiting"
    assert d["waitingSteps"][0]["daysLeft"] == 4
    assert (d["followUpOf"], d["followUps"]) == (None, [])
    roadmap.release(repo, "0.0.2", with_waiting=True)
    src = dashboard._item_detail(roadmap._dashboard_api(), repo, 1)
    fu = dashboard._item_detail(roadmap._dashboard_api(), repo, 2)
    assert src["followUps"] == [2] and fu["followUpOf"] == 1
    assert fu["waitingSteps"][0]["until"] == _iso(4)


def test_dashboard_html_has_waiting_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ('"waiting"', 'waiting:"wait"', ".lg-wait", "--wait:",
                 "function rowMark", "const countdown", "const daysLeft",
                 "it.waitingSteps", "d.waitingSteps", '"follow-up of"',
                 '"follow-ups"', "d.followUpOf", "d.followUps",
                 "[ xX~]", "li.task.waiting", '"waiting, "+countdown'):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
    # the board/lane filter lists the waiting lane
    assert '"stale","waiting","active"' in body
