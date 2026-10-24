"""Digest: what landed, moved, stalled and got blocked since a time (plan 45)."""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/roadmap/scripts"))
from rmlib import digest as rmdigest  # noqa: E402

UTC = datetime.timezone.utc


def _now():
    return datetime.datetime.now(UTC).replace(microsecond=0)


def _git(repo, *args, when=None):
    env = dict(os.environ)
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return subprocess.run(["git", *args], cwd=repo, check=True, env=env,
                          capture_output=True, text=True).stdout


def _commit(repo, msg, when=None):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", msg, when=when)


def _setup(roadmap, repo, monkeypatch, n=5, settings=None):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    for i in range(n):
        roadmap.new_item(repo, "feature", f"Item {i + 1}")
    if settings:
        cfg = roadmap.read_config(repo)
        cfg.setdefault("settings", {}).update(settings)
        roadmap.write_config(repo, cfg)
    return repo


def _fixture(roadmap, repo, monkeypatch):
    """Two days ago: items 1-5 planned, item 3 claimed in review. Inside the
    last day: item 2 completed, item 3 moved review -> gate-ready, and item 4's
    branch (last commit 7.5 days ago) crossed the 7-day stale line 12h ago."""
    _setup(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 3, stage="review")
    _commit(repo, "baseline", when=_now() - datetime.timedelta(days=2))
    _git(repo, "branch", "-M", "main")
    _git(repo, "checkout", "-q", "-b", "roadmap/4")
    (repo / "work4.txt").write_text("x\n")
    _commit(repo, "work (plan 4)", when=_now() - datetime.timedelta(days=7, hours=12))
    _git(repo, "checkout", "-q", "main")
    roadmap.check_step(repo, 2, None, all_done=True)
    roadmap.set_claim(repo, 3, stage="gate-ready")
    _commit(repo, "today's work", when=_now() - datetime.timedelta(hours=1))
    return repo


def _ids(rows):
    return [r["id"] for r in rows]


# --- step 1: window parsing and change collection ----------------------------

def test_parse_since_forms():
    now = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    assert rmdigest.parse_since("3h", now) == now - datetime.timedelta(hours=3)
    assert rmdigest.parse_since("1d", now) == now - datetime.timedelta(days=1)
    assert rmdigest.parse_since("2w", now) == now - datetime.timedelta(weeks=2)
    assert rmdigest.parse_since("30m", now) == now - datetime.timedelta(minutes=30)
    assert rmdigest.parse_since("2026-10-20T08:00:00Z", now) == \
        datetime.datetime(2026, 10, 20, 8, tzinfo=UTC)
    day = rmdigest.parse_since("2026-10-20", now)          # local midnight
    assert day.tzinfo is not None and day.astimezone().date().isoformat() == "2026-10-20"
    for bad in ("yesterday", "", "3x", "2027-01-01"):
        with pytest.raises(ValueError):
            rmdigest.parse_since(bad, now)


def test_collect_lists_exactly_the_window_changes(roadmap, repo, monkeypatch):
    _fixture(roadmap, repo, monkeypatch)
    d = rmdigest.collect(repo, rmdigest.parse_since("1d"))
    assert d["baseline"] and d["git"]
    assert _ids(d["completed"]) == [2]
    assert [(c["id"], c["from"]["stage"], c["to"]["stage"]) for c in d["claims"]] == \
        [(3, "review", "gate-ready")]
    assert [(s["id"], s["reason"]) for s in d["stalled"]] == [(4, "stale")]
    assert _ids(d["ticked"]) == [2] and d["ticked"][0]["count"] == d["ticked"][0]["total"]
    assert d["newPlans"] == [] and d["ideas"] == [] and d["runs"] == []
    assert d["newBranches"] == []          # roadmap/4's first commit predates the window
    assert d["counts"]["completed"] == 1 and d["counts"]["stepsTicked"] >= 1


def test_wider_window_sees_more_and_narrow_window_sees_nothing(roadmap, repo, monkeypatch):
    _fixture(roadmap, repo, monkeypatch)
    wide = rmdigest.collect(repo, rmdigest.parse_since("3d"))   # before any commit
    assert wide["baseline"] is None
    assert _ids(wide["newPlans"]) == [1, 2, 3, 4, 5]
    assert [(c["id"], c["from"]["stage"], c["to"]["stage"]) for c in wide["claims"]] == \
        [(3, None, "gate-ready")]
    assert [b["name"] for b in rmdigest.collect(
        repo, rmdigest.parse_since("8d"))["newBranches"]] == ["roadmap/4"]
    later = rmdigest.collect(repo, rmdigest.parse_since("30m"))
    for key in ("completed", "claims", "ticked", "newPlans", "stalled", "ideas"):
        assert later[key] == [], key


def test_blocked_claim_goes_under_stalled_not_claims(roadmap, repo, monkeypatch):
    _fixture(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 5, stage="blocked", note="waiting on API keys")
    d = rmdigest.collect(repo, rmdigest.parse_since("1d"))
    assert ("blocked" in [s["reason"] for s in d["stalled"] if s["id"] == 5])
    assert 5 not in _ids(d["claims"])
    assert any(a["kind"] == "blocked" and a["id"] == 5 for a in d["attention"])


def test_new_plan_idea_and_run_in_window(roadmap, repo, monkeypatch):
    _fixture(roadmap, repo, monkeypatch)
    roadmap.new_item(repo, "bug", "Login breaks")
    roadmap.add_idea(repo, "Dark mode for the dashboard")
    from rmlib import runs as rmruns
    rmruns.append_run(repo, rmruns.make_record("suite", "unit", "fail", failing=["t1"]))
    rmruns.append_run(repo, rmruns.make_record(
        "gate", "old", "pass", now=_now() - datetime.timedelta(days=3)))
    d = rmdigest.collect(repo, rmdigest.parse_since("1d"))
    assert [(p["id"], p["type"]) for p in d["newPlans"]] == [(6, "bug")]
    assert [i["title"] for i in d["ideas"]] == ["Dark mode for the dashboard"]
    assert [r["label"] for r in d["runs"]] == ["unit"]
    assert any(a["kind"] == "trunk" for a in d["attention"])


def test_outside_git_reports_no_history(roadmap, tmp_path, monkeypatch):
    _setup(roadmap, tmp_path, monkeypatch, n=2)
    roadmap.check_step(tmp_path, 1, None, all_done=True)
    d = rmdigest.collect(tmp_path, rmdigest.parse_since("1d"))
    assert d["git"] is False and d["baseline"] is None
    assert d["completed"] == [] and d["newPlans"] == []


def test_attention_registry_covers_each_feature(roadmap, repo, monkeypatch):
    _setup(roadmap, repo, monkeypatch, n=3, settings={"wipLimit": 1})
    roadmap.set_claim(repo, 1, stage="fixing", verdict="REFUTED")
    roadmap.set_claim(repo, 3, stage="review")
    st = roadmap.status(repo)
    # plan 46 payload key: due/overdue waiting steps come first when present.
    st["waitingDue"] = [{"id": 2, "displayId": "FEAT-2", "title": "Item 2",
                         "step": 3, "daysLeft": -2, "reason": "soak"}]
    st["conflicts"] = {"pairs": [{"risk": "high", "a": {"id": 1, "displayId": "FEAT-1"},
                                  "b": {"id": 3, "displayId": "FEAT-3"},
                                  "files": ["a.py"], "conflictFiles": ["a.py"]},
                                 {"risk": "low", "a": {"id": 1}, "b": {"id": 2}}]}
    kinds = [a["kind"] for a in rmdigest.attention(repo, st)]
    assert kinds[0] == "waiting"
    assert {"waiting", "refuted", "wip", "conflict"} <= set(kinds)
    assert kinds.count("conflict") == 1
    first = rmdigest.attention(repo, st)[0]["text"]
    assert "step 3" in first and "2d overdue" in first and "soak" in first


def test_attention_flags_template_stubs_on_in_flight_items(roadmap, repo, monkeypatch,
                                                           template_gate):
    _setup(roadmap, repo, monkeypatch, n=2)
    roadmap.set_claim(repo, 1, stage="review")
    kinds = [(a["kind"], a.get("id")) for a in
             rmdigest.attention(repo, roadmap.status(repo))]
    assert ("stubs", 1) in kinds and ("stubs", 2) not in kinds   # 2 is only planned
