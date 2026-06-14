def test_slugify(roadmap):
    assert roadmap.slugify("Auth Setup!") == "auth-setup"
    assert roadmap.slugify("Fix   login   bug") == "fix-login-bug"
    assert roadmap.slugify("API v2 / OAuth") == "api-v2-oauth"


def test_atomic_write_and_config_roundtrip(roadmap, repo):
    (repo / ".roadmap").mkdir()
    cfg = {"project": "X", "currentVersion": "0.0.1", "nextId": 1,
           "items": [], "settings": {"autoCommit": True, "gitTagOnRelease": False}}
    roadmap.write_config(repo, cfg)
    assert (repo / ".roadmap/config.json").exists()
    assert roadmap.read_config(repo) == cfg


def test_find_root_walks_up(roadmap, repo):
    (repo / ".roadmap").mkdir()
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert roadmap.find_root(nested) == repo


def test_init_project_greenfield(roadmap, repo):
    cfg = roadmap.init_project(repo, "My Project")
    assert cfg["project"] == "My Project"
    assert cfg["currentVersion"] == "0.0.1"
    assert cfg["nextId"] == 1
    assert (repo / "ROADMAP.md").exists()
    assert (repo / ".roadmap/plans").is_dir()
    rm = (repo / "ROADMAP.md").read_text()
    assert "My Project" in rm
    assert roadmap.AUTO_START in rm and roadmap.AUTO_END in rm


def test_init_cli_writes_config(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert roadmap.main(["init", "--name", "Demo"]) == 0
    assert roadmap.read_config(repo)["project"] == "Demo"
