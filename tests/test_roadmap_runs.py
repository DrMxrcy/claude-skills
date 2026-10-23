"""Run log (plan 38): rmlib/runs.py + `run` / `status --runs`, trunk health,
the union-merge gitattribute, and the dashboard gate timeline."""
import datetime
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"


@pytest.fixture
def runs(roadmap):
    import importlib
    return importlib.import_module("rmlib.runs")


@pytest.fixture
def proj(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    for n in range(3):
        roadmap.new_item(repo, "feature", f"Item {n + 1}")
    return repo


def _t(minute):
    return datetime.datetime(2026, 10, 23, 12, minute, tzinfo=datetime.timezone.utc)


def _rec(runs, label, result="pass", kind="gate", minute=0, **kw):
    return runs.make_record(kind, label, result, now=_t(minute), **kw)


# ---- step 1: writer, lock, trim, reader ------------------------------------

def test_parse_duration(runs):
    assert runs.parse_duration("12m") == 720
    assert runs.parse_duration("1h30m") == 5400
    assert runs.parse_duration("2m30s") == 150
    assert runs.parse_duration("90") == 90
    assert runs.parse_duration(None) is None
    for bad in ("abc", "1.5m", "m"):
        with pytest.raises(ValueError):
            runs.parse_duration(bad)
    assert runs.format_duration(5400) == "1h30m" and runs.format_duration(150) == "2m30s"


def test_split_list_keeps_bracketed_commas(runs):
    assert runs.split_list("a::t[1,2], b::u\nc") == ["a::t[1,2]", "b::u", "c"]
    assert runs.split_list("") == []


def test_parse_shards(runs):
    assert runs.parse_shards("unit=pass, e2e=FAIL") == {"unit": "pass", "e2e": "fail"}
    for bad in ("unit", "unit=maybe", "=pass"):
        with pytest.raises(ValueError):
            runs.parse_shards(bad)


def test_make_record_validates_and_derives_start(runs):
    r = runs.make_record("gate", "merge 38", "pass", duration=600, now=_t(30),
                         log="https://ci.example/1", items=[38], branches=["roadmap/38"])
    assert r["at"] == "2026-10-23T12:30:00Z" and r["startedAt"] == "2026-10-23T12:20:00Z"
    assert r["items"] == [38] and r["branches"] == ["roadmap/38"]
    for kwargs in ({"log": "javascript:alert(1)"}, {"log": "/tmp/x.log"}):
        with pytest.raises(ValueError):
            runs.make_record("gate", "x", "pass", **kwargs)
    with pytest.raises(ValueError):
        runs.make_record("deploy", "x", "pass")
    with pytest.raises(ValueError):
        runs.make_record("gate", "x", "ok")
    with pytest.raises(ValueError):
        runs.make_record("gate", "  ", "pass")


def test_two_appends_two_parseable_lines_newest_first(runs, proj):
    runs.append_run(proj, _rec(runs, "first", minute=1))
    runs.append_run(proj, _rec(runs, "second", minute=2))
    lines = runs.runs_path(proj).read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(ln) for ln in lines)
    got, warnings = runs.read_runs(proj)
    assert [r["label"] for r in got] == ["second", "first"] and warnings == []


def test_same_second_ties_break_by_file_order(runs, proj):
    runs.append_run(proj, _rec(runs, "a"))
    runs.append_run(proj, _rec(runs, "b"))
    assert [r["label"] for r in runs.read_runs(proj)[0]] == ["b", "a"]


def test_union_merged_order_is_chronological(runs, proj):
    # A union merge can put a branch's older line after trunk's newer one.
    runs.append_run(proj, _rec(runs, "newer", minute=9))
    runs.append_run(proj, _rec(runs, "older", minute=3))
    assert [r["label"] for r in runs.read_runs(proj)[0]] == ["newer", "older"]


def test_trim_keeps_runs_keep(runs, proj):
    for n in range(7):
        runs.append_run(proj, _rec(runs, f"r{n}", minute=n), keep=5)
    lines = runs.runs_path(proj).read_text().splitlines()
    assert len(lines) == 5
    assert [r["label"] for r in runs.read_runs(proj)[0]] == ["r6", "r5", "r4", "r3", "r2"]


def test_runs_keep_setting(runs):
    assert runs.runs_keep({"settings": {"runsKeep": 3}}) == 3
    for bad in ({}, {"settings": {"runsKeep": 0}}, {"settings": {"runsKeep": "x"}}):
        assert runs.runs_keep(bad) == runs.DEFAULT_KEEP


def test_bad_lines_skipped_with_warning(runs, proj):
    runs.append_run(proj, _rec(runs, "ok", minute=1))
    path = runs.runs_path(proj)
    with open(path, "a") as f:
        f.write("{not json\n")
        f.write('{"kind":"gate"}\n')              # parseable, not a run
        f.write('[1,2]')                          # no trailing newline
    runs.append_run(proj, _rec(runs, "after", minute=2))   # must not glue on
    got, warnings = runs.read_runs(proj)
    assert [r["label"] for r in got] == ["after", "ok"]
    assert len(warnings) == 3 and "unparseable" in warnings[0]


def test_reader_sanitises_fields(runs, proj):
    bad = {"at": "2026-10-23T12:00:00Z", "kind": "gate", "label": "x", "result": "fail",
           "log": "javascript:alert(1)", "items": ["7", 8], "durationSec": -4,
           "shards": {"u": "maybe", "e": "fail"}, "failing": "notalist"}
    runs.runs_path(proj).write_text(json.dumps(bad) + "\n")
    (r,), _ = runs.read_runs(proj)
    assert r["log"] is None and r["items"] == [8] and r["durationSec"] is None
    assert r["shards"] == {"e": "fail"} and r["failing"] == []


def test_concurrent_appends_never_corrupt(runs, proj):
    def worker(k):
        for n in range(10):
            runs.append_run(proj, _rec(runs, f"w{k}-{n}"), keep=1000)
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    got, warnings = runs.read_runs(proj)
    assert len(got) == 40 and warnings == []


def test_missing_file_is_empty(runs, proj):
    assert runs.read_runs(proj) == ([], [])


# ---- step 2: `run`, `status --runs`, payload runs + trunkHealth ------------

def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


def test_run_cli_appends_and_status_runs_lists_newest_first(roadmap, runs, proj, capsys):
    assert roadmap.main(["run", "--kind", "gate", "--label", "merge 1+2", "--result",
                         "pass", "--items", "1,#2", "--branches", "roadmap/1,roadmap/2",
                         "--duration", "12m", "--log", "https://ci.example/run/7"]) == 0
    assert roadmap.main(["run", "--kind", "suite", "--label", "nightly", "--result",
                         "fail", "--shards", "unit=pass,e2e=fail",
                         "--failing", "tests/e2e.py::test_a[x,y], tests/e2e.py::test_b"]) == 0
    lines = runs.runs_path(proj).read_text().splitlines()
    first = json.loads(lines[0])
    assert first["items"] == [1, 2] and first["durationSec"] == 720
    assert first["branches"] == ["roadmap/1", "roadmap/2"]
    capsys.readouterr()
    assert roadmap.main(["status", "--runs"]) == 0
    out = capsys.readouterr().out
    assert out.index("nightly") < out.index("merge 1+2")
    assert "https://ci.example/run/7" in out and "tests/e2e.py::test_a[x,y]" in out
    assert "trunk health: RED" in out and "e2e=fail" in out
    roadmap.main(["status", "--runs", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert [r["label"] for r in data["runs"]] == ["nightly", "merge 1+2"]


def test_run_cli_rejects_bad_input(roadmap, runs, proj, capsys):
    assert roadmap.main(["run", "--kind", "gate", "--label", "x", "--result", "pass",
                         "--log", "file:///etc/passwd"]) == 1
    assert roadmap.main(["run", "--kind", "gate", "--label", "x", "--result", "pass",
                         "--duration", "soon"]) == 1
    assert not runs.runs_path(proj).exists()
    with pytest.raises(SystemExit):
        roadmap.main(["run", "--kind", "deploy", "--label", "x", "--result", "pass"])


def test_run_cli_honours_runs_keep(roadmap, runs, proj):
    cfg = roadmap.read_config(proj)
    cfg["settings"]["runsKeep"] = 2
    roadmap.write_config(proj, cfg)
    for n in range(4):
        roadmap.main(["run", "--kind", "gate", "--label", f"g{n}", "--result", "pass"])
    assert len(runs.runs_path(proj).read_text().splitlines()) == 2


def test_status_survives_unparseable_line(roadmap, runs, proj, capsys):
    runs.append_run(proj, _rec(runs, "ok"))
    with open(runs.runs_path(proj), "a") as f:
        f.write("garbage\n")
    st = roadmap.status(proj)
    assert [r["label"] for r in st["runs"]] == ["ok"]
    assert st["runWarnings"] and "unparseable" in st["runWarnings"][0]
    capsys.readouterr()
    assert roadmap.main(["status"]) == 0
    assert "warning:" in capsys.readouterr().err
    assert roadmap.main(["status", "--runs"]) == 0


def test_status_payload_runs_capped_and_no_warnings_key_when_clean(roadmap, runs, proj):
    for n in range(runs.STATUS_RUNS + 5):
        runs.append_run(proj, _rec(runs, f"r{n}"))
    st = roadmap.status(proj)
    assert len(st["runs"]) == runs.STATUS_RUNS and "runWarnings" not in st
    assert st["trunkHealth"] == {"shards": [], "green": None, "ahead": []}


def test_trunk_health_latest_suite_per_shard(runs):
    rs = [_rec(runs, "nightly", "pass", "suite", 9, shards={"unit": "pass"}),
          _rec(runs, "nightly", "fail", "suite", 5, shards={"unit": "fail", "e2e": "fail"},
               failing=["t_e2e"]),
          _rec(runs, "lint", "pass", "suite", 4),                     # shard = label
          _rec(runs, "branch", "fail", "suite", 8, branches=["roadmap/9"]),
          _rec(runs, "merge", "fail", "gate", 10)]
    rs = [runs._clean(r) for r in sorted(rs, key=lambda r: r["at"], reverse=True)]
    h = runs.trunk_health(rs, "main")
    by = {s["shard"]: s for s in h["shards"]}
    assert set(by) == {"unit", "e2e", "lint"}            # gate + branch-only suite ignored
    assert by["unit"]["result"] == "pass" and by["unit"]["failing"] == []
    assert by["e2e"]["result"] == "fail" and by["e2e"]["failing"] == ["t_e2e"]
    assert h["green"] is False
    on_main = runs._clean(_rec(runs, "x", "pass", "suite", 11, branches=["main"]))
    assert runs.trunk_health([on_main], "main")["green"] is True


def test_trunk_health_ahead_counts_integration_commits(roadmap, runs, proj):
    _git(proj, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    _git(proj, "branch", "roadmap/v1")
    _git(proj, "checkout", "-qb", "roadmap/v2")
    for n in range(3):
        _git(proj, "commit", "--allow-empty", "-qm", f"w{n}")
    _git(proj, "checkout", "-q", "main")
    assert "trunkHealth" not in roadmap.status(proj)                 # unset, no runs
    for setting, want in (("roadmap/v2", [{"branch": "roadmap/v2", "commits": 3}]),
                          (["roadmap/v*"], [{"branch": "roadmap/v1", "commits": 0},
                                            {"branch": "roadmap/v2", "commits": 3}]),
                          ("main", []), ("nope", [])):
        cfg = roadmap.read_config(proj)
        cfg["settings"]["integrationBranch"] = setting
        roadmap.write_config(proj, cfg)
        assert roadmap.status(proj)["trunkHealth"]["ahead"] == want, setting
    assert runs.trunk_ahead(proj, "roadmap/v2", None) == []          # no trunk


def test_payload_unchanged_without_runs_or_integration(roadmap, proj, capsys):
    st = roadmap.status(proj)
    assert not {"runs", "trunkHealth", "runWarnings"} & set(st)
    assert roadmap.main(["status", "--runs"]) == 0
    assert "no runs recorded" in capsys.readouterr().out


def test_trunk_ahead_outside_git(runs, tmp_path):
    assert runs.trunk_ahead(tmp_path, "dev", "main") == []


# ---- step 3: union-merge gitattribute via init / upgrade -------------------

def test_init_adds_union_merge_line(roadmap, runs, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    text = (repo / ".gitattributes").read_text()
    assert text == runs.GITATTR_LINE + "\n"
    roadmap.init_project(repo, "P", claude_md=False)
    assert (repo / ".gitattributes").read_text() == text           # idempotent


def test_upgrade_adds_line_once_and_keeps_content(roadmap, runs, repo, capsys):
    roadmap.init_project(repo, "P", claude_md=False)
    (repo / ".gitattributes").write_text("* text=auto")             # no newline, no line
    roadmap.upgrade(repo)
    assert (repo / ".gitattributes").read_text() == "* text=auto\n" + runs.GITATTR_LINE + "\n"
    assert "merge=union" in capsys.readouterr().out
    roadmap.upgrade(repo)
    assert (repo / ".gitattributes").read_text().count("merge=union") == 1
    assert "merge=union" not in capsys.readouterr().out


def test_union_merge_resolves_concurrent_appends(roadmap, runs, proj):
    _git(proj, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    _git(proj, "checkout", "-qb", "side")
    runs.append_run(proj, _rec(runs, "side-gate", minute=2))
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "side run")
    _git(proj, "checkout", "-q", "main")
    runs.append_run(proj, _rec(runs, "main-gate", minute=1))
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "main run")
    _git(proj, "merge", "-q", "--no-edit", "side")                  # no conflict
    got, warnings = runs.read_runs(proj)
    assert [r["label"] for r in got] == ["side-gate", "main-gate"] and warnings == []

