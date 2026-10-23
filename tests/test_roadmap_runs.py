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
