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
    me = threading.current_thread()

    def counting(cmd, *a, **k):
        if cmd and cmd[0] == "git" and threading.current_thread() is me:
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
