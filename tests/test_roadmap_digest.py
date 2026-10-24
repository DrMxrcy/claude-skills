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


# --- step 2: `digest` command, md/json output, `--since last` stamp -----------

def _section(text, heading):
    """Rows printed under `heading` in the terminal digest."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(heading + " ("))
    rows = []
    for l in lines[start + 1:]:
        if not l.startswith("  "):
            break
        rows.append(l.strip())
    return rows


def test_cli_digest_text_headings(roadmap, repo, monkeypatch, capsys):
    _fixture(roadmap, repo, monkeypatch)
    capsys.readouterr()
    assert roadmap.main(["digest", "--since", "1d"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Digest: P — since ")
    assert _section(out, "Completed") == ["FEAT-2 Item 2 (v0.0.1)"]
    assert _section(out, "Claims moved") == ["FEAT-3 Item 3 — review → gate-ready"]
    assert len(_section(out, "Stale or blocked")) == 1
    assert _section(out, "Stale or blocked")[0].startswith("FEAT-4 Item 4 — stale (roadmap/4")
    assert "New plans" not in out and "Ideas added" not in out


def test_cli_digest_md_and_json(roadmap, repo, monkeypatch, capsys):
    _fixture(roadmap, repo, monkeypatch)
    capsys.readouterr()
    assert roadmap.main(["digest", "--since", "1d", "--format", "md"]) == 0
    md = capsys.readouterr().out
    assert md.startswith("## Digest: P")
    assert "### Completed (1)\n- FEAT-2 Item 2 (v0.0.1)" in md
    assert "### Claims moved (1)\n- FEAT-3 Item 3 — review → gate-ready" in md
    assert roadmap.main(["digest", "--since", "1d", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert [c["id"] for c in d["completed"]] == [2]
    assert d["label"] == "1d" and d["counts"]["claims"] == 1


def test_since_last_covers_only_changes_after_previous_run(roadmap, repo, monkeypatch,
                                                           capsys):
    _fixture(roadmap, repo, monkeypatch)
    capsys.readouterr()
    assert roadmap.main(["digest", "--json"]) == 0           # first run: 1d fallback
    first = json.loads(capsys.readouterr().out)
    assert first["label"].startswith("1d") and [c["id"] for c in first["completed"]] == [2]
    # A run with nothing new since: the stamp moved, so nothing repeats.
    _commit(repo, "noise")
    assert roadmap.main(["digest", "--since", "last", "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["label"] == "last run"
    assert again["completed"] == [] and again["claims"] == [] and again["stalled"] == []
    assert again["baseline"]["sha"] is None       # diffed against the stamped snapshot
    # A change after the stamp shows up next time (committed a moment later).
    roadmap.set_claim(repo, 5, stage="review", verdict="REFUTED")
    _commit(repo, "claim 5", when=_now() + datetime.timedelta(seconds=2))
    assert roadmap.main(["digest", "--since", "last", "--json"]) == 0
    third = json.loads(capsys.readouterr().out)
    assert [(c["id"], c["to"]["stage"]) for c in third["claims"]] == [(5, "review")]
    # Uncommitted changes count once: seen by this run, gone from the next.
    roadmap.set_claim(repo, 1, stage="review")
    assert roadmap.main(["digest", "--json"]) == 0
    assert [c["id"] for c in json.loads(capsys.readouterr().out)["claims"]] == [1]
    assert roadmap.main(["digest", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["claims"] == []


def test_digest_writes_nothing_git_tracks(roadmap, repo, monkeypatch, capsys):
    _fixture(roadmap, repo, monkeypatch)
    before = _git(repo, "status", "--porcelain")
    assert before == ""
    assert roadmap.main(["digest", "--since", "1d"]) == 0
    assert roadmap.main(["digest"]) == 0
    assert _git(repo, "status", "--porcelain", "--ignored") == ""
    stamp = repo / ".git" / rmdigest.STAMP_FILE
    data = json.loads(stamp.read_text())
    assert list(data) == ["::t"] and "digest" in data["::t"]   # root prefix :: owner
    assert rmdigest.read_stamp(repo, "digest", "t") is not None
    assert rmdigest.read_stamp(repo, "digest", "someone-else") is None


def test_stamp_is_shared_by_linked_worktrees(roadmap, repo, monkeypatch, tmp_path_factory):
    _fixture(roadmap, repo, monkeypatch)
    wt = tmp_path_factory.mktemp("wt") / "w"
    _git(repo, "worktree", "add", "-q", str(wt), "roadmap/4")
    assert rmdigest.stamp_path(wt).resolve() == (repo / ".git" / rmdigest.STAMP_FILE).resolve()
    rmdigest.write_stamp(wt, "digest", "t")
    assert rmdigest.read_stamp(repo, "digest", "t") is not None
    assert _git(wt, "status", "--porcelain") == ""


def test_bad_since_is_an_error(roadmap, repo, monkeypatch, capsys):
    _fixture(roadmap, repo, monkeypatch)
    assert roadmap.main(["digest", "--since", "soon"]) == 1
    assert "bad --since" in capsys.readouterr().err


# --- step 3: orient prints a short digest since the last session ---------------

def test_orient_prints_short_digest_and_restamps(roadmap, repo, monkeypatch, capsys):
    _fixture(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 5, stage="fixing", verdict="REFUTED")
    capsys.readouterr()
    assert roadmap.main(["orient"]) == 0                  # first session: 1d fallback
    out = capsys.readouterr().out
    lines = [l for l in out.splitlines()
             if l.startswith(("Since ", "⚠ Needs attention", "Details: roadmap.py digest"))]
    assert len(lines) == 3, out
    assert lines[0].startswith("Since 1d (no previous run): 1 completed")
    assert "1 stale/blocked" in lines[0] and "claims moved" in lines[0]
    assert "FEAT-5 Item 5 — verdict REFUTED" in lines[1]
    assert lines[2].startswith("Details: roadmap.py digest --since 20")
    assert rmdigest.read_stamp(repo, "orient", "t") is not None
    assert rmdigest.read_stamp(repo, "digest", "t") is None     # separate keys
    # Next session: nothing moved since, so one line; attention still shows.
    assert roadmap.main(["orient", "--json"]) == 0
    dg = json.loads(capsys.readouterr().out)["digest"]
    assert dg["label"] == "last session" and dg["summary"] == ""
    assert any("REFUTED" in a for a in dg["attention"])
    # The uncommitted claim on item 5 was seen last session: it does not repeat.
    assert "005-item-5.md" in _git(repo, "status", "--porcelain")


def test_orient_quiet_session_is_one_line(roadmap, repo, monkeypatch, capsys):
    _setup(roadmap, repo, monkeypatch, n=1)
    _commit(repo, "init", when=_now() - datetime.timedelta(days=3))
    rmdigest.write_stamp(repo, "orient", "t", _now() - datetime.timedelta(hours=5))
    capsys.readouterr()
    assert roadmap.main(["orient"]) == 0
    out = capsys.readouterr().out
    assert "Since last session (5h ago): no roadmap changes" in out
    assert "Details: roadmap.py digest" not in out


def test_orient_outside_git_and_handoff_have_no_digest(roadmap, tmp_path, monkeypatch,
                                                       capsys):
    _setup(roadmap, tmp_path, monkeypatch, n=1)
    capsys.readouterr()
    assert roadmap.main(["orient", "--json"]) == 0
    assert "digest" not in json.loads(capsys.readouterr().out)
    assert "digest" not in roadmap.handoff(tmp_path)
