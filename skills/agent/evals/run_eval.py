#!/usr/bin/env python3
"""Golden-task eval helper for the agent fleet (stdlib only).

  run_eval.py list
  run_eval.py materialize <task> [dest]      fresh git repo from fixtures/<task>/
  run_eval.py grade <task> <dir>             run the hidden oracle against a final result
  run_eval.py record --task T --config C ... append one run to the ledger
  run_eval.py report [--ledger PATH]         pass rate per task x config, flags flips

<task> is a task id ("03-review-off-by-one") or its number ("03").

Fixture layout: fixtures/<task>/ holds the base repo. An optional `_step/` overlay is
committed on top as a second commit (the "step under review", so HEAD~1..HEAD is the
diff). An optional `_oracle/` holds hidden `oracle*.py` unittest files: never copied by
materialize, only run by `grade` in a throwaway copy of the result. An optional
`_solution/` overlay is a reference fix, used only by the self-tests to prove the
oracle is satisfiable (`materialize --solution`); never show it to the orchestrator.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVALS = Path(__file__).resolve().parent
TASKS = EVALS / "tasks"
FIXTURES = EVALS / "fixtures"
DEFAULT_LEDGER = EVALS / "results" / "ledger.jsonl"
HIDDEN = {"_step", "_oracle", "_solution", "__pycache__"}
# Fixed identity + dates so every materialized repo has identical history.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "eval", "GIT_AUTHOR_EMAIL": "eval@example.invalid",
    "GIT_COMMITTER_NAME": "eval", "GIT_COMMITTER_EMAIL": "eval@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


def task_ids():
    return sorted(p.stem for p in TASKS.glob("[0-9][0-9]-*.md"))


def resolve(task):
    ids = task_ids()
    if task in ids:
        return task
    hits = [t for t in ids if t.split("-", 1)[0] == task]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"unknown task {task!r}; known: {', '.join(ids)}")


def _copy_tree(src, dest):
    for item in src.iterdir():
        if item.name in HIDDEN:
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(item, target)


def _git(dest, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                    *args], cwd=dest, check=True, capture_output=True,
                   env={**os.environ, **GIT_ENV})


def materialize(task, dest=None, solution=False):
    task = resolve(task)
    src = FIXTURES / task
    if not src.is_dir():
        raise SystemExit(f"no fixture for {task}: {src}")
    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix=f"eval-{task}-"))
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"destination not empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    _copy_tree(src, dest)
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", f"base: {task}")
    step = src / "_step"
    if step.is_dir():
        _copy_tree(step, dest)
        msg = (step / ".message").read_text().strip() if (step / ".message").is_file() \
            else f"step under review: {task}"
        message_file = dest / ".message"
        if message_file.exists():
            message_file.unlink()
        _git(dest, "add", "-A")
        _git(dest, "commit", "-q", "-m", msg)
    if solution:
        ref = src / "_solution"
        if not ref.is_dir():
            raise SystemExit(f"no reference solution for {task}")
        _copy_tree(ref, dest)  # left uncommitted: the "final result" to grade
    return dest


def grade(task, result_dir):
    """Run the task's hidden oracle against result_dir. True/False, or None if no oracle."""
    task = resolve(task)
    oracle = FIXTURES / task / "_oracle"
    if not oracle.is_dir():
        return None
    with tempfile.TemporaryDirectory(prefix=f"grade-{task}-") as tmp:
        work = Path(tmp) / "work"
        shutil.copytree(result_dir, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        for f in oracle.glob("oracle*.py"):
            shutil.copy2(f, work / f.name)
        res = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q",
                              "-s", ".", "-p", "oracle*.py"], cwd=work,
                             capture_output=True, text=True)
        sys.stderr.write(res.stderr[-2000:])
        return res.returncode == 0


def _yn(value):
    v = str(value).strip().lower()
    if v in ("y", "yes", "true", "1"):
        return True
    if v in ("n", "no", "false", "0"):
        return False
    if v in ("na", "n/a", "none", "-"):
        return None
    raise argparse.ArgumentTypeError(f"expected y / n / na, got {value!r}")


def _read(ledger):
    ledger = Path(ledger)
    if not ledger.is_file():
        return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]


def record(ledger=DEFAULT_LEDGER, *, task, config, run=None, caught_bug=None,
           skills_ok, tokens, wall_s, rework, rubric_pass, notes=""):
    task = resolve(task)
    ledger = Path(ledger)
    if run is None:
        run = 1 + sum(1 for r in _read(ledger) if r["task"] == task and r["config"] == config)
    row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "task": task, "config": config, "run": run, "caught_bug": caught_bug,
           "skills_ok": skills_ok, "tokens": tokens, "wall_s": wall_s,
           "rework": rework, "rubric_pass": rubric_pass, "notes": notes}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _rate(values):
    vals = [v for v in values if v is not None]
    return f"{sum(vals)}/{len(vals)}" if vals else "-"


def report(ledger=DEFAULT_LEDGER, out=sys.stdout):
    rows = _read(ledger)
    if not rows:
        print(f"no runs in {ledger}", file=out)
        return {}
    groups = defaultdict(list)
    for r in rows:
        groups[(r["task"], r["config"])].append(r)
    configs = sorted({c for _, c in groups})
    flags = {}
    print(f"{'task':<28} {'config':<14} runs pass  caught skills tokens   wall_s rework flags",
          file=out)
    for (task, config) in sorted(groups):
        runs = groups[(task, config)]
        f = []
        for key in ("rubric_pass", "caught_bug", "skills_ok"):
            if len({r[key] for r in runs if r[key] is not None}) > 1:
                f.append(f"FLIPPED:{key}")
        if len(runs) < 2:
            f.append("FEW-RUNS")
        flags[(task, config)] = f
        mean = lambda k: sum(r[k] for r in runs) / len(runs)
        print(f"{task:<28} {config:<14} {len(runs):>4} {_rate(r['rubric_pass'] for r in runs):>5} "
              f"{_rate(r['caught_bug'] for r in runs):>6} {_rate(r['skills_ok'] for r in runs):>6} "
              f"{mean('tokens'):>7.0f} {mean('wall_s'):>7.0f} {mean('rework'):>6.1f} "
              f"{' '.join(f)}", file=out)
    print("\nper config (all tasks):", file=out)
    for config in configs:
        runs = [r for (t, c), rs in groups.items() if c == config for r in rs]
        print(f"  {config:<14} pass {_rate(r['rubric_pass'] for r in runs):>6}  "
              f"caught {_rate(r['caught_bug'] for r in runs):>6}  "
              f"tokens {sum(r['tokens'] for r in runs):>9}  "
              f"rework {sum(r['rework'] for r in runs):>3}", file=out)
    flipped = sorted({t for (t, _), f in flags.items() if any(x.startswith("FLIPPED") for x in f)})
    if flipped:
        print("\ninspect flipped tasks (read their transcripts, not just scores): "
              + ", ".join(flipped), file=out)
    return flags


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    m = sub.add_parser("materialize")
    m.add_argument("task")
    m.add_argument("dest", nargs="?")
    m.add_argument("--solution", action="store_true",
                   help="self-test only: apply the hidden reference fix on top")
    g = sub.add_parser("grade")
    g.add_argument("task")
    g.add_argument("dir")
    r = sub.add_parser("record")
    r.add_argument("--task", required=True)
    r.add_argument("--config", required=True)
    r.add_argument("--run", type=int)
    r.add_argument("--caught-bug", type=_yn, default=None, help="y / n / na (no seeded bug)")
    r.add_argument("--skills-ok", type=_yn, required=True)
    r.add_argument("--tokens", type=int, required=True)
    r.add_argument("--wall-s", type=float, required=True)
    r.add_argument("--rework", type=int, required=True)
    r.add_argument("--rubric-pass", type=_yn, required=True)
    r.add_argument("--notes", default="")
    r.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    rp = sub.add_parser("report")
    rp.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    a = p.parse_args(argv)

    if a.cmd == "list":
        for t in task_ids():
            print(t)
    elif a.cmd == "materialize":
        print(materialize(a.task, a.dest, solution=a.solution))
    elif a.cmd == "grade":
        ok = grade(a.task, a.dir)
        print({True: "PASS", False: "FAIL", None: "NO-ORACLE (grade by rubric)"}[ok])
        return 0 if ok is not False else 1
    elif a.cmd == "record":
        row = record(a.ledger, task=a.task, config=a.config, run=a.run,
                     caught_bug=a.caught_bug, skills_ok=a.skills_ok, tokens=a.tokens,
                     wall_s=a.wall_s, rework=a.rework, rubric_pass=a.rubric_pass,
                     notes=a.notes)
        print(json.dumps(row))
    elif a.cmd == "report":
        report(a.ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
