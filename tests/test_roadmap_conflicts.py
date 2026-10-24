"""Branch conflict risk (plan 41): rmlib/conflicts.py, `status --conflicts`,
payload and dashboard hooks."""
import hashlib
import importlib
import json
import subprocess
import threading

import pytest


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


def _write(repo, name, text):
    (repo / name).write_text(text)


def _commit_files(repo, msg, **files):
    for name, text in files.items():
        _write(repo, name.replace("__", "."), text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)


@pytest.fixture
def cf(roadmap):
    mod = importlib.import_module("rmlib.conflicts")
    mod._FILES.clear()
    mod._PAIRS.clear()
    mod._MT.clear()
    importlib.import_module("rmlib.branches")._CACHE.clear()
    return mod


BASE_X = "".join(f"line {n}\n" for n in range(1, 21))


@pytest.fixture
def abc(repo):
    """main with x.py / y.py; branch A and B both rewrite x.py line 1, C edits
    y.py alone. Returns {name: tip sha} plus the trunk sha under "main"."""
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit_files(repo, "init", x__py=BASE_X, y__py="y\n")
    shas = {}
    for name, files in (("A", {"x__py": "A edit\n" + BASE_X.split("\n", 1)[1]}),
                        ("B", {"x__py": "B edit\n" + BASE_X.split("\n", 1)[1]}),
                        ("C", {"y__py": "C edit\n"})):
        _git(repo, "checkout", "-qb", name, "main")
        _commit_files(repo, f"{name} work", **files)
        shas[name] = _git(repo, "rev-parse", "HEAD").strip()
        _git(repo, "checkout", "-q", "main")
    shas["main"] = _git(repo, "rev-parse", "main").strip()
    return shas


def _cands(shas, *names):
    return [{"id": i, "displayId": f"F{i}", "title": n, "branch": n,
             "sha": shas[n], "landedIn": None}
            for i, n in enumerate(names, 1)]


def _repo_state(repo):
    """Everything a read-only command must leave alone: refs, HEAD, index,
    worktree status."""
    idx = repo / ".git" / "index"
    return (_git(repo, "for-each-ref", "--format=%(refname) %(objectname)"),
            _git(repo, "rev-parse", "HEAD"),
            hashlib.sha1(idx.read_bytes()).hexdigest() if idx.exists() else None,
            _git(repo, "status", "--porcelain"))


def test_changed_files_vs_trunk(cf, repo, abc):
    assert cf.changed_files(repo, "A") == ["x.py"]
    assert cf.changed_files(repo, "C") == ["y.py"]
    assert cf.changed_files(repo, "nope") is None
    assert cf.changed_files_at(repo, abc["main"], abc["B"]) == ["x.py"]
    # stacked: E cut from A sees x.py vs trunk, only its own z.py vs A
    _git(repo, "checkout", "-qb", "E", "A")
    _commit_files(repo, "E work", z__py="z\n")
    _git(repo, "checkout", "-q", "main")
    assert cf.changed_files(repo, "E") == ["x.py", "z.py"]
    assert cf.changed_files(repo, "E", base="A") == ["z.py"]
    assert cf.changed_files(repo, "E", base="nope") is None


def test_same_lines_is_high_and_lone_branch_leads_order(cf, repo, abc):
    rep = cf.overlaps(repo, abc["main"], _cands(abc, "A", "B", "C"))
    assert rep["mergeTree"] is True and rep["checked"] == 3
    assert len(rep["pairs"]) == 1
    p = rep["pairs"][0]
    assert {p["a"]["branch"], p["b"]["branch"]} == {"A", "B"}
    assert p["risk"] == "high" and p["files"] == ["x.py"]
    assert p["conflictFiles"] == ["x.py"]
    assert rep["counts"] == {"high": 1, "medium": 0, "low": 0}
    assert rep["order"][0]["branch"] == "C" and rep["order"][0]["overlaps"] == 0
    assert [o["overlaps"] for o in rep["order"]] == [0, 1, 1]


def test_without_merge_tree_overlap_is_medium(cf, repo, abc, monkeypatch):
    monkeypatch.setattr(cf, "merge_tree_supported", lambda: False)
    rep = cf.overlaps(repo, abc["main"], _cands(abc, "A", "B", "C"))
    assert rep["mergeTree"] is False
    assert [p["risk"] for p in rep["pairs"]] == ["medium"]
    assert rep["pairs"][0]["files"] == ["x.py"]
    assert "file overlap only" in cf.format_conflicts(rep)


def test_shared_file_different_lines_is_low(cf, repo, abc):
    _git(repo, "checkout", "-qb", "D", "main")
    lines = BASE_X.splitlines(keepends=True)
    lines[-1] = "D edit at the bottom\n"
    _commit_files(repo, "D work", x__py="".join(lines))
    abc["D"] = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    rep = cf.overlaps(repo, abc["main"], _cands(abc, "A", "D"))
    assert [p["risk"] for p in rep["pairs"]] == ["low"]
    assert rep["pairs"][0]["conflictFiles"] == []


def test_shared_files_capped_at_ten(cf, repo):
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit_files(repo, "init", base__txt="b\n")
    tips = {}
    for name in ("P", "Q"):
        _git(repo, "checkout", "-qb", name, "main")
        _commit_files(repo, name, **{f"f{n}__py": f"{name}{n}\n" for n in range(12)})
        tips[name] = _git(repo, "rev-parse", "HEAD").strip()
        _git(repo, "checkout", "-q", "main")
    tips["main"] = _git(repo, "rev-parse", "main").strip()
    rep = cf.overlaps(repo, tips["main"], _cands(tips, "P", "Q"))
    p = rep["pairs"][0]
    assert p["fileCount"] == 12 and len(p["files"]) == 10
    assert "+2 more" in cf.format_conflicts(rep)


def test_cached_on_tips_no_git_when_unchanged(cf, repo, abc, monkeypatch):
    cands = _cands(abc, "A", "B", "C")
    first = cf.overlaps(repo, abc["main"], cands)
    calls = []
    real = subprocess.run

    def counting(cmd, *a, **k):
        # any thread (the cold path fans out), but only git calls on this repo
        if cmd and cmd[0] == "git" and str(repo) in cmd:
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    assert cf.overlaps(repo, abc["main"], cands) == first
    assert calls == []
    # Moving one tip recomputes only that branch and its pairs.
    monkeypatch.setattr(subprocess, "run", real)
    _git(repo, "checkout", "-q", "C")
    _commit_files(repo, "C more", z__py="z\n")
    abc["C"] = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "main")
    monkeypatch.setattr(subprocess, "run", counting)
    cf.overlaps(repo, abc["main"], _cands(abc, "A", "B", "C"))
    assert len(calls) == 1 and "diff" in calls[0]


def test_landed_in_same_integration_branch_skipped(cf, repo, abc):
    cands = _cands(abc, "A", "B")
    for c in cands:
        c["landedIn"] = "integration"
    assert cf.overlaps(repo, abc["main"], cands)["pairs"] == []


def test_never_modifies_branches_or_index(cf, repo, abc):
    before = _repo_state(repo)
    cf.overlaps(repo, abc["main"], _cands(abc, "A", "B", "C"))
    cf.changed_files(repo, "B")
    assert _repo_state(repo) == before


def test_no_trunk_sha_is_empty_report(cf, repo, abc):
    rep = cf.overlaps(repo, None, _cands(abc, "A", "B"))
    assert rep["pairs"] == [] and rep["order"] == [] and rep["checked"] == 0


# --- status --conflicts, payload, merge order (step 2) ----------------------

@pytest.fixture
def items3(roadmap, cf, repo, monkeypatch):
    """Items 1-3 with branches roadmap/1 and roadmap/2 rewriting x.py line 1
    and roadmap/3 editing y.py alone. Roadmap files stay untracked."""
    monkeypatch.chdir(repo)
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _write(repo, "x.py", BASE_X)
    _write(repo, "y.py", "y\n")
    _git(repo, "add", "x.py", "y.py")
    _git(repo, "commit", "-qm", "init")
    roadmap.main(["init", "--name", "Demo"])
    for t in ("Alpha", "Beta", "Gamma"):
        roadmap.main(["new", "--type", "feature", "--title", t])
    rest = BASE_X.split("\n", 1)[1]
    for n, (path, text) in {1: ("x.py", "one\n" + rest), 2: ("x.py", "two\n" + rest),
                            3: ("y.py", "three\n")}.items():
        _git(repo, "checkout", "-qb", f"roadmap/{n}", "main")
        _write(repo, path, text)
        _git(repo, "add", path)
        _git(repo, "commit", "-qm", f"work (plan {n})")
        _git(repo, "checkout", "-q", "main")
    return repo


def test_status_conflicts_text_high_pair_and_order(roadmap, items3, capsys):
    before = _repo_state(items3)
    assert roadmap.main(["status", "--conflicts"]) == 0
    out = capsys.readouterr().out
    assert "1 high" in out
    high = next(l for l in out.splitlines() if l.strip().startswith("HIGH"))
    assert "roadmap/1" in high and "roadmap/2" in high and "x.py" in high
    order = out.split("suggested merge order", 1)[1].splitlines()[1:]
    assert "Gamma" in order[0] and "no overlaps" in order[0]
    assert _repo_state(items3) == before


def test_status_conflicts_json_and_payload(roadmap, items3, capsys):
    assert roadmap.main(["status", "--conflicts", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)["conflicts"]
    assert rep["checked"] == 3 and rep["counts"]["high"] == 1
    pair = rep["pairs"][0]
    assert {pair["a"]["id"], pair["b"]["id"]} == {1, 2}
    assert [o["id"] for o in rep["order"]] == [3, 1, 2]
    st = roadmap.status(items3)
    assert "conflicts" not in st and "trunkSha" not in st
    assert roadmap.status(items3, conflicts=True)["conflicts"] == rep


def test_status_conflicts_medium_without_merge_tree(roadmap, cf, items3,
                                                    monkeypatch, capsys):
    monkeypatch.setattr(cf, "merge_tree_supported", lambda: False)
    roadmap.main(["status", "--conflicts", "--json"])
    rep = json.loads(capsys.readouterr().out)["conflicts"]
    assert [p["risk"] for p in rep["pairs"]] == ["medium"]
    assert rep["pairs"][0]["files"] == ["x.py"]


def test_conflicts_skip_done_and_merged(roadmap, items3, capsys):
    _git(items3, "merge", "-q", "--no-edit", "roadmap/3")
    rep = roadmap.status(items3, conflicts=True)["conflicts"]
    assert rep["checked"] == 2 and {o["id"] for o in rep["order"]} == {1, 2}


def test_conflicts_payload_unchanged_refs_one_ref_scan(roadmap, items3, monkeypatch):
    st = roadmap.status(items3)
    first = roadmap.conflicts_payload(items3, st)
    calls = []
    real = subprocess.run

    def counting(cmd, *a, **k):
        if cmd and cmd[0] == "git" and threading.current_thread() is threading.main_thread():
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    assert roadmap.conflicts_payload(items3, st) == first
    # Only the cached ref scan's signature call; no diff, no merge-tree.
    assert len(calls) == 1 and "for-each-ref" in calls[0]
    calls.clear()
    assert roadmap.conflicts_payload(items3, st, trunk_sha=None) == first
    assert len(calls) == 1


def test_status_conflicts_outside_git(roadmap, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    roadmap.main(["init", "--name", "Demo"])
    capsys.readouterr()
    assert roadmap.main(["status", "--conflicts"]) == 0
    assert "0 open item branches" in capsys.readouterr().out


def test_items_sharing_a_branch_are_one_node(cf, repo, abc):
    cands = _cands(abc, "A", "B", "C")
    cands.append({"id": 9, "displayId": "F9", "title": "also on A", "branch": "A",
                  "sha": abc["A"], "landedIn": None})
    rep = cf.overlaps(repo, abc["main"], cands)
    assert rep["checked"] == 3 and len(rep["pairs"]) == 1
    a = next(w for w in (rep["pairs"][0]["a"], rep["pairs"][0]["b"]) if w["branch"] == "A")
    assert a["id"] == 1 and a["items"] == [1, 9]
    assert "F1 +1 (A)" in cf.format_conflicts(rep)


# --- dashboard panel and plan-page overlaps (step 3) ------------------------

def test_dashboard_payload_carries_conflicts(roadmap, dashboard, items3):
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), items3)
    payload = json.loads(bc.snapshot()[1])
    rep = payload["conflicts"]
    assert rep["counts"]["high"] == 1
    assert {rep["pairs"][0]["a"]["id"], rep["pairs"][0]["b"]["id"]} == {1, 2}
    assert rep["order"][0]["id"] == 3


def test_dashboard_unchanged_refs_tick_runs_no_extra_git(roadmap, dashboard,
                                                         items3, monkeypatch):
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), items3)
    calls = []
    real = subprocess.run
    me = threading.current_thread()

    def counting(cmd, *a, **k):
        if cmd and cmd[0] == "git" and threading.current_thread() is me:
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    bc._tick()
    # the refs signature only: no diff, no merge-tree, no status rebuild
    assert len(calls) == 1 and "for-each-ref" in calls[0]
    # A rebuild with unchanged tips reuses every cached diff and merge-tree.
    calls.clear()
    bc._dump()
    assert not [c for c in calls if "diff" in c or "merge-tree" in c]


def test_dashboard_without_conflicts_hook_omits_panel(roadmap, dashboard, items3):
    api = roadmap._dashboard_api()
    del api.conflicts_payload
    payload = json.loads(dashboard._Broadcaster(api, items3).snapshot()[1])
    assert "conflicts" not in payload


def test_dashboard_html_has_conflict_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ("conflictsPanel(d.conflicts)", "overlapsOf(d.id)",
                 'fact(facts, "overlaps"', "conflicts: P.conflicts", "r-high"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
