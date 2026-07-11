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
    assert "One item at a time" in cm
    assert "Quality-first build" in cm
    assert "high-quality" in cm
    assert "handoff` is optional" in cm or "handoff is optional" in cm
    assert "Micro-commit" in cm
    assert "Abrupt switch" in cm
    assert "rate-limit" in cm or "Rate limits" in cm
    assert "hyphen only" in cm
    assert "next` has no `--auto`" in cm or "next has no" in cm


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
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    roadmap.check_step(repo, 1, None, all_done=True)           # sync writes changelog
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Sign in with email" in cl
    assert "(feature)" not in cl                 # user-facing — no type jargon


def test_changelog_uses_note_and_groups_by_type(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Auth backend", note="Sign in with email")
    roadmap.new_item(repo, "bug", "Null deref on logout", note="No more logout crash")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    cl = (repo / "CHANGELOG.md").read_text()
    assert "Sign in with email" in cl and "Auth backend" not in cl   # note used, not title
    assert "🐛 Fixed" in cl and "No more logout crash" in cl
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
    roadmap.new_item(repo, "feature", "Big feature", note="A big new feature")  # 0/2 done
    cl = (repo / "CHANGELOG.md").read_text()
    assert "(in progress)" in cl and "- (pending) A big new feature" in cl


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
    assert "([archived plan](.roadmap/archive/001-stray-thing.md))" in rm  # links the archive


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
    rm = (repo / "ROADMAP.md").read_text()
    assert "(was #1) A" in rm and "archived plan" not in rm   # breadcrumb, but no dead link


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
    roadmap.new_item(repo, "feature", "A", version="1.3.0", note="Feature A")
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


def test_upgrade_refreshes_rules_and_reports_version(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    claude = repo / "CLAUDE.md"
    claude.write_text(f"# P\n\n{roadmap.RULES_START}\nOLD RULES\n{roadmap.RULES_END}\n")
    roadmap.upgrade(repo)
    text = claude.read_text()
    assert "OLD RULES" not in text
    assert "## Roadmap tracking" in text
    assert roadmap.read_config(repo)["skillVersion"] == roadmap.get_version()
    assert roadmap.get_version() in capsys.readouterr().out


def test_upgrade_command_runs(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    assert roadmap.main(["upgrade"]) == 0
    assert roadmap.read_config(repo)["skillVersion"] == roadmap.get_version()


# --- audience-aware public/internal changelog ---------------------------------

def test_audience_defaults_by_type(roadmap):
    assert roadmap.item_audience({"type": "feature"}) == "public"
    assert roadmap.item_audience({"type": "bug"}) == "public"
    assert roadmap.item_audience({"type": "refactor"}) == "internal"
    assert roadmap.item_audience({"type": "chore"}) == "internal"
    assert roadmap.item_audience({"type": "feature", "audience": "internal"}) == "internal"


def test_internal_item_excluded_from_public_but_in_internal(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")     # public
    roadmap.new_item(repo, "refactor", "Rework cache", note="Cache rewrite")  # internal by default
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    public = (repo / "CHANGELOG.md").read_text()
    internal = (repo / "CHANGELOG.internal.md").read_text()
    assert "Sign in with email" in public and "Cache rewrite" not in public
    # Versions with real public bullets stay clean — no roll-up line (less is more);
    # the internal work is still fully logged in CHANGELOG.internal.md.
    assert roadmap.ROLLUP_LINE not in public
    assert "Cache rewrite" in internal and "Sign in with email" in internal


def test_public_item_without_note_omitted_with_warning(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Secret sauce")          # public, no note
    roadmap.check_step(repo, 1, None, all_done=True)
    _text, warnings = roadmap.render_public_changelog(repo)
    assert "Secret sauce" not in _text
    assert any("no note" in w for w in warnings)


def test_set_audience_moves_item_between_changelogs(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Internal tool", note="Did a thing")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "Did a thing" in (repo / "CHANGELOG.md").read_text()   # public by default
    roadmap.set_audience(repo, 1, "internal")
    assert "Did a thing" not in (repo / "CHANGELOG.md").read_text()
    assert "Did a thing" in (repo / "CHANGELOG.internal.md").read_text()


def test_set_audience_rejects_bad_value(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    with pytest.raises(ValueError):
        roadmap.set_audience(repo, 1, "everyone")


def test_lint_note_flags_internal_tells(roadmap):
    assert roadmap.lint_note("Plain user benefit") == []
    tells = roadmap.lint_note("Fixed the Convex mutation in src/api/db.ts (#77)")
    low = [t.lower() for t in tells]
    assert "convex" in low and "#77" in tells and any(".ts" in t for t in tells)


def test_lint_note_flags_soft_dev_phrasing(roadmap):
    # process/architecture phrasing a vendor/path scan misses
    tells = [t.lower() for t in
             roadmap.lint_note("Pre-launch hardening pass that lays the groundwork")]
    assert "hardening" in tells and "groundwork" in tells and "pre-launch" in tells
    assert roadmap.lint_note("Crowd levels are more accurate now") == []   # clean benefit


def test_lint_note_flags_scope_and_compliance_terms(roadmap):
    assert "admin" in [t.lower() for t in roadmap.lint_note("New admin dashboard")]
    assert "gdpr" in [t.lower() for t in roadmap.lint_note("GDPR data export tool")]
    assert "moderation" in [t.lower() for t in roadmap.lint_note("Moderation queue")]


def test_audit_flags_internal_scope_in_clean_looking_title(roadmap, repo):
    roadmap.init_project(repo, "P")
    # note reads user-facing, but the title reveals admin-only scope
    roadmap.new_item(repo, "feature", "Admin moderation dashboard", note="Manage your community")
    msgs = roadmap.audit_public_notes(repo)
    assert any("#1" in m and "admin" in m.lower() for m in msgs)


def test_demote_tells_are_high_confidence_only(roadmap):
    # wrong-audience signals (admin/compliance/security/plumbing) demote
    assert "admin" in [t.lower() for t in roadmap.demote_tells("New admin panel")]
    assert "gdpr" in [t.lower() for t in roadmap.demote_tells("GDPR export")]
    # warn-tier wording (vendor/jargon) is NOT a demote signal on its own
    assert roadmap.demote_tells("Refactored the Convex schema") == []


def test_unclassified_item_with_demote_tell_auto_routes_internal(roadmap):
    # a feature would default public, but a high-confidence tell routes it internal…
    assert roadmap.item_audience({"type": "feature", "title": "Admin dashboard"}) == "internal"
    # …unless the audience is set explicitly, which always wins
    assert roadmap.item_audience(
        {"type": "feature", "title": "Admin dashboard", "audience": "public"}) == "public"


def test_audit_flags_explicit_public_with_internal_signal(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Admin tools", note="Manage things", audience="public")
    msgs = roadmap.audit_public_notes(repo)
    assert any("#1" in m and "PUBLIC" in m and "admin" in m.lower() for m in msgs)


def test_internal_changelog_falls_back_to_title(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "chore", "Bump deps")               # internal, no note
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "Bump deps" in (repo / "CHANGELOG.internal.md").read_text()  # title fallback


# ---- collapse shipped versions -------------------------------------------------

def test_shipped_versions_collapse_below_current(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Old thing", version="0.0.1")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.new_item(repo, "feature", "New thing", version="0.1.0")
    roadmap.release(repo, "0.1.0")
    managed = (repo / "ROADMAP.md").read_text().split(
        roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "#1 Old thing" not in managed                  # collapsed away
    assert "### [x] v0.0.1 — 100% · 1 item" in managed    # summary line
    assert "shipped" in managed                           # versionDates date shown
    assert "CHANGELOG.internal.md" in managed             # history pointer
    assert "#2 New thing" in managed                      # current version expanded


def test_done_current_and_future_versions_stay_expanded(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Current work", version="0.0.1")
    roadmap.check_step(repo, 1, None, all_done=True)      # current version 100%
    roadmap.new_item(repo, "feature", "Future done", version="0.1.0")
    roadmap.check_step(repo, 2, None, all_done=True)      # future version 100%
    managed = (repo / "ROADMAP.md").read_text().split(
        roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "#1 Current work" in managed                   # == current: never collapses
    assert "#2 Future done" in managed                    # > current: awaits review/release


def test_collapse_opt_out_setting(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Old thing", version="0.0.1")
    roadmap.check_step(repo, 1, None, all_done=True)
    cfg = roadmap.read_config(repo)
    cfg["settings"]["collapseShipped"] = False
    roadmap.write_config(repo, cfg)
    roadmap.release(repo, "0.1.0")
    managed = (repo / "ROADMAP.md").read_text().split(
        roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "#1 Old thing" in managed                      # opted out: full render


# ---- idea command ---------------------------------------------------------------

def test_idea_adds_single_bullet(roadmap, repo):
    roadmap.init_project(repo, "P")
    note = roadmap.add_idea(repo, "Dark mode toggle")
    assert note is None
    rm = (repo / "ROADMAP.md").read_text()
    freeform = rm.split(roadmap.AUTO_START)[0]
    assert "- Dark mode toggle" in freeform
    assert not (repo / ".roadmap/notes").exists()


def test_idea_with_body_writes_linked_note_file(roadmap, repo):
    roadmap.init_project(repo, "P")
    note = roadmap.add_idea(repo, "Season Pass tier", body="Long brainstorm...\nmany lines")
    assert note is not None and note.exists()
    assert note.parent == repo / ".roadmap/notes"
    text = note.read_text()
    assert text.startswith("# Season Pass tier") and "Long brainstorm..." in text
    freeform = (repo / "ROADMAP.md").read_text().split(roadmap.AUTO_START)[0]
    assert "- Season Pass tier ([notes](.roadmap/notes/" in freeform
    assert "many lines" not in freeform                   # body stays out of ROADMAP.md


def test_idea_note_filenames_dedupe(roadmap, repo):
    roadmap.init_project(repo, "P")
    a = roadmap.add_idea(repo, "Same title", body="one")
    b = roadmap.add_idea(repo, "Same title", body="two")
    assert a != b and a.exists() and b.exists()
    assert b.name.endswith("-2.md")


def test_idea_empty_title_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError):
        roadmap.add_idea(repo, "   ")


def test_cli_idea_body_file(roadmap, repo, monkeypatch, capsys):
    roadmap.init_project(repo, "P")
    src = repo / "brainstorm.md"
    src.write_text("full write-up\n")
    monkeypatch.chdir(repo)
    assert roadmap.main(["idea", "--title", "Widget", "--body-file", str(src)]) == 0
    out = capsys.readouterr().out
    assert "Parked idea: Widget" in out and ".roadmap/notes/" in out


# ---- roadmap_health size warnings ----------------------------------------------

def test_health_quiet_on_small_roadmap(roadmap, repo):
    roadmap.init_project(repo, "P")
    assert roadmap.roadmap_health(repo) == []


def test_health_warns_on_long_freeform_region(roadmap, repo):
    roadmap.init_project(repo, "P")
    rm = repo / "ROADMAP.md"
    filler = "\n".join(f"- idea {i}" for i in range(50))
    rm.write_text(rm.read_text().replace(roadmap.AUTO_START, filler + "\n" + roadmap.AUTO_START))
    msgs = roadmap.roadmap_health(repo)
    assert any("free-form" in m for m in msgs)


def test_health_warns_on_total_length(roadmap, repo):
    roadmap.init_project(repo, "P")
    rm = repo / "ROADMAP.md"
    rm.write_text(rm.read_text() + "\n" * 200)            # blank lines: total, not free-form
    msgs = roadmap.roadmap_health(repo)
    assert len(msgs) == 1                                 # only the total-length warning
    assert "ROADMAP.md is" in msgs[0]


def test_shipped_unnoted_public_item_rolls_up_not_vanishes(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login")            # public, but no note
    roadmap.check_step(repo, 1, None, all_done=True)
    text, warnings = roadmap.render_public_changelog(repo)
    assert "## v0.0.1" in text                            # version block still present
    assert "Login" not in text                            # raw title never leaks
    assert "behind-the-scenes" in text.lower()            # covered by the roll-up line
    assert any("#1" in w and "no note" in w for w in warnings)


def test_health_warns_on_freeform_char_volume(roadmap, repo):
    roadmap.init_project(repo, "P")
    rm = repo / "ROADMAP.md"
    prose = "- huge brainstorm bullet " + "x" * 5000     # few lines, many chars
    rm.write_text(rm.read_text().replace(roadmap.AUTO_START, prose + "\n" + roadmap.AUTO_START))
    msgs = roadmap.roadmap_health(repo)
    assert any("free-form" in m and "characters" in m for m in msgs)


# ---- tidy free-form hygiene report ----------------------------------------------

def _inject_freeform(roadmap, repo, block):
    rm = repo / "ROADMAP.md"
    rm.write_text(rm.read_text().replace(
        roadmap.AUTO_START, block + "\n" + roadmap.AUTO_START))


def test_tidy_clean_on_fresh_roadmap(roadmap, repo):
    roadmap.init_project(repo, "P")
    rep = roadmap.tidy_report(repo)
    assert rep["clean"] is True and rep["bullets"] == []


def test_tidy_flags_long_bullet_without_notes_link(roadmap, repo):
    roadmap.init_project(repo, "P")
    _inject_freeform(roadmap, repo, "- big prose-wall idea " + "x" * 300)
    rep = roadmap.tidy_report(repo)
    assert rep["clean"] is False
    assert any("long-no-link" in b["flags"] for b in rep["bullets"])


def test_tidy_linked_bullet_gets_grace(roadmap, repo):
    # A bullet with a notes link is fine up to twice the budget.
    roadmap.init_project(repo, "P")
    _inject_freeform(roadmap, repo,
                     "- linked idea " + "x" * 250 + " ([notes](.roadmap/notes/x.md))")
    rep = roadmap.tidy_report(repo)
    assert not any("long" in f for b in rep["bullets"] for f in b["flags"])


def test_tidy_flags_nested_sub_bullets(roadmap, repo):
    roadmap.init_project(repo, "P")
    _inject_freeform(roadmap, repo,
                     "- deferred findings\n  - finding one\n  - finding two")
    rep = roadmap.tidy_report(repo)
    flagged = [b for b in rep["bullets"] if "nested" in b["flags"]]
    assert flagged and flagged[0]["children"] == 2


def test_tidy_flags_duplicate_of_tracked_item(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "User data export as portable file")
    _inject_freeform(roadmap, repo, "- User data export as a portable file")
    rep = roadmap.tidy_report(repo)
    dupes = [b for b in rep["bullets"] if "duplicate" in b["flags"]]
    assert dupes and dupes[0]["duplicateOf"] == 1


def test_tidy_counts_prose_outside_bullets(roadmap, repo):
    roadmap.init_project(repo, "P")
    _inject_freeform(roadmap, repo,
                     "**Future phases** promote these when started, long prose here.")
    rep = roadmap.tidy_report(repo)
    assert rep["prose"]["lines"] == 1
    assert rep["prose"]["leads"] and rep["prose"]["leads"][0].startswith("**Future")


def test_tidy_ignores_auto_region(roadmap, repo):
    # Version headings and item rows inside the auto markers never count.
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Something " + "y" * 80)
    rep = roadmap.tidy_report(repo)
    assert rep["clean"] is True


def test_cli_tidy_json(roadmap, repo, monkeypatch, capsys):
    roadmap.init_project(repo, "P")
    monkeypatch.chdir(repo)
    assert roadmap.main(["tidy", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["clean"] is True
    _inject_freeform(roadmap, repo, "- prose wall " + "z" * 400)
    assert roadmap.main(["tidy"]) == 0
    out = capsys.readouterr().out
    assert "needs grooming" in out and "/roadmap:tidy" in out


# ---- changelog --json --------------------------------------------------------------

def test_changelog_json_structure(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    roadmap.new_item(repo, "bug", "Crash", note="Fixed a crash on launch")
    roadmap.new_item(repo, "refactor", "Cache", note="Cache rewrite")   # internal
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    roadmap.check_step(repo, 3, None, all_done=True)
    data = roadmap.changelog_json(repo)
    assert len(data) == 1
    v = data[0]
    assert v["version"] == "0.0.1" and v["released"] is True and v["date"]
    assert v["sections"]["New"] == [{"text": "Sign in with email", "pending": False}]
    assert v["sections"]["Fixed"] == [{"text": "Fixed a crash on launch", "pending": False}]
    assert v["rollup"] is True                       # the internal refactor
    assert "Cache rewrite" not in json.dumps(v)      # internal note never leaks


def test_changelog_json_pending_and_unreleased(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Half done", note="Coming soon thing")
    data = roadmap.changelog_json(repo)
    assert data[0]["released"] is False and data[0]["date"] is None
    assert data[0]["sections"]["New"][0]["pending"] is True


def test_cli_changelog_json(roadmap, repo, monkeypatch, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    roadmap.check_step(repo, 1, None, all_done=True)
    monkeypatch.chdir(repo)
    assert roadmap.main(["changelog", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["sections"]["New"][0]["text"] == "Sign in with email"


# ---- externalized incubator -------------------------------------------------------

def test_externalize_moves_bullets_and_leaves_link(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.add_idea(repo, "First parked idea")
    dest = roadmap.externalize_incubator(repo)
    assert dest == repo / ".roadmap/IDEAS.md"
    ideas = dest.read_text()
    assert "First parked idea" in ideas
    rm_text = (repo / "ROADMAP.md").read_text()
    assert "First parked idea" not in rm_text
    assert ".roadmap/IDEAS.md" in rm_text                 # link bullet stays
    cfg = roadmap.read_config(repo)
    assert cfg["settings"]["incubatorFile"] == ".roadmap/IDEAS.md"


def test_externalize_twice_raises(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.externalize_incubator(repo)
    with pytest.raises(ValueError):
        roadmap.externalize_incubator(repo)


def test_idea_and_promote_target_external_file(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.externalize_incubator(repo)
    roadmap.add_idea(repo, "External parked idea")
    ideas = repo / ".roadmap/IDEAS.md"
    assert "External parked idea" in ideas.read_text()
    assert "External parked idea" not in (repo / "ROADMAP.md").read_text()
    path = roadmap.promote_idea(repo, match="External parked")
    assert path.exists()
    assert "External parked idea" not in ideas.read_text()


def test_remove_demotes_to_external_file(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.externalize_incubator(repo)
    roadmap.new_item(repo, "feature", "Doomed thing")
    roadmap.remove_item(repo, 1)
    assert "(was #1) Doomed thing" in (repo / ".roadmap/IDEAS.md").read_text()
    assert "(was #1)" not in (repo / "ROADMAP.md").read_text()


def test_tidy_report_covers_external_file(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.externalize_incubator(repo)
    ideas = repo / ".roadmap/IDEAS.md"
    ideas.write_text(ideas.read_text() + "- prose wall idea " + "w" * 300 + "\n")
    rep = roadmap.tidy_report(repo)
    assert any("long-no-link" in b["flags"] for b in rep["bullets"])


def test_externalized_dashboard_is_tidy_clean(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.add_idea(repo, "Some idea")
    roadmap.externalize_incubator(repo)
    rep = roadmap.tidy_report(repo)
    assert rep["clean"] is True


# --- next / depends gating / promote / orient / drift / multi-agent rules ------

def test_next_item_skips_blocked_dependency(roadmap, repo, capsys):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    nxt = roadmap.next_item(repo)
    assert nxt is not None and nxt["id"] == 1
    roadmap.check_step(repo, 1, None, all_done=True)
    nxt2 = roadmap.next_item(repo)
    assert nxt2 is not None and nxt2["id"] == 2


def test_next_item_returns_none_when_all_blocked(roadmap, repo, capsys):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    # B depends on A; only B is "next" candidate if we somehow only had B unfinished —
    # with both unfinished, A is chosen. Make A also depend on B → cycle rejected on set.
    # Instead finish nothing and depend B→A: next is A. Force path:
    roadmap.set_depends(repo, 1, [2])  # A blocked by B, B free
    nxt = roadmap.next_item(repo)
    assert nxt is not None and nxt["id"] == 2
    # After finishing B, A unblocks
    roadmap.check_step(repo, 2, None, all_done=True)
    assert roadmap.next_item(repo)["id"] == 1


def test_next_force_ignores_blockers(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 1, [2])
    # Without force, next is #2 (unblocked). With force and we want #1:
    # next_item force still walks in order — first candidate is #1, force allows it.
    nxt = roadmap.next_item(repo, force=True)
    assert nxt["id"] == 1


def test_status_shows_blocked_by(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    st = roadmap.status(repo)
    b = next(i for i in st["items"] if i["id"] == 2)
    assert b["blockedBy"] == [1]
    assert b["dependsOn"] == [1]


def test_cli_next(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["next"]) == 0
    out = capsys.readouterr().out
    assert "#1 Auth" in out


def test_warn_incomplete_deps(roadmap, repo, capsys):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    blocked = roadmap.warn_incomplete_deps(repo, 2)
    assert blocked == [1]
    err = capsys.readouterr().err
    assert "depends on incomplete" in err
    assert roadmap.warn_incomplete_deps(repo, 2, force=True) == [1]
    assert "depends on incomplete" not in capsys.readouterr().err


def test_promote_sole_bullet(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.add_idea(repo, "Dark mode toggle")
    path = roadmap.promote_idea(repo, type_="feature")
    assert path.exists()
    cfg = roadmap.read_config(repo)
    assert any(i["title"] == "Dark mode toggle" for i in cfg["items"])
    rm = (repo / "ROADMAP.md").read_text()
    assert "Dark mode toggle" not in rm.split("roadmap:auto:start")[0] or \
           "- Dark mode toggle" not in rm  # bullet removed from incubator
    # More precise: incubator bullets list empty of that title
    bullets = roadmap.list_incubator_bullets(repo)
    assert all(b["title"] != "Dark mode toggle" for b in bullets)


def test_promote_by_match_and_index(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.add_idea(repo, "Alpha idea")
    roadmap.add_idea(repo, "Beta idea")
    path = roadmap.promote_idea(repo, match="Beta", type_="bug")
    assert "beta" in path.name or path.exists()
    assert any(i["title"] == "Beta idea" for i in roadmap.read_config(repo)["items"])
    path2 = roadmap.promote_idea(repo, index=1, type_="feature")
    assert path2.exists()
    assert roadmap.list_incubator_bullets(repo) == []


def test_promote_requires_selector_when_multiple(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.add_idea(repo, "One")
    roadmap.add_idea(repo, "Two")
    with pytest.raises(ValueError, match="multiple"):
        roadmap.promote_idea(repo)


def test_cli_promote(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.add_idea(repo, "Ship it")
    assert roadmap.main(["promote", "--match", "Ship"]) == 0
    assert any(i["title"] == "Ship it" for i in roadmap.read_config(repo)["items"])


def test_orient_payload(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    payload = roadmap.orient(repo)
    assert payload["project"] == "P"
    assert payload["currentVersion"] == "0.0.1"
    assert payload["next"]["id"] == 1
    assert payload["itemsTotal"] == 1
    text = roadmap.format_orient(payload)
    assert "Auth" in text and "v0.0.1" in text
    # Dual slash forms so Grok never gets colon-only recommendations
    assert "/roadmap-next" in text and "/roadmap:next" in text
    assert "/roadmap-build" in text
    assert "not next --auto" in text


def test_orient_noop_without_roadmap(roadmap, tmp_path):
    assert roadmap.orient(tmp_path) is None


def test_cli_orient_hook_json(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["orient", "--hook"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Auth" in data["hookSpecificOutput"]["additionalContext"]


def _git_commit_all(repo, msg="checkpoint"):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)


def test_drift_check_nudge_after_commits(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    _git_commit_all(repo, "initial roadmap")
    # Baseline check-off stamps last_seen_sha
    roadmap.check_step(repo, 1, 1)  # partial progress so version still unfinished
    assert roadmap.read_config(repo).get("last_seen_sha")
    # Make a new commit without checking off further
    (repo / "extra.txt").write_text("x")
    _git_commit_all(repo, "work outside roadmap")
    msg = roadmap.drift_check(repo)
    assert msg is not None
    assert "commit" in msg and "catchup" in msg


def test_drift_check_silent_when_caught_up(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    _git_commit_all(repo, "initial")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.drift_check(repo) is None


def test_init_writes_agents_md_and_dual_slash_names(roadmap, repo):
    roadmap.init_project(repo, "P")
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (repo / name).read_text()
        assert "roadmap:rules:start" in text
        assert "/roadmap:status" in text and "/roadmap-status" in text
        assert "/roadmap-build" in text and "hyphen only" in text
        assert "Quality-first build" in text
        assert "spec review" in text
        assert "Micro-commit" in text
        assert "Abrupt switch" in text


def test_rules_block_in_example(roadmap):
    from pathlib import Path
    example = Path(roadmap.__file__).resolve().parent.parent / "example" / "CLAUDE.md"
    text = example.read_text()
    assert roadmap.RULES_START in text
    body = text.split(roadmap.RULES_START, 1)[1].split(roadmap.RULES_END, 1)[0]
    assert "/roadmap-build" in body and "hyphen only" in body
    assert "promote" in body.lower() or "roadmap-promote" in body


def test_depends_rejects_two_cycle(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B")
    roadmap.set_depends(repo, 2, [1])
    with pytest.raises(ValueError, match="cycle"):
        roadmap.set_depends(repo, 1, [2])


def test_handoff_includes_checklist_and_skill_version(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["handoff"]) == 0
    out = capsys.readouterr().out
    assert "Auth" in out
    assert "Multi-coder / rate-limit checklist" in out or "rate-limit" in out
    assert "Skill:" in out or "skill" in out.lower()


def test_orient_reports_git_dirty(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    (repo / "loose.txt").write_text("x")
    payload = roadmap.orient(repo)
    assert payload["gitDirty"] is True
    text = roadmap.format_orient(payload)
    assert "uncommitted" in text.lower()


def test_cli_handoff_json(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    assert roadmap.main(["handoff", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "skillVersionInstalled" in data
    assert data["project"] == "P"
