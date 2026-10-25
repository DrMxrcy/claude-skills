"""Plan 48: the per-user project registry behind `serve --all`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"
sys.path.insert(0, str(SCRIPT.parent))
import rmlib.registry as reg  # noqa: E402


def _cli(cwd, *args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


def _project(path: Path, name: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    res = _cli(path, "init", "--name", name)
    assert res.returncode == 0, res.stderr
    return path


def _reg_file(home: Path) -> dict:
    return json.loads((home / "projects.json").read_text())


def test_registry_honours_roadmap_home(_registry_home):
    assert reg.registry_path() == _registry_home / "projects.json"


@pytest.mark.parametrize("cmd", [["status"], ["orient"], ["status", "--json"]])
def test_commands_register_the_project(tmp_path, _registry_home, cmd):
    p = _project(tmp_path / "alpha", "Alpha")
    assert not (_registry_home / "projects.json").exists()   # init does not register
    assert _cli(p, *cmd).returncode == 0
    data = _reg_file(_registry_home)
    entry = data["projects"][str(p.resolve())]
    assert entry["name"] == "Alpha" and entry["lastSeen"].endswith("Z")


def test_check_registers_the_project(roadmap, repo, monkeypatch, _registry_home):
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "Demo"])
    roadmap.main(["new", "--type", "feature", "--title", "Thing"])
    assert roadmap.main(["check", "--plan", "1", "--step", "1"]) == 0
    assert str(repo.resolve()) in _reg_file(_registry_home)["projects"]


def test_outside_a_project_registers_nothing(tmp_path, _registry_home):
    (tmp_path / "plain").mkdir()
    assert _cli(tmp_path / "plain", "orient").returncode == 0
    assert not (_registry_home / "projects.json").exists()


def test_touch_is_throttled(tmp_path, _registry_home):
    p = _project(tmp_path / "alpha", "Alpha")
    assert reg.touch(p) is True
    assert reg.touch(p) is False          # refreshed under a minute ago
    data = _reg_file(_registry_home)
    data["projects"][str(p.resolve())]["lastSeen"] = "2000-01-01T00:00:00Z"
    (_registry_home / "projects.json").write_text(json.dumps(data))
    assert reg.touch(p) is True


def test_linked_worktree_registers_the_main_checkout(repo, _registry_home):
    git = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, check=True,
                                              capture_output=True)
    assert _cli(repo, "init", "--name", "Main").returncode == 0
    git("add", "-A")
    git("commit", "-qm", "init")
    wt = repo.parent / (repo.name + "-wt")
    git("worktree", "add", "-q", "-b", "side", str(wt))
    assert reg.main_checkout(wt.resolve()) == repo.resolve()
    assert _cli(wt, "status").returncode == 0
    assert list(_reg_file(_registry_home)["projects"]) == [str(repo.resolve())]


def test_broken_registry_is_ignored(tmp_path, _registry_home):
    p = _project(tmp_path / "alpha", "Alpha")
    (_registry_home / "projects.json").write_text("{not json")
    assert reg.load() == {} and reg.entries() == []
    res = _cli(p, "status")
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr
    # self-heals on the next touch
    assert str(p.resolve()) in _reg_file(_registry_home)["projects"]
    (_registry_home / "projects.json").write_text('{"projects": [1, 2]}')
    assert reg.load() == {}
    (_registry_home / "projects.json").write_text(
        '{"projects": {"/x": "bad", "/y": {"name": "Y"}}}')
    assert list(reg.load()) == ["/y"]


def test_unwritable_registry_never_fails_a_command(tmp_path, monkeypatch):
    p = _project(tmp_path / "alpha", "Alpha")
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so the registry dir cannot be created")
    env = {**os.environ, "ROADMAP_HOME": str(blocker / "home")}
    for cmd in (["status"], ["orient"], ["status", "--json"]):
        res = _cli(p, *cmd, env=env)
        assert res.returncode == 0, res.stderr
        assert "Traceback" not in res.stderr
    assert reg.touch(p) is True    # the default (fixture) home still works
    monkeypatch.setenv("ROADMAP_HOME", str(blocker / "home"))
    assert reg.touch(p) is False


def test_projects_lists_and_forgets(tmp_path, _registry_home):
    a = _project(tmp_path / "alpha", "Alpha")
    b = _project(tmp_path / "beta", "Beta Two")
    for p in (a, b):
        assert _cli(p, "status").returncode == 0
    res = _cli(tmp_path, "projects")
    assert res.returncode == 0, res.stderr
    assert "alpha" in res.stdout and "beta-two" in res.stdout
    rows = json.loads(_cli(tmp_path, "projects", "--json").stdout)["projects"]
    assert [(r["slug"], r["exists"]) for r in rows] == [("alpha", True),
                                                        ("beta-two", True)]
    # a deleted project path is flagged, then forgotten
    import shutil
    shutil.rmtree(b)
    res = _cli(tmp_path, "projects")
    assert "missing" in res.stdout and "--forget beta-two" in res.stdout
    res = _cli(tmp_path, "projects", "--forget", "beta-two")
    assert res.returncode == 0 and "forgot" in res.stdout
    assert [r["slug"] for r in reg.entries()] == ["alpha"]
    res = _cli(tmp_path, "projects", "--forget", "nope")
    assert res.returncode == 1 and "no registered project" in res.stderr


def test_clashing_names_get_unique_slugs(tmp_path, _registry_home):
    a = _project(tmp_path / "one" / "app", "App")
    b = _project(tmp_path / "two" / "app", "App")
    reg.touch(a), reg.touch(b)
    slugs = [r["slug"] for r in reg.entries()]
    assert len(set(slugs)) == 2 and all(s.startswith("app-") for s in slugs)


def test_registry_dir_never_becomes_a_project(tmp_path, monkeypatch, roadmap):
    """~/.roadmap is the registry home, not a project rooted at $HOME."""
    home = tmp_path / "home"
    monkeypatch.setenv("ROADMAP_HOME", str(home / ".roadmap"))
    sub = home / "work" / "plain"
    sub.mkdir(parents=True)
    p = _project(home / "proj", "Proj")
    reg.touch(p)
    assert (home / ".roadmap" / "projects.json").exists()
    assert roadmap.find_root(sub) != home
    (p / "src").mkdir()
    assert roadmap.find_root(p / "src") == p
