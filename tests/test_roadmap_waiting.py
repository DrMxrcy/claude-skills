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
