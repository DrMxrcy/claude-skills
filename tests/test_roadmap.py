import json
import subprocess

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


def test_derive_status(roadmap):
    assert roadmap.derive_status(0, 2) == "planned"
    assert roadmap.derive_status(1, 2) == "active"
    assert roadmap.derive_status(2, 2) == "done"
    assert roadmap.derive_status(0, 0) == "planned"


def test_sync_renders_region_and_preserves_incubator(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Auth Setup")
    roadmap.check_step(repo, 1, 1)
    rm = (repo / "ROADMAP.md").read_text()
    managed = rm.split(roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "Auth Setup" in managed
    assert "50%" in managed
    assert "feature" in managed
    assert "Idea Incubator" in rm  # free-form preserved


def test_sync_updates_plan_status_frontmatter(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "status: done" in (repo / ".roadmap/plans/001-a.md").read_text()


def test_sync_is_idempotent(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    first = (repo / "ROADMAP.md").read_text()
    roadmap.sync(repo)
    roadmap.sync(repo)
    assert (repo / "ROADMAP.md").read_text() == first


def test_sync_raises_on_malformed_markers(roadmap, repo):
    roadmap.init_project(repo, "P")
    (repo / "ROADMAP.md").write_text("# no markers here\n")
    with pytest.raises(ValueError):
        roadmap.sync(repo)


def test_render_region_orders_versions_semantically(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "ten", version="0.0.10")
    roadmap.new_item(repo, "feature", "two", version="0.0.2")
    rm = (repo / "ROADMAP.md").read_text()
    assert rm.index("v0.0.2") < rm.index("v0.0.10")


def test_version_marker_not_done_when_item_incomplete(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")  # 0/2 steps done
    rm = (repo / "ROADMAP.md").read_text()
    managed = rm.split(roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "### [ ] v0.0.1" in managed


def test_release_bumps_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.release(repo, "0.0.2")
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"
    assert "v0.0.2" in (repo / "ROADMAP.md").read_text()


def test_status_returns_structure(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    st = roadmap.status(repo)
    assert st["currentVersion"] == "0.0.1"
    assert st["items"][0]["pct"] == 50
    assert st["items"][0]["type"] == "feature"
    assert st["project"] == "P"
    assert st["items"][0]["done"] == 1
    assert st["items"][0]["total"] == 2


def test_release_with_tag_creates_git_tag(roadmap, repo):
    roadmap.init_project(repo, "P")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    roadmap.release(repo, "0.0.2", tag=True)
    out = subprocess.run(["git", "tag", "-l"], cwd=repo, capture_output=True, text=True)
    assert "v0.0.2" in out.stdout


def test_status_handles_missing_plan_file(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    (repo / ".roadmap/plans/001-a.md").unlink()
    st = roadmap.status(repo)
    assert st["items"][0]["done"] == 0
    assert st["items"][0]["total"] == 0


def test_detect_version_from_package_json(roadmap, repo):
    (repo / "package.json").write_text(json.dumps({"version": "2.3.4"}))
    assert roadmap.detect_version(repo) == "2.3.4"


def test_detect_version_from_pyproject(roadmap, repo):
    (repo / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n')
    assert roadmap.detect_version(repo) == "9.9.9"


def test_detect_version_fallback(roadmap, repo):
    assert roadmap.detect_version(repo) == "0.0.1"


def test_adopt_seeds_version_and_preserves_existing_roadmap(roadmap, repo):
    (repo / "package.json").write_text(json.dumps({"version": "1.5.0"}))
    (repo / "ROADMAP.md").write_text("# Existing\n\n- my old note\n")
    cfg = roadmap.init_project(repo, "Legacy", adopt=True)
    assert cfg["currentVersion"] == "1.5.0"
    rm = (repo / "ROADMAP.md").read_text()
    assert "my old note" in rm          # preserved
    assert roadmap.AUTO_START in rm      # managed region appended


def test_init_is_idempotent_preserves_items(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    cfg = roadmap.init_project(repo, "P")   # re-init must not wipe state
    assert cfg["nextId"] == 2
    assert len(cfg["items"]) == 1


def test_detect_version_pyproject_prefers_project_over_tool(roadmap, repo):
    (repo / "pyproject.toml").write_text(
        '[tool.poetry]\nversion = "0.1.0"\n\n[project]\nversion = "9.9.9"\n')
    assert roadmap.detect_version(repo) == "9.9.9"


def test_detect_version_pyproject_poetry_only(roadmap, repo):
    (repo / "pyproject.toml").write_text('[tool.poetry]\nversion = "3.2.1"\n')
    assert roadmap.detect_version(repo) == "3.2.1"


def test_import_creates_plan_with_extracted_steps(roadmap, repo):
    roadmap.init_project(repo, "P")
    src = repo / "TODO.md"
    src.write_text("# Todo\n- [ ] build login\n- [x] set up db\n- not a step\n")
    created = roadmap.import_file(repo, src)
    assert len(created) == 1
    body = created[0].read_text()
    assert "build login" in body and "set up db" in body
    assert "not a step" not in body
    # imported checked state is preserved
    assert roadmap.count_progress(created[0]) == (1, 2)


def test_import_preserves_backslash_content(roadmap, repo):
    roadmap.init_project(repo, "P")
    src = repo / "TODO.md"
    src.write_text("- [ ] use \\1 and \\g<0> literally\n")
    created = roadmap.import_file(repo, src)
    body = created[0].read_text()
    assert "use \\1 and \\g<0> literally" in body
    assert roadmap.count_progress(created[0]) == (0, 1)


def test_import_ignores_fenced_source_checkboxes(roadmap, repo):
    roadmap.init_project(repo, "P")
    src = repo / "TODO.md"
    src.write_text("- [ ] real task\n```\n- [ ] fenced example\n```\n")
    created = roadmap.import_file(repo, src)
    body = created[0].read_text()
    assert "real task" in body
    assert "fenced example" not in body
    assert roadmap.count_progress(created[0]) == (0, 1)


def test_cli_new_bad_type_returns_1(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.main(["init", "--name", "P"])
    rc = roadmap.main(["new", "--type", "epic", "--title", "x"])
    assert rc == 1
    assert "Error" in capsys.readouterr().err


def test_cli_command_before_init_returns_1(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    rc = roadmap.main(["new", "--type", "feature", "--title", "x"])
    assert rc == 1


def test_cli_happy_path_returns_0(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert roadmap.main(["init", "--name", "P"]) == 0
    assert roadmap.main(["new", "--type", "feature", "--title", "A"]) == 0


def test_init_creates_claude_md_rules(roadmap, repo):
    roadmap.init_project(repo, "P")
    cm = (repo / "CLAUDE.md").read_text()
    assert "roadmap:rules:start" in cm
    assert "Work one checklist item at a time" in cm


def test_init_claude_md_idempotent_and_preserves_content(roadmap, repo):
    (repo / "CLAUDE.md").write_text("# Existing\n\n- keep this\n")
    roadmap.init_project(repo, "P")
    roadmap.init_project(repo, "P")          # re-init must not duplicate
    cm = (repo / "CLAUDE.md").read_text()
    assert "keep this" in cm
    assert cm.count("roadmap:rules:start") == 1


def test_init_no_claude_md_opt_out(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    assert not (repo / "CLAUDE.md").exists()


def test_release_blocked_when_items_incomplete(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")          # 0/2 done in v0.0.1
    with pytest.raises(ValueError):
        roadmap.release(repo, "0.0.2")
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.1"   # not bumped


def test_release_force_bypasses_incomplete(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.release(repo, "0.0.2", force=True)
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"


def test_release_writes_changelog(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login")
    roadmap.check_step(repo, 1, None, all_done=True)           # sync writes changelog
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Login" in cl
    assert "(feature)" not in cl                 # user-facing — no type jargon


def test_changelog_uses_note_and_groups_by_type(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Auth backend", note="Sign in with email")
    roadmap.new_item(repo, "bug", "Null deref on logout")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    cl = (repo / "CHANGELOG.md").read_text()
    assert "Sign in with email" in cl and "Auth backend" not in cl   # note used, not title
    assert "🐛 Fixed" in cl and "Null deref on logout" in cl
    assert cl.index("✨ New") < cl.index("🐛 Fixed")                 # New before Fixed


def test_changelog_written_on_completion_via_sync(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    roadmap.check_step(repo, 1, None, all_done=True)           # triggers sync
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Sign in with email" in cl
    assert "(pending)" not in cl                               # version fully done


def test_changelog_in_progress_shows_pending(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Big feature")          # 0/2 done
    cl = (repo / "CHANGELOG.md").read_text()
    assert "(in progress)" in cl and "- (pending) Big feature" in cl


def test_changelog_date_is_stable_across_resync(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    first = (repo / "CHANGELOG.md").read_text()
    date = roadmap.read_config(repo)["versionDates"]["0.0.1"]
    roadmap.sync(repo)
    roadmap.sync(repo)
    assert (repo / "CHANGELOG.md").read_text() == first        # no churn
    assert roadmap.read_config(repo)["versionDates"]["0.0.1"] == date


def test_new_with_note_and_set_note(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "X", note="hello")
    assert roadmap.read_config(repo)["items"][0]["note"] == "hello"
    roadmap.set_note(repo, 1, "updated")
    assert roadmap.read_config(repo)["items"][0]["note"] == "updated"


def test_norm_version_strips_leading_v(roadmap):
    assert roadmap._norm_version("v1.0.0") == "1.0.0"
    assert roadmap._norm_version("V2.3.4") == "2.3.4"
    assert roadmap._norm_version(" 1.0.0 ") == "1.0.0"
    assert roadmap._norm_version("1.0.0") == "1.0.0"


def test_new_item_normalizes_v_prefixed_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "First", version="1.0.0")
    roadmap.new_item(repo, "feature", "Eighth", version="v1.0.0")
    versions = [i["version"] for i in roadmap.read_config(repo)["items"]]
    assert versions == ["1.0.0", "1.0.0"]
    roadmap_md = (repo / "ROADMAP.md").read_text()
    assert "vv1.0.0" not in roadmap_md
    assert roadmap_md.count("### [ ] v1.0.0") == 1


def test_release_normalizes_v_prefixed_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.release(repo, "v0.0.2")
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"


def test_sync_heals_v_prefixed_versions(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "First", version="1.0.0")
    # Simulate a config corrupted before normalization existed.
    cfg = roadmap.read_config(repo)
    cfg["items"][0]["version"] = "v1.0.0"
    roadmap.write_config(repo, cfg)
    roadmap.sync(repo)
    assert roadmap.read_config(repo)["items"][0]["version"] == "1.0.0"
    assert "vv1.0.0" not in (repo / "ROADMAP.md").read_text()


def test_get_version(roadmap):
    from pathlib import Path
    vf = Path(roadmap.__file__).resolve().parent.parent / "VERSION"
    assert roadmap.get_version() == vf.read_text(encoding="utf-8").strip()


def test_version_command(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert roadmap.main(["version"]) == 0
    assert capsys.readouterr().out.strip() == roadmap.get_version()


def test_reorder_changes_render_sequence_within_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # id 1
    roadmap.new_item(repo, "feature", "B")   # id 2
    roadmap.new_item(repo, "feature", "C")   # id 3
    roadmap.reorder(repo, "0.0.1", [3, 1, 2])
    rm = (repo / "ROADMAP.md").read_text()
    assert rm.index("#3 C") < rm.index("#1 A") < rm.index("#2 B")


def test_reorder_rejects_id_from_other_version(roadmap, repo):
    import pytest
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B", version="1.0.0")
    with pytest.raises(ValueError):
        roadmap.reorder(repo, "0.0.1", [2])


def test_render_defaults_to_id_order_without_reorder(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    rm = (repo / "ROADMAP.md").read_text()
    assert rm.index("#1 A") < rm.index("#2 B")


def test_merge_combines_steps_and_drops_sources(roadmap, repo):
    roadmap.init_project(repo, "P")
    keep = roadmap.new_item(repo, "feature", "Auth")
    src = roadmap.new_item(repo, "feature", "Login")
    keep.write_text(keep.read_text() + "\n## Extra\n- [ ] keep step\n")
    src.write_text(src.read_text() + "\n## Extra\n- [x] source step\n")
    roadmap.merge_items(repo, keep_id=1, source_ids=[2])
    cfg = roadmap.read_config(repo)
    assert [i["id"] for i in cfg["items"]] == [1]   # source removed
    assert not src.exists()                         # source plan deleted
    merged = keep.read_text()
    assert "keep step" in merged and "source step" in merged


def test_merge_rewrites_dependencies_to_keeper(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # 1
    roadmap.new_item(repo, "feature", "B")   # 2
    roadmap.new_item(repo, "feature", "C")   # 3
    cfg = roadmap.read_config(repo)
    next(i for i in cfg["items"] if i["id"] == 3)["dependsOn"] = [2]
    roadmap.write_config(repo, cfg)
    roadmap.merge_items(repo, keep_id=1, source_ids=[2])
    c = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 3)
    assert c["dependsOn"] == [1]           # dep retargeted 2 -> 1


def test_merge_rejects_keeper_in_sources(roadmap, repo):
    import pytest
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.merge_items(repo, keep_id=1, source_ids=[1])


def test_depends_sets_field(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # 1
    roadmap.new_item(repo, "feature", "B")   # 2
    roadmap.set_depends(repo, 2, [1])
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert dep["dependsOn"] == [1]


def test_depends_dedups_and_preserves_order(roadmap, repo):
    roadmap.init_project(repo, "P")
    for t in ("A", "B", "C"):
        roadmap.new_item(repo, "feature", t)
    roadmap.set_depends(repo, 3, [2, 1, 2])
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 3)
    assert dep["dependsOn"] == [2, 1]


def test_depends_rejects_self_and_unknown(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 1, [1])        # self
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 1, [99])       # unknown target
    with pytest.raises(ValueError):
        roadmap.set_depends(repo, 99, [1])       # unknown plan


def test_depends_clear_removes_field(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    roadmap.set_depends(repo, 2, [], clear=True)
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert "dependsOn" not in dep


def test_cli_depends(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    assert roadmap.main(["depends", "--plan", "2", "--on", "1"]) == 0
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert dep["dependsOn"] == [1]


def test_remove_archives_and_drops(roadmap, repo):
    roadmap.init_project(repo, "P")
    p = roadmap.new_item(repo, "feature", "Stray thing")
    roadmap.remove_item(repo, 1)
    cfg = roadmap.read_config(repo)
    assert cfg["items"] == []                                  # dropped from registry
    assert not p.exists()                                      # original gone
    assert (repo / ".roadmap/archive/001-stray-thing.md").exists()  # archived
    rm = (repo / "ROADMAP.md").read_text()
    assert "(was #1) Stray thing" in rm                        # demoted to Incubator
    assert rm.index("Idea Incubator") < rm.index("(was #1)")   # under the heading


def test_remove_retargets_dependents(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")   # 1
    roadmap.new_item(repo, "feature", "B")   # 2
    roadmap.set_depends(repo, 2, [1])
    roadmap.remove_item(repo, 1)
    dep = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert "dependsOn" not in dep            # link to removed item cleared


def test_remove_missing_plan_file_still_drops(roadmap, repo):
    roadmap.init_project(repo, "P")
    p = roadmap.new_item(repo, "feature", "A")
    p.unlink()                               # plan file already gone
    roadmap.remove_item(repo, 1)
    assert roadmap.read_config(repo)["items"] == []


def test_remove_unknown_id_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.remove_item(repo, 99)


def test_cli_remove(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    assert roadmap.main(["remove", "--plan", "1"]) == 0
    assert roadmap.read_config(repo)["items"] == []


def test_changelog_command_prints(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.main(["changelog"]) == 0
    assert "Sign in" in capsys.readouterr().out


def test_backfill_dates_from_git_tag(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    # remove the auto-stamped date so backfill has work to do
    cfg = roadmap.read_config(repo)
    cfg["versionDates"] = {}
    roadmap.write_config(repo, cfg)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v0.0.1"], cwd=repo, check=True)
    roadmap.backfill_changelog(repo)
    date = roadmap.read_config(repo)["versionDates"].get("0.0.1")
    assert date and date.count("-") == 2          # ISO YYYY-MM-DD from tag commit


def test_backfill_no_tag_leaves_undated(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")        # incomplete, no tag
    cfg = roadmap.read_config(repo)
    cfg["versionDates"] = {}
    roadmap.write_config(repo, cfg)
    roadmap.backfill_changelog(repo)
    assert roadmap.read_config(repo)["versionDates"] == {}   # nothing to backfill


def test_retarget_from_versions_moves_items(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.0.0")   # 1
    roadmap.new_item(repo, "feature", "B", version="1.3.0")   # 2
    roadmap.new_item(repo, "feature", "C", version="1.6.0")   # 3
    roadmap.retarget(repo, "1.0.0", from_versions=["1.3.0", "1.6.0"])
    versions = {i["id"]: i["version"] for i in roadmap.read_config(repo)["items"]}
    assert versions == {1: "1.0.0", 2: "1.0.0", 3: "1.0.0"}


def test_retarget_rewrites_plan_frontmatter(roadmap, repo):
    roadmap.init_project(repo, "P")
    p = roadmap.new_item(repo, "feature", "A", version="1.3.0")
    roadmap.retarget(repo, "2.0.0", from_versions=["1.3.0"])
    assert "version: 2.0.0" in p.read_text()


def test_retarget_by_plan_ids(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.0.0")   # 1
    roadmap.new_item(repo, "feature", "B", version="1.0.0")   # 2
    roadmap.retarget(repo, "1.5.0", plan_ids=[2])
    versions = {i["id"]: i["version"] for i in roadmap.read_config(repo)["items"]}
    assert versions == {1: "1.0.0", 2: "1.5.0"}


def test_retarget_normalizes_target(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.0.0")
    roadmap.retarget(repo, "v2.0.0", plan_ids=[1])
    assert roadmap.read_config(repo)["items"][0]["version"] == "2.0.0"


def test_retarget_requires_exactly_one_selector(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.retarget(repo, "1.0.0")                                  # neither
    with pytest.raises(ValueError):
        roadmap.retarget(repo, "1.0.0", from_versions=["0.0.1"], plan_ids=[1])  # both


def test_retarget_unknown_plan_id_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.retarget(repo, "1.0.0", plan_ids=[99])


def test_retarget_empty_selection_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.0.0")
    with pytest.raises(ValueError):
        roadmap.retarget(repo, "2.0.0", from_versions=["9.9.9"])         # no such version


def test_retarget_prunes_emptied_version_dates(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.3.0")
    roadmap.check_step(repo, 1, None, all_done=True)                     # stamps versionDates[1.3.0]
    assert "1.3.0" in roadmap.read_config(repo)["versionDates"]
    roadmap.retarget(repo, "1.0.0", from_versions=["1.3.0"])
    vd = roadmap.read_config(repo)["versionDates"]
    assert "1.3.0" not in vd                                             # emptied version pruned
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v1.0.0" in cl and "## v1.3.0" not in cl                   # re-rendered under target


def test_cli_retarget(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.6.0")
    assert roadmap.main(["retarget", "--to", "1.0.0", "--from", "1.6.0"]) == 0
    assert roadmap.read_config(repo)["items"][0]["version"] == "1.0.0"
