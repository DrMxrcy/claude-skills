"""Scope drift per branch (plan 42): declared-path extraction and matching
(rmlib/parse.py), the off-plan report (`status --drift`, payload) and the
dashboard hooks."""
import pytest

from rmlib import parse as P


# --- declared paths from plan bodies (step 1) -------------------------------

BLUEPRINT = """
## 🏗️ Architectural Blueprint
- **Files to create:** `src/new.py` (the new module, see `docs/x.md` for why).
- **Files to modify:** `src/a.py` (`claim` subparser; `status --open`), `lib/` +
  `web/app/(auth)/page.tsx`, `pkg/{one,two}.ts`, `assets/*.svg`
- **Schema/interface changes:** `api/schema.json` is not a file to touch
- **Downstream impact:** none

## 🚶 Step-by-Step Checklist
- [ ] Step 1: parser -> target: rmlib/parse.py, tests
- [ ] Step 2: docs and smoke run -> target: plan evidence
- [ ] Step 3: command target -> target: `npm run test -- foo`, `README.md`
- [ ] Step 4: arrow form → target: scripts/run.sh
"""


def test_declared_paths_blueprint_and_targets():
    got = P.declared_paths(BLUEPRINT)
    assert got == ["src/new.py", "src/a.py", "lib/", "web/app/(auth)/page.tsx",
                   "pkg/one.ts", "pkg/two.ts", "assets/*.svg", "rmlib/parse.py",
                   "README.md", "scripts/run.sh"]
    # parenthesized commentary, flags, commands, prose words and other
    # fields never count
    for not_a_path in ("docs/x.md", "claim", "status --open", "api/schema.json",
                       "tests", "plan", "evidence", "npm run test -- foo"):
        assert not_a_path not in got


def test_declared_paths_unbackticked_prose_and_nested_bullets():
    body = """
- **Files to modify:** rmlib/report.py (orient payload + human line), SKILL.md
  settings table, references/quality-build.md, Dockerfile, .env.example, docs, e.g.
- **Files to create:**
  - `hooks/sync.sh`: support the `workspacePaths` stdin and `{}` stdout
  - `install.sh`: add `--agy` / `--antigravity`; see https://example.com/x.md
- **Files to create:** none
```
- **Files to modify:** `fenced/ignored.py`
```
<!-- - **Files to modify:** `commented/out.py` -->
"""
    assert P.declared_paths(body) == [
        "rmlib/report.py", "SKILL.md", "references/quality-build.md",
        "Dockerfile", ".env.example", "hooks/sync.sh", "install.sh"]


def test_template_plan_declares_nothing(roadmap, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "Blank"])
    plan = next((tmp_path / ".roadmap" / "plans").glob("001-*.md"))
    assert P.parse_plan(plan)["declaredPaths"] == []


@pytest.mark.parametrize("pattern,path,hit", [
    ("src/a.py", "src/a.py", True),
    ("src/a.py", "src/a.pyc", False),
    ("src/a.py", "src/ab.py", False),
    ("rmlib/parse.py", "skills/roadmap/scripts/rmlib/parse.py", True),  # suffix
    ("parse.py", "skills/x/parse.py", True),
    ("arse.py", "skills/x/parse.py", False),                # component boundary
    ("src/", "src/deep/b.py", True),
    ("src/", "src", False),
    ("src", "src/deep/b.py", True),                         # plain name: dir too
    ("lib/", "pkg/lib/x.py", True),
    ("src/*.py", "src/b.py", True),
    ("src/*.py", "src/deep/b.py", False),                   # * stays in a component
    ("src/**/*.py", "src/deep/er/b.py", True),
    ("src/**", "src/deep/b.py", True),
    ("**/*.md", "a/b/c.md", True),
    ("rmlib/dashboard.*", "rmlib/dashboard.html", True),
    ("./src/a.py", "src/a.py", True),
    ("/src/a.py", "src/a.py", True),
    ("web/app/(auth)/page.tsx", "web/app/(auth)/page.tsx", True),
    ("web/[slug]/x.ts", "web/[slug]/x.ts", True),           # brackets are literal
    ("web/[slug]/x.ts", "web/s/x.ts", False),
])
def test_path_matches(pattern, path, hit):
    assert P.path_matches(pattern, path) is hit


def test_off_plan_acceptance_example():
    changed = ["src/a.py", "src/b.py", "tests/test_a.py"]
    allow = P.scope_allow({})
    assert P.off_plan(changed, ["src/a.py"], allow) == ["src/b.py"]


def test_default_allow_list_never_flags_tests_lockfiles_roadmap():
    allow = P.scope_allow(None)
    safe = ["tests/test_x.py", "pkg/tests/y.py", "test/x.js", "src/__tests__/a.ts",
            "src/test_util.py", "pkg/x_test.go", "web/a.test.tsx", "web/a.spec.ts",
            "package-lock.json", "apps/web/pnpm-lock.yaml", "yarn.lock", "uv.lock",
            "Cargo.lock", "go.sum", "poetry.lock", "Gemfile.lock", "bun.lockb",
            ".roadmap/plans/001-x.md", ".roadmap/config.json", "ROADMAP.md",
            "CHANGELOG.md", "CHANGELOG.internal.md"]
    assert P.off_plan(safe, [], allow) == []
    assert P.off_plan(["src/a.py", "contest.py"], [], allow) == ["src/a.py",
                                                                 "contest.py"]


def test_scope_allow_setting_adds_and_removes():
    allow = P.scope_allow({"scopeAllow": ["docs/", "*.{svg,png}", "!tests/", 7]})
    assert "docs/" in allow and "*.svg" in allow and "*.png" in allow
    assert "tests/" not in allow and ".roadmap/" in allow
    assert P.off_plan(["docs/a.md", "img/x.png", "tests/t.py"], [], allow) \
        == ["tests/t.py"]
    assert P.scope_allow({"scopeAllow": "docs/"}) == list(P.DEFAULT_SCOPE_ALLOW)


def test_real_plan_shapes_parse(roadmap):
    """This repo's plans 30 and 31 (merged) parse to their declared files."""
    from pathlib import Path
    plans = Path(__file__).resolve().parent.parent / ".roadmap" / "plans"
    p30 = P.parse_plan(next(plans.glob("030-*.md")))["declaredPaths"]
    assert "rmlib/branches.py" in p30 and "dashboard.html" in p30
    assert "claim" not in p30 and "plan" not in p30
    p31 = P.parse_plan(next(plans.glob("031-*.md")))["declaredPaths"]
    assert "rmlib/dashboard.html" in p31
    assert not [p for p in p31 if "api" in p or "notes" in p]


# --- off-plan report: `status --drift`, payload (step 2) --------------------

import hashlib  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


def _commit(repo, msg, files):
    for name, text in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        _git(repo, "add", "-f", name)
    _git(repo, "commit", "-qm", msg)


def _declare(roadmap, repo, item_id, line):
    """Put a `Files to modify` line into item `item_id`'s plan (untracked)."""
    plan = next((repo / ".roadmap" / "plans").glob(f"{item_id:03d}-*.md"))
    text = plan.read_text()
    plan.write_text(text.replace("- **Files to modify:**", f"- **Files to modify:** {line}", 1))


def _set_settings(roadmap, repo, **kv):
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {}).update(kv)
    roadmap.write_config(repo, cfg)


def _repo_state(repo):
    idx = repo / ".git" / "index"
    # Branches and tags only: a user-level git hook may add refs/notes/* to a
    # fresh commit asynchronously, which is not the drift report writing.
    return (_git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                 "refs/heads", "refs/tags"),
            _git(repo, "rev-parse", "HEAD"),
            hashlib.sha1(idx.read_bytes()).hexdigest() if idx.exists() else None,
            _git(repo, "status", "--porcelain"))


@pytest.fixture
def caches():
    importlib.import_module("rmlib.branches")._CACHE.clear()
    cf = importlib.import_module("rmlib.conflicts")
    for c in (cf._FILES, cf._PAIRS, cf._FORKS):
        c.clear()
    return cf


@pytest.fixture
def drift3(roadmap, repo, caches, monkeypatch):
    """Item 1 declares `src/a.py` and changes src/a.py, tests/test_a.py,
    src/b.py, package-lock.json and a .roadmap note; item 2 declares `lib/` and
    `assets/*.svg`; item 3 declares nothing. Roadmap files stay untracked."""
    monkeypatch.chdir(repo)
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init", {"src/a.py": "a\n", "README.md": "r\n"})
    roadmap.main(["init", "--name", "Demo"])
    for t in ("Alpha", "Beta", "Gamma"):
        roadmap.main(["new", "--type", "feature", "--title", t])
    _declare(roadmap, repo, 1, "`src/a.py` (the parser)")
    _declare(roadmap, repo, 2, "`lib/`, `assets/*.svg`")
    work = {1: {"src/a.py": "a2\n", "tests/test_a.py": "t\n", "src/b.py": "b\n",
                "package-lock.json": "{}\n", ".roadmap/notes/n.md": "n\n"},
            2: {"lib/x/y.py": "y\n", "assets/i.svg": "<svg/>\n",
                "assets/sub/j.svg": "<svg/>\n"},
            3: {"src/c.py": "c\n"}}
    for n, files in work.items():
        _git(repo, "checkout", "-qb", f"roadmap/{n}", "main")
        _commit(repo, f"work (plan {n})", files)
        _git(repo, "checkout", "-q", "main")
    return repo


def test_drift_acceptance_only_undeclared_file_flagged(roadmap, drift3, capsys):
    before = _repo_state(drift3)
    rep = roadmap.status(drift3, drift=True)["scopeDrift"]
    one = next(e for e in rep["items"] if e["id"] == 1)
    assert one["offPlan"] == ["src/b.py"] and one["offPlanCount"] == 1
    assert one["changed"] == 5 and one["noScope"] is False
    assert one["base"]["kind"] == "trunk"
    assert rep["byItem"][1] == ["src/b.py"]
    assert _repo_state(drift3) == before


def test_drift_directory_and_glob_declarations(roadmap, drift3):
    rep = roadmap.status(drift3, drift=True)["scopeDrift"]
    two = next(e for e in rep["items"] if e["id"] == 2)
    assert two["declared"] == ["lib/", "assets/*.svg"]
    assert two["offPlan"] == ["assets/sub/j.svg"]


def test_drift_no_declared_scope(roadmap, drift3, capsys):
    st = roadmap.status(drift3, drift=True)
    rep = st["scopeDrift"]
    three = next(e for e in rep["items"] if e["id"] == 3)
    assert three["noScope"] is True and three["offPlan"] == []
    assert rep["noScope"] == [3] and rep["byItem"][3] is None
    row = next(i for i in st["items"] if i["id"] == 3)
    assert row["offPlan"] is None
    assert roadmap.main(["status", "--drift"]) == 0
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "Gamma" in l)
    assert "no declared scope" in line and "1 changed" in line


def test_status_drift_text_and_json(roadmap, drift3, capsys):
    assert roadmap.main(["status", "--drift"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith(
        "scope drift: 3 open item branches · 2 off-plan · 1 no declared scope")
    alpha = next(l for l in out.splitlines() if "Alpha" in l)
    assert "1 off-plan of 5 changed: src/b.py" in alpha and "roadmap/1" in alpha
    for safe in ("tests/test_a.py", "package-lock.json", ".roadmap/"):
        assert safe not in out
    assert roadmap.main(["status", "--drift", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)["scopeDrift"]
    assert [e["id"] for e in rep["items"]] == [1, 2, 3]   # off-plan, then no scope
    assert rep["flagged"] == 2 and rep["checked"] == 3
    assert rep["byItem"] == {"1": ["src/b.py"], "2": ["assets/sub/j.svg"], "3": None}


def test_plain_status_has_no_drift(roadmap, drift3):
    st = roadmap.status(drift3)
    assert "scopeDrift" not in st
    assert not [i for i in st["items"] if "offPlan" in i]


def test_drift_scope_allow_setting(roadmap, drift3):
    _set_settings(roadmap, drift3, scopeAllow=["src/b.py", "!tests/", "!test_*.py"])
    rep = roadmap.status(drift3, drift=True)["scopeDrift"]
    assert rep["byItem"][1] == ["tests/test_a.py"]


def test_drift_skips_done_and_merged(roadmap, drift3):
    _git(drift3, "merge", "-q", "--no-edit", "roadmap/3")
    rep = roadmap.status(drift3, drift=True)["scopeDrift"]
    assert {e["id"] for e in rep["items"]} == {1, 2}


def test_drift_unchanged_refs_reuse_cached_diffs(roadmap, drift3, monkeypatch):
    st = roadmap.status(drift3)
    first = roadmap.scope_drift_payload(drift3, st)
    calls = []
    real = subprocess.run

    def counting(cmd, *a, **k):
        if cmd and cmd[0] == "git" and threading.current_thread() is threading.main_thread():
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    assert roadmap.scope_drift_payload(drift3, st) == first
    assert calls and not [c for c in calls if "diff" in c]


def test_drift_outside_git(roadmap, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    roadmap.main(["init", "--name", "Demo"])
    capsys.readouterr()
    assert roadmap.main(["status", "--drift"]) == 0
    assert "0 open item branches" in capsys.readouterr().out


# --- branches cut from an integration branch -------------------------------

@pytest.fixture
def integ(roadmap, repo, caches, monkeypatch):
    """`integ` cut from main carries other.py (earlier work). roadmap/1 is cut
    from integ and changes c.py (open); roadmap/2 is cut from integ, changes
    d.py and is merged back (--no-ff: landed). Both plans declare only their
    own file, so integ's other.py must not count against them."""
    monkeypatch.chdir(repo)
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init", {"README.md": "r\n"})
    roadmap.main(["init", "--name", "Demo"])
    for t in ("Open", "Landed"):
        roadmap.main(["new", "--type", "feature", "--title", t])
    _declare(roadmap, repo, 1, "`c.py`")
    _declare(roadmap, repo, 2, "`d.py`")
    _set_settings(roadmap, repo, integrationBranch="integ")
    _git(repo, "checkout", "-qb", "integ", "main")
    _commit(repo, "earlier integration work", {"other.py": "o\n"})
    for n, f in ((1, "c.py"), (2, "d.py")):
        _git(repo, "checkout", "-qb", f"roadmap/{n}", "integ")
        _commit(repo, f"work (plan {n})", {f: f"{n}\n"})
        _git(repo, "checkout", "-q", "integ")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "roadmap/2")
    _commit(repo, "later integration work", {"later.py": "l\n"})
    _git(repo, "checkout", "-q", "main")
    return repo


def test_branch_cut_from_integration_counts_only_its_own_work(roadmap, integ, caches):
    files, wb = caches.own_changed_files(integ, "roadmap/1", None, "integ")
    assert files == ["c.py"] and wb["kind"] == "integration" and wb["ref"] == "integ"
    # vs trunk it would also carry other.py
    assert caches.changed_files(integ, "roadmap/1", None, "integ") == ["c.py", "other.py"]
    rep = roadmap.status(integ, drift=True)["scopeDrift"]
    assert rep["byItem"][1] == []


def test_landed_branch_diffs_from_its_fork(roadmap, integ, caches):
    st = roadmap.status(integ)
    assert next(i for i in st["items"] if i["id"] == 2)["lane"] == "landed"
    files, wb = caches.own_changed_files(integ, "roadmap/2", None, "integ")
    assert files == ["d.py"] and wb["kind"] == "fork" and wb["ref"] == "integ"
    rep = roadmap.status(integ, drift=True)["scopeDrift"]
    assert rep["byItem"][2] == []
    two = next(e for e in rep["items"] if e["id"] == 2)
    assert two["base"]["kind"] == "fork" and two["changed"] == 1


def test_branch_cut_from_trunk_keeps_trunk_base(roadmap, integ, caches):
    _git(integ, "checkout", "-qb", "roadmap/3", "main")
    _commit(integ, "work (plan 3)", {"e.py": "e\n"})
    _git(integ, "checkout", "-q", "main")
    files, wb = caches.own_changed_files(integ, "roadmap/3", None, "integ")
    assert files == ["e.py"] and wb["kind"] == "trunk"


def test_items_sharing_a_branch_judged_against_all_their_plans(roadmap, drift3):
    """A claim naming another item's branch puts both items on one entry."""
    roadmap.main(["claim", "3", "--stage", "review", "--branch", "roadmap/1"])
    rep = roadmap.status(drift3, drift=True)["scopeDrift"]
    one = next(e for e in rep["items"] if e["branch"] == "roadmap/1")
    assert one["items"] == [1, 3] and one["offPlan"] == ["src/b.py"]
    assert rep["byItem"][3] == ["src/b.py"]


# --- dashboard chip and plan-page list (step 3) ------------------------------

def test_dashboard_payload_carries_scope_drift(roadmap, dashboard, drift3):
    before = _repo_state(drift3)
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), drift3)
    rep = json.loads(bc.snapshot()[1])["scopeDrift"]
    assert rep["byItem"] == {"1": ["src/b.py"], "2": ["assets/sub/j.svg"], "3": None}
    assert rep["flagged"] == 2
    assert _repo_state(drift3) == before


def test_dashboard_rebuild_unchanged_refs_runs_no_diff(roadmap, dashboard, drift3,
                                                       monkeypatch):
    bc = dashboard._Broadcaster(roadmap._dashboard_api(), drift3)
    calls = []
    real = subprocess.run
    me = threading.current_thread()

    def counting(cmd, *a, **k):
        if cmd and cmd[0] == "git" and threading.current_thread() is me:
            calls.append(cmd)
        return real(cmd, *a, **k)

    monkeypatch.setattr(subprocess, "run", counting)
    bc._dump()
    assert not [c for c in calls if "diff" in c]


def test_dashboard_without_drift_hook_omits_it(roadmap, dashboard, drift3):
    api = roadmap._dashboard_api()
    del api.scope_drift_payload
    payload = json.loads(dashboard._Broadcaster(api, drift3).snapshot()[1])
    assert "scopeDrift" not in payload


def test_dashboard_safe_drift_survives_a_failing_hook(dashboard, tmp_path):
    import types

    def boom(root, st):
        raise RuntimeError("git trouble")
    rm = types.SimpleNamespace(scope_drift_payload=boom)
    assert dashboard._safe_drift(rm, tmp_path, {}) is None


def test_dashboard_html_has_drift_hooks(dashboard):
    body = dashboard._dashboard_html()
    for hook in ("scopeDrift: P.scopeDrift", "function offPlanOf(",
                 "offPlanChip(it.id)", "offPlanChip(d.id)", "offPlanOf(d.id)",
                 '" off-plan"', "no declared scope", "offplan-list"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body
