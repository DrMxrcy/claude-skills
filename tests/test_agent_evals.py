"""Coverage for the agent fleet's golden-task evals (skills/agent/evals/)."""
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EVALS = REPO / "skills" / "agent" / "evals"

_spec = importlib.util.spec_from_file_location("run_eval", EVALS / "run_eval.py")
run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_eval)

TASKS = run_eval.task_ids()
SECTIONS = ("## Prompt", "## Seeded defect", "## Expected agents and skills", "## Rubric")
FIELDS = ("id", "category", "risk tier", "fixture", "test command", "oracle at HEAD")


def _fields(text):
    return {m.group(1).strip(): m.group(2).strip()
            for m in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$", text, re.M)}


def test_ten_golden_tasks_with_required_mix():
    assert len(TASKS) == 10
    cats = [_fields((EVALS / "tasks" / f"{t}.md").read_text())["category"] for t in TASKS]
    assert sum(c.startswith("seeded-bug") for c in cats) >= 3
    for needed in ("security-fix", "lookup", "mechanical", "spec-conformance",
                   "exploration", "control", "feature"):
        assert needed in cats, needed


@pytest.mark.parametrize("task", TASKS)
def test_task_file_has_required_sections_and_fixture(task):
    text = (EVALS / "tasks" / f"{task}.md").read_text()
    for heading in SECTIONS:
        assert re.search(rf"^{re.escape(heading)}", text, re.M), f"{task}: missing {heading}"
    fields = _fields(text)
    for key in FIELDS:
        assert fields.get(key), f"{task}: missing field {key!r}"
    assert fields["id"] == f"`{task}`"
    assert fields["oracle at HEAD"] in ("pass", "fail", "none")
    assert (EVALS / "fixtures" / task).is_dir(), f"{task}: fixture missing"
    rubric = text.split("## Rubric", 1)[1]
    assert "PASS" in rubric and "FAIL" in rubric
    assert (EVALS / "fixtures" / task / "_oracle").is_dir() == (fields["oracle at HEAD"] != "none")


@pytest.mark.parametrize("task", TASKS)
def test_fixture_materializes_tests_green_and_oracle_matches(task, tmp_path):
    dest = run_eval.materialize(task, tmp_path / "repo")
    files = {p.name for p in dest.iterdir()}
    assert not files & {"_step", "_oracle", "_solution", ".message"}, files
    assert not any(p.name.startswith("oracle") for p in dest.rglob("*.py"))
    log = subprocess.run(["git", "log", "--format=%s"], cwd=dest,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    has_step = (EVALS / "fixtures" / task / "_step").is_dir()
    assert len(log) == (2 if has_step else 1)
    assert subprocess.run(["git", "status", "--porcelain"], cwd=dest,
                          capture_output=True, text=True).stdout == ""

    res = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=dest,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr

    expected = _fields((EVALS / "tasks" / f"{task}.md").read_text())["oracle at HEAD"]
    got = run_eval.grade(task, dest)
    assert got == {"pass": True, "fail": False, "none": None}[expected]


@pytest.mark.parametrize("task", [t for t in TASKS
                                  if (EVALS / "fixtures" / t / "_oracle").is_dir()])
def test_oracle_is_satisfiable_by_reference_solution(task, tmp_path):
    fixture = EVALS / "fixtures" / task
    if not (fixture / "_solution").is_dir():
        pytest.skip("oracle already passes at HEAD (control task)")
    dest = run_eval.materialize(task, tmp_path / "repo", solution=True)
    assert run_eval.grade(task, dest) is True
    res = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=dest,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_materialize_resolves_number_and_rejects_nonempty_dest(tmp_path):
    dest = run_eval.materialize("03", tmp_path / "a")
    assert (dest / "pager.py").is_file()
    assert "total // size" in (dest / "pager.py").read_text()   # step commit applied
    with pytest.raises(SystemExit):
        run_eval.materialize("03", dest)
    with pytest.raises(SystemExit):
        run_eval.materialize("99", tmp_path / "b")


def test_materialize_is_deterministic(tmp_path):
    heads = []
    for name in ("x", "y"):
        dest = run_eval.materialize("04", tmp_path / name)
        heads.append(subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest,
                                    capture_output=True, text=True).stdout)
    assert heads[0] == heads[1]


def _rec(ledger, **kw):
    base = dict(task="03", config="baseline", caught_bug=True, skills_ok=True,
                tokens=1000, wall_s=10.0, rework=0, rubric_pass=True)
    return run_eval.record(ledger, **{**base, **kw})


def test_record_appends_rows_and_autonumbers_runs(tmp_path):
    ledger = tmp_path / "results" / "ledger.jsonl"
    a = _rec(ledger)
    b = _rec(ledger, rubric_pass=False)
    c = _rec(ledger, config="spec-merged")
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(rows) == 3
    assert (a["run"], b["run"], c["run"]) == (1, 2, 1)
    assert rows[0]["task"] == "03-review-off-by-one"
    for key in ("task", "config", "run", "caught_bug", "skills_ok", "tokens",
                "wall_s", "rework", "rubric_pass"):
        assert key in rows[0]


def test_report_pass_rate_and_flags_flipped(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    _rec(ledger)
    _rec(ledger, rubric_pass=False, caught_bug=False)          # baseline flips
    _rec(ledger, config="spec-merged")
    _rec(ledger, config="spec-merged")                         # stable
    _rec(ledger, task="09", config="baseline", caught_bug=None)  # single run
    out = io.StringIO()
    flags = run_eval.report(ledger, out=out)
    text = out.getvalue()
    assert "FLIPPED:rubric_pass" in flags[("03-review-off-by-one", "baseline")]
    assert "FLIPPED:caught_bug" in flags[("03-review-off-by-one", "baseline")]
    assert flags[("03-review-off-by-one", "spec-merged")] == []
    assert flags[("09-clean-pass-control", "baseline")] == ["FEW-RUNS"]
    row = next(l for l in text.splitlines() if l.startswith("03-review-off-by-one")
               and "baseline" in l)
    assert " 1/2 " in row
    assert "inspect flipped tasks" in text and "03-review-off-by-one" in text.split("inspect")[1]


def test_cli_record_and_report_round_trip(tmp_path):
    ledger = tmp_path / "l.jsonl"
    script = str(EVALS / "run_eval.py")
    res = subprocess.run([sys.executable, script, "record", "--task", "01", "--config",
                          "baseline", "--caught-bug", "na", "--skills-ok", "y", "--tokens",
                          "500", "--wall-s", "4", "--rework", "0", "--rubric-pass", "y",
                          "--ledger", str(ledger)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["caught_bug"] is None
    res = subprocess.run([sys.executable, script, "report", "--ledger", str(ledger)],
                         capture_output=True, text=True)
    assert res.returncode == 0 and "01-lookup-direct" in res.stdout


def test_results_ledger_is_gitignored():
    res = subprocess.run(["git", "check-ignore", "-q",
                          "skills/agent/evals/results/ledger.jsonl"], cwd=REPO)
    assert res.returncode == 0
