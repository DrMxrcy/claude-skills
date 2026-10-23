"""Numbered slot reservations (plan 33): rmlib/slots.py + `slot` / `status --slots`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"
KIND = {"glob": "db/*.sql", "pattern": r"^(\d{4})_", "width": 4}


@pytest.fixture
def slots(roadmap):
    """rmlib.slots / rmlib.branches with their module caches cleared."""
    import importlib
    for name in ("rmlib.slots", "rmlib.branches"):
        importlib.import_module(name)._CACHE.clear()
    return importlib.import_module("rmlib.slots")


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


def _commit_all(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)


def _write(repo, rel, text="-- sql\n"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _configure(roadmap, repo, kinds=None):
    cfg = roadmap.read_config(repo)
    cfg["settings"]["slots"] = {"migration": dict(KIND)} if kinds is None else kinds
    roadmap.write_config(repo, cfg)


@pytest.fixture
def proj(roadmap, slots, repo, monkeypatch):
    """main with db/0267_a.sql + db/0268_b.sql, six planned items, the
    `migration` kind configured, everything committed."""
    monkeypatch.chdir(repo)
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    roadmap.init_project(repo, "P", claude_md=False)
    for n in range(6):
        roadmap.new_item(repo, "feature", f"Item {n + 1}")
    _configure(roadmap, repo)
    _write(repo, "db/0267_a.sql")
    _write(repo, "db/0268_b.sql")
    _write(repo, "db/meta/0999_journal.sql")     # not matched: glob is one level
    _commit_all(repo, "init")
    return repo


def _plan(repo, n):
    return next((repo / ".roadmap/plans").glob(f"{n:03d}-*.md"))


def _slot_status(roadmap, repo):
    return roadmap.status(repo)["slots"]


def _res(payload, plan):
    return next(r for k in payload["kinds"] for r in k["reservations"]
                if r["plan"] == plan)


# ---- step 1: config, trunk scan, reserve / release ------------------------

def test_glob_and_prefix(slots):
    rx = slots._glob_re("db/*.sql")
    assert rx.match("db/0001_x.sql") and not rx.match("db/meta/0001_x.sql")
    deep = slots._glob_re("pkgs/**/drizzle/*.sql")
    assert deep.match("pkgs/drizzle/1_a.sql") and deep.match("pkgs/a/b/drizzle/1_a.sql")
    assert slots._literal_prefix("packages/db/drizzle/*.sql") == "packages/db/drizzle"
    assert slots._literal_prefix("**/m/*.sql") == ""


@pytest.mark.parametrize("bad, msg", [
    ({"m": {"pattern": r"^(\d+)"}}, "glob is required"),
    ({"m": {"glob": "db/*.sql"}}, "pattern is required"),
    ({"m": {"glob": "db/*.sql", "pattern": r"^\d+"}}, "group"),
    ({"m": {"glob": "db/*.sql", "pattern": "("}}, "does not compile"),
    ({"m": {"glob": "../x/*.sql", "pattern": r"(\d+)"}}, "relative"),
    ({"m": {"glob": "db/*.sql", "pattern": r"(\d+)", "width": "4"}}, "width"),
    ({"bad kind": {"glob": "db/*.sql", "pattern": r"(\d+)"}}, "kind names"),
    (["x"], "must be an object"),
])
def test_load_kinds_rejects_bad_config(slots, bad, msg):
    with pytest.raises(ValueError, match=msg):
        slots.load_kinds({"settings": {"slots": bad}})


def test_reserve_takes_next_after_trunk_then_after_reservations(roadmap, proj):
    """Acceptance: trunk at 0268 -> 0269 then 0270."""
    assert roadmap.main(["slot", "5", "--kind", "migration", "--name", "x"]) == 0
    assert roadmap.main(["slot", "6", "--kind", "migration"]) == 0
    meta5 = roadmap.parse_plan(_plan(proj, 5))["meta"]
    meta6 = roadmap.parse_plan(_plan(proj, 6))["meta"]
    assert meta5["slot_migration"] == "0269_x"
    assert meta6["slot_migration"] == "0270"
    assert roadmap.count_progress(_plan(proj, 5)) == (0, 2)       # body untouched


def test_reserve_prints_value_and_is_idempotent(roadmap, proj, capsys):
    roadmap.main(["slot", "1", "--kind", "migration", "--name", "a"])
    assert capsys.readouterr().out.strip() == "0269_a"
    assert roadmap.main(["slot", "1", "--kind", "migration"]) == 0
    io = capsys.readouterr()
    assert io.out.strip() == "0269_a" and "already holds" in io.err
    # a different name is refused instead of silently renumbering
    assert roadmap.main(["slot", "1", "--kind", "migration", "--name", "zz"]) == 1
    assert "release it first" in capsys.readouterr().err


def test_reserve_add_and_release(roadmap, proj, capsys):
    roadmap.main(["slot", "1", "--kind", "migration", "--name", "a"])
    roadmap.main(["slot", "1", "--kind", "migration", "--name", "a_rls", "--add"])
    meta = roadmap.parse_plan(_plan(proj, 1))["meta"]
    assert meta["slot_migration"] == "0269_a, 0270_a_rls"
    capsys.readouterr()
    assert roadmap.main(["slot", "1", "--kind", "migration", "--release"]) == 0
    assert "released migration 0269_a, 0270_a_rls" in capsys.readouterr().out
    assert "slot_migration" not in roadmap.parse_plan(_plan(proj, 1))["meta"]
    assert roadmap.main(["slot", "1", "--kind", "migration", "--release"]) == 0
    assert "no migration reservation" in capsys.readouterr().out
    # released numbers are free again
    roadmap.main(["slot", "2", "--kind", "migration"])
    assert roadmap.parse_plan(_plan(proj, 2))["meta"]["slot_migration"] == "0269"


def test_reserve_errors(roadmap, proj, capsys):
    assert roadmap.main(["slot", "1", "--kind", "adr"]) == 1
    assert "unknown slot kind 'adr'" in capsys.readouterr().err
    assert roadmap.main(["slot", "1", "--kind", "migration", "--name", "a b"]) == 1
    assert "invalid slot name" in capsys.readouterr().err
    assert roadmap.main(["slot", "99", "--kind", "migration"]) == 1
    roadmap.check_step(proj, 4, None, all_done=True)
    assert roadmap.main(["slot", "4", "--kind", "migration"]) == 1
    assert "done" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        roadmap.main(["slot", "1"])                      # no --kind


def test_reserve_without_config_explains(roadmap, repo, slots, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    assert roadmap.main(["slot", "1", "--kind", "migration"]) == 1
    assert "no slot kinds configured" in capsys.readouterr().err


def test_reserve_outside_git_scans_working_tree(roadmap, slots, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roadmap.init_project(tmp_path, "P", claude_md=False)
    roadmap.new_item(tmp_path, "feature", "A")
    _configure(roadmap, tmp_path)
    _write(tmp_path, "db/0041_x.sql")
    res = slots.reserve(tmp_path, 1, "migration")
    assert res["token"] == "0042"


def test_width_inferred_when_unset(roadmap, proj, slots):
    _configure(roadmap, proj, {"migration": {"glob": "db/*.sql", "pattern": r"^(\d+)_"}})
    assert slots.reserve(proj, 1, "migration")["token"] == "0269"


def test_reserve_skips_numbers_already_added_on_branches(roadmap, proj, slots):
    _git(proj, "checkout", "-qb", "fix/side")
    _write(proj, "db/0275_side.sql")
    _commit_all(proj, "side migration")
    _git(proj, "checkout", "-q", "main")
    assert slots.reserve(proj, 1, "migration")["token"] == "0276"


def test_reserve_sees_trunk_plans_from_a_branch_checkout(roadmap, proj, slots):
    """A worktree cut before a trunk reservation still never reuses it."""
    wt = proj.parent / (proj.name + "-wt")
    _git(proj, "worktree", "add", "-q", "-b", "roadmap/2", str(wt))
    slots.reserve(proj, 1, "migration")                # 0269, committed on trunk
    _commit_all(proj, "reserve (plan 1)")
    # the main checkout steps off trunk, so only the trunk REF holds 0269 now
    _git(proj, "checkout", "-q", "--detach", "HEAD~1")
    assert "slot_migration" not in _plan(proj, 1).read_text()
    slots._CACHE.clear()
    assert slots.reserve(wt, 2, "migration")["token"] == "0270"


def test_reserve_sees_uncommitted_reservations_in_other_worktrees(roadmap, proj, slots):
    wt = proj.parent / (proj.name + "-wt2")
    _git(proj, "worktree", "add", "-q", "-b", "roadmap/3", str(wt))
    assert slots.reserve(wt, 3, "migration")["token"] == "0269"    # uncommitted
    assert slots.reserve(proj, 1, "migration")["token"] == "0270"


def test_concurrent_reservations_never_share_a_number(roadmap, proj):
    """Fails if: two reservations can receive the same number."""
    procs = [subprocess.Popen([sys.executable, str(SCRIPT), "slot", str(n),
                               "--kind", "migration"], cwd=proj,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for n in range(1, 7)]
    outs = [p.communicate(timeout=60) for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    got = sorted(o.strip() for o, _ in outs)
    assert got == ["0269", "0270", "0271", "0272", "0273", "0274"]


# ---- step 2: match states and slot --check --------------------------------

def _branch_with(repo, branch, files, msg):
    _git(repo, "checkout", "-qb", branch)
    for f in files:
        _write(repo, f)
    _commit_all(repo, msg)
    _git(repo, "checkout", "-q", "main")


def test_states_ok_missing_and_stray_clash(roadmap, proj, slots, capsys):
    """Acceptance: branch adds 0271 for a plan that reserved 0269 -> clash,
    `slot --check` exits 1."""
    slots.reserve(proj, 1, "migration", name="x")     # 0269
    slots.reserve(proj, 2, "migration")               # 0270
    slots.reserve(proj, 3, "migration")               # 0271 — no branch
    _commit_all(proj, "reservations")
    _branch_with(proj, "roadmap/1", ["db/0271_x.sql"], "migration (plan 1)")
    _branch_with(proj, "roadmap/2", ["db/0270_y.sql"], "migration (plan 2)")
    p = _slot_status(roadmap, proj)
    assert p["kinds"][0]["trunkHighest"] == "0268"
    assert p["kinds"][0]["branchHighest"] == "0271"
    r1, r2, r3 = _res(p, 1), _res(p, 2), _res(p, 3)
    assert (r1["state"], r1["detail"]) == ("clash", "branch adds 0271_x.sql (not reserved)")
    assert r1["branch"] == "roadmap/1" and r1["lane"] == "building"
    assert (r2["state"], r2["detail"]) == ("ok", "branch adds 0270")
    assert (r3["state"], r3["detail"]) == ("missing", "no branch yet")
    capsys.readouterr()
    assert roadmap.main(["slot", "--check"]) == 1
    out = capsys.readouterr().out
    assert "slot check: 1 clash(es)" in out and "#1 migration clash" in out
    assert roadmap.main(["slot", "2", "--check"]) == 0          # plan-scoped gate
    assert "slot check: no clashes" in capsys.readouterr().out


def test_branch_without_slot_file_is_missing(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration")
    _commit_all(proj, "reserve")
    _branch_with(proj, "roadmap/1", ["src/a.py"], "code (plan 1)")
    r = _res(_slot_status(roadmap, proj), 1)
    assert (r["state"], r["detail"]) == ("missing", "no 0269 on roadmap/1 yet")
    assert roadmap.main(["slot", "--check"]) == 0


def test_two_plans_same_number_clash(roadmap, proj, slots, capsys):
    slots.reserve(proj, 1, "migration")
    path = _plan(proj, 2)        # a hand edit (or a bad merge) double-books 0269
    path.write_text(slots._apply_slot(path.read_text(), "migration", "0269_dup"))
    p = _slot_status(roadmap, proj)
    assert _res(p, 1)["state"] == _res(p, 2)["state"] == "clash"
    assert _res(p, 1)["detail"] == "0269 also reserved by #2"
    assert p["clashes"] == 2
    assert roadmap.main(["slot", "--check", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert {f["plan"] for f in data["failures"]} == {1, 2}


def test_taken_when_trunk_gains_the_number_from_elsewhere(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration", name="mine")
    _write(proj, "db/0269_someone_else.sql")
    _commit_all(proj, "hotfix migration")
    r = _res(_slot_status(roadmap, proj), 1)
    assert (r["state"], r["detail"]) == ("taken", "trunk already has 0269 (0269_someone_else.sql)")
    assert roadmap.main(["slot", "--check"]) == 1


def test_landed_reservation_is_ok(roadmap, proj, slots):
    """Squash-merged work: trunk has the reserved file name -> ok, not taken."""
    slots.reserve(proj, 1, "migration", name="mine")
    _write(proj, "db/0269_mine.sql")
    _commit_all(proj, "squash (plan 1)")
    r = _res(_slot_status(roadmap, proj), 1)
    assert (r["state"], r["detail"]) == ("ok", "on trunk")


def test_merged_branch_reservation_is_ok(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration")
    _commit_all(proj, "reserve")
    _branch_with(proj, "roadmap/1", ["db/0269_m.sql"], "m (plan 1)")
    _git(proj, "merge", "-q", "--ff-only", "roadmap/1")
    r = _res(_slot_status(roadmap, proj), 1)
    assert r["state"] == "ok"


def test_inherited_commits_tagged_for_other_plans_are_not_strays(roadmap, proj, slots):
    """Stacked branches: roadmap/2 is cut from roadmap/1 and carries its
    migration; only plan 2's own commits count against plan 2."""
    slots.reserve(proj, 1, "migration")       # 0269
    slots.reserve(proj, 2, "migration")       # 0270
    _commit_all(proj, "reserve")
    _git(proj, "checkout", "-qb", "roadmap/1")
    _write(proj, "db/0269_one.sql")
    _commit_all(proj, "one (plan 1)")
    _git(proj, "checkout", "-qb", "roadmap/2")
    _write(proj, "db/0270_two.sql")
    _commit_all(proj, "two (plan 2)")
    _git(proj, "checkout", "-q", "main")
    p = _slot_status(roadmap, proj)
    assert _res(p, 1)["state"] == "ok" and _res(p, 2)["state"] == "ok"


def test_renumbered_file_counts_only_final_name(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration")       # 0269
    _commit_all(proj, "reserve")
    _git(proj, "checkout", "-qb", "roadmap/1")
    _write(proj, "db/0271_x.sql")
    _commit_all(proj, "x (plan 1)")
    _git(proj, "mv", "db/0271_x.sql", "db/0269_x.sql")
    _commit_all(proj, "renumber (plan 1)")
    _git(proj, "checkout", "-q", "main")
    assert _res(_slot_status(roadmap, proj), 1)["state"] == "ok"


def test_claimed_branch_wins_for_match(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration")
    _commit_all(proj, "reserve")
    _branch_with(proj, "feature/odd-name", ["db/0269_z.sql"], "z")
    roadmap.set_claim(proj, 1, stage="review", branch="feature/odd-name")
    r = _res(_slot_status(roadmap, proj), 1)
    assert r["state"] == "ok" and r["branch"] == "feature/odd-name"


def test_done_plans_drop_out_of_the_listing(roadmap, proj, slots):
    slots.reserve(proj, 1, "migration")
    roadmap.check_step(proj, 1, None, all_done=True)
    assert _slot_status(roadmap, proj)["kinds"][0]["reservations"] == []


# ---- step 3: status payload and `status --slots` --------------------------

def test_no_config_leaves_status_unchanged(roadmap, repo, slots, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    st = roadmap.status(repo)
    assert "slots" not in st
    assert set(st) == {"project", "currentVersion", "versionComplete", "counts",
                       "items", "trunk", "otherBranches"}
    assert roadmap.main(["status", "--slots"]) == 0
    assert "no slot kinds configured" in capsys.readouterr().out


def test_bad_config_never_breaks_status(roadmap, proj, capsys):
    _configure(roadmap, proj, {"migration": {"glob": "db/*.sql"}})
    st = roadmap.status(proj)
    assert "pattern is required" in st["slots"]["error"]
    assert st["items"]                                  # rest of status intact
    assert roadmap.main(["slot", "--check"]) == 1


def test_status_slots_text_and_json(roadmap, proj, slots, capsys):
    slots.reserve(proj, 1, "migration", name="x")
    capsys.readouterr()
    assert roadmap.main(["status", "--slots"]) == 0
    out = capsys.readouterr().out
    assert "migration · db/*.sql · trunk highest 0268" in out
    assert "0269_x" in out and "FEAT-1" in out and "missing" in out
    assert roadmap.main(["status", "--slots", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    r = data["slots"]["kinds"][0]["reservations"][0]
    assert r["numbers"] == ["0269"] and r["state"] == "missing"
    assert r["displayId"] == "FEAT-1" and r["source"] == "local"


def test_branch_checkout_lists_trunk_only_plans(roadmap, proj, slots):
    """A plan created and reserved on trunk after a worktree forked shows up in
    the worktree's listing (source trunk) so its clashes are visible there."""
    wt = proj.parent / (proj.name + "-wt3")
    _git(proj, "worktree", "add", "-q", "-b", "roadmap/9", str(wt))
    roadmap.new_item(proj, "feature", "Late")           # id 7, trunk only
    slots.reserve(proj, 7, "migration", name="late")
    _commit_all(proj, "late plan")
    slots._CACHE.clear()
    p = roadmap.status(wt)["slots"]
    r = _res(p, 7)
    assert r["source"] == "trunk" and r["value"] == "0269_late"


def test_slot_scan_git_calls_are_cached(roadmap, proj, slots, monkeypatch):
    slots.reserve(proj, 1, "migration")
    _commit_all(proj, "reserve")
    _branch_with(proj, "roadmap/1", ["db/0269_a.sql"], "a (plan 1)")
    roadmap.status(proj)
    calls = []
    real = slots._git
    monkeypatch.setattr(slots, "_git", lambda root, *a, **k: calls.append(a[0]) or real(root, *a, **k))
    roadmap.status(proj)
    assert calls == ["rev-parse"]          # tree/log results come from the cache
