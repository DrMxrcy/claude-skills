import pytest


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


def test_new_item_allocates_and_registers(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, "feature", "Auth Setup")
    assert path == repo / ".roadmap/plans/001-auth-setup.md"
    assert path.exists()
    body = path.read_text()
    assert "id: 1" in body and "type: feature" in body and "Auth Setup" in body
    cfg = roadmap.read_config(repo)
    assert cfg["nextId"] == 2
    assert cfg["items"][0] == {"id": 1, "slug": "auth-setup", "title": "Auth Setup",
                               "type": "feature", "version": "0.0.1",
                               "file": "plans/001-auth-setup.md"}


def test_new_item_bug_uses_bug_template(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, "bug", "Fix login")
    assert "Symptom & Reproduction" in path.read_text()


def test_new_item_rejects_bad_type(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.new_item(repo, "epic", "x")


def test_new_item_rejects_empty_slug_title(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.new_item(repo, "feature", "!!!")


def test_parse_plan_and_progress(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, "feature", "A")
    parsed = roadmap.parse_plan(path)
    assert parsed["meta"]["id"] == "1"
    assert len(parsed["steps"]) == 2
    assert roadmap.count_progress(path) == (0, 2)


def test_check_flips_one_box(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    path = repo / ".roadmap/plans/001-a.md"
    assert roadmap.count_progress(path) == (1, 2)
    roadmap.check_step(repo, 1, 1, undo=True)
    assert roadmap.count_progress(path) == (0, 2)


def test_check_all_done(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (2, 2)


def test_check_bad_id_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.check_step(repo, 99, 1)


def test_parse_plan_ignores_fenced_checkboxes(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, "feature", "A")
    path.write_text(path.read_text() + "\n```\n- [ ] not a real step\n```\n")
    assert roadmap.count_progress(path) == (0, 2)


def test_check_does_not_touch_fenced_box(roadmap, repo):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, "feature", "A")
    path.write_text(path.read_text() + "\n```\n- [ ] fenced\n```\n")
    roadmap.check_step(repo, 1, None, all_done=True)
    body = path.read_text()
    assert "- [ ] fenced" in body
    assert roadmap.count_progress(path) == (2, 2)


def test_check_step_zero_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.check_step(repo, 1, 0)


def test_check_flips_only_target_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    steps = roadmap.parse_plan(repo / ".roadmap/plans/001-a.md")["steps"]
    assert steps[0][0] is True and steps[1][0] is False
