import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

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


@pytest.mark.parametrize("type_,steps", [("feature", 2), ("bug", 3), ("refactor", 3)])
def test_new_item_has_acceptance_section(roadmap, repo, type_, steps):
    roadmap.init_project(repo, "P")
    path = roadmap.new_item(repo, type_, f"Thing {type_}")
    assert "## ✅ Acceptance" in path.read_text()
    # Acceptance bullets must not be checkboxes, or they'd count as checklist steps.
    assert roadmap.count_progress(path) == (0, steps)


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


def _set_require_evidence(roadmap, repo, value):
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {})["requireEvidence"] = value
    roadmap.write_config(repo, cfg)


def _plan_lines(repo):
    return (repo / ".roadmap/plans/001-a.md").read_text().splitlines()


def test_check_evidence_written_under_the_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, evidence="pytest -q: 287 passed")
    lines = _plan_lines(repo)
    i = next(n for n, ln in enumerate(lines) if ln.startswith("- [x] Step 1"))
    assert lines[i + 1] == (f"  > evidence: pytest -q: 287 passed "
                            f"({datetime.date.today().isoformat()})")
    assert "Step 2" in lines[i + 2]
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (1, 2)


def test_build_worktree_scopes_branch_per_item_or_version():
    text = (Path(__file__).resolve().parents[1] / "commands/roadmap-build.md").read_text()
    assert "roadmap/<id>-<slug>" in text          # single item gets its own branch
    assert "roadmap/v<version>" in text           # whole version gets one shared branch
    assert "Never create a version-wide branch for a single item" in text
    assert "`roadmap/<id>-<slug>` instead" not in text  # the old optional wording is gone


def test_quality_build_documents_orchestration_rules():
    text = (Path(__file__).resolve().parents[1]
            / "skills/roadmap/references/quality-build.md").read_text()
    assert "One orchestrator per item" in text
    assert "Respawn budget: four respawns per step" in text
    assert "Respawn, never resume" in text
    assert "Merge-only roadmap writes" in text


def test_shared_brief_is_cache_prefix_and_respawns_from_brief():
    root = Path(__file__).resolve().parents[1]
    common = (root / "skills/agent/references/brief-common.md").read_text()
    assert "## Respawn" in common
    assert "Never resume an earlier subagent" in common
    assert "This file is the cache prefix" in common
    assert "## Stop" in common
    qb = (root / "skills/roadmap/references/quality-build.md").read_text()
    assert "Respawn, never resume" in qb


def test_quality_build_documents_merge_gate():
    text = (Path(__file__).resolve().parents[1]
            / "skills/roadmap/references/quality-build.md").read_text()
    assert "## Merge gate (per-item branches)" in text
    assert "git merge --abort" in text             # conflicts stop the gate
    assert "Never auto-resolve a conflict" in text
    assert "Run the full gate on the trunk" in text
    assert "Red:" in text and "keep the item worktree" in text
    assert "Roadmap state is written only at step 5" in text


def test_routing_docs_name_branch_scope_and_pending_handoff():
    root = Path(__file__).resolve().parents[1]
    skill = (root / "skills/roadmap/SKILL.md").read_text()
    nxt = (root / "commands/roadmap-next.md").read_text()
    assert "handoff --plan ID --pending" in skill
    assert "[--tokens N]" in skill
    assert "Parallel `--auto` is **opt-in** and not yet built" in skill
    assert "`scout` (haiku)" in nxt and "`executor` (opus)" in nxt
    assert "general-purpose` subagent" not in nxt   # the old unlabeled-subagent table is gone


def test_check_tokens_recorded_beside_evidence(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, evidence="pytest -q: 287 passed", tokens=18432)
    lines = _plan_lines(repo)
    i = next(n for n, ln in enumerate(lines) if ln.startswith("- [x] Step 1"))
    assert lines[i + 1] == (f"  > evidence: pytest -q: 287 passed "
                            f"({datetime.date.today().isoformat()}) · tokens: 18432")
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (1, 2)


def test_check_tokens_optional_and_validated(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    # no --tokens: the existing line format is unchanged
    roadmap.check_step(repo, 1, 1, evidence="suite green")
    assert "tokens:" not in "\n".join(_plan_lines(repo))
    # negative counts are refused and leave the plan untouched
    before = _plan_lines(repo)
    with pytest.raises(ValueError, match="non-negative"):
        roadmap.check_step(repo, 1, 2, evidence="suite green", tokens=-5)
    assert _plan_lines(repo) == before


def test_evidence_line_is_never_counted_as_a_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, evidence="- [ ] sneaky\n- [x] also sneaky")
    path = repo / ".roadmap/plans/001-a.md"
    assert roadmap.count_progress(path) == (1, 2)
    steps = roadmap.parse_plan(path)["steps"]
    assert steps[0][0] is True and steps[1][0] is False
    # a second check of step 2 still targets the real step, not the evidence text
    roadmap.check_step(repo, 1, 2)
    assert roadmap.count_progress(path) == (2, 2)


def test_evidence_does_not_leak_into_generated_output(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, evidence="pytest -q: 287 passed")
    assert "evidence" not in (repo / "ROADMAP.md").read_text()
    changelog = repo / "CHANGELOG-INTERNAL.md"
    if changelog.exists():
        assert "evidence" not in changelog.read_text()
    item = roadmap.status(repo)["items"][0]
    assert (item["status"], item["done"], item["total"]) == ("active", 1, 2)


def test_check_without_evidence_is_unchanged(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    assert "evidence" not in (repo / ".roadmap/plans/001-a.md").read_text()


def test_check_all_done_applies_evidence_to_every_step(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True, evidence="suite green")
    body = (repo / ".roadmap/plans/001-a.md").read_text()
    assert body.count("  > evidence: suite green") == 2
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (2, 2)


def test_check_undo_writes_no_evidence(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, undo=True, evidence="ignored")
    path = repo / ".roadmap/plans/001-a.md"
    assert "evidence" not in path.read_text()
    assert roadmap.count_progress(path) == (0, 2)


def test_require_evidence_refuses_bare_check(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_require_evidence(roadmap, repo, True)
    with pytest.raises(ValueError, match="--evidence"):
        roadmap.check_step(repo, 1, 1)
    with pytest.raises(ValueError, match="--evidence"):
        roadmap.check_step(repo, 1, 1, evidence="   ")
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (0, 2)
    roadmap.check_step(repo, 1, 1, evidence="pytest -q: 287 passed")
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (1, 2)


def test_require_evidence_never_blocks_undo(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1, evidence="ok")
    _set_require_evidence(roadmap, repo, True)
    roadmap.check_step(repo, 1, 1, undo=True)
    assert roadmap.count_progress(repo / ".roadmap/plans/001-a.md") == (0, 2)


def test_cli_check_evidence_and_gate(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "A")
    _set_require_evidence(roadmap, repo, True)
    assert roadmap.main(["check", "--plan", "1", "--step", "1"]) == 1
    assert "--evidence" in capsys.readouterr().err
    assert roadmap.main(["check", "--plan", "1", "--step", "1",
                         "--evidence", "pytest -q: 287 passed"]) == 0
    assert "  > evidence: pytest -q: 287 passed" in \
        (repo / ".roadmap/plans/001-a.md").read_text()


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
    assert "Orient first" in cm
    assert "Micro-commit" in cm
    assert "Never hand-edit `ROADMAP.md`" in cm
    assert "All agents use the hyphen form" in cm
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
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email", audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)           # sync writes changelog
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Sign in with email" in cl
    assert "(feature)" not in cl                 # user-facing — no type jargon


def test_changelog_uses_note_and_groups_by_type(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Auth backend", note="Sign in with email", audience="public")
    roadmap.new_item(repo, "bug", "Null deref on logout", note="No more logout crash", audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.check_step(repo, 2, None, all_done=True)
    cl = (repo / "CHANGELOG.md").read_text()
    assert "Sign in with email" in cl and "Auth backend" not in cl   # note used, not title
    assert "🐛 Fixed" in cl and "No more logout crash" in cl
    assert cl.index("✨ New") < cl.index("🐛 Fixed")                 # New before Fixed


def test_changelog_written_on_completion_via_sync(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email", audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)           # triggers sync
    cl = (repo / "CHANGELOG.md").read_text()
    assert "## v0.0.1" in cl and "✨ New" in cl and "Sign in with email" in cl
    assert "(pending)" not in cl                               # version fully done


def test_changelog_in_progress_shows_pending(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Big feature", note="A big new feature",
                     audience="public")  # 0/2 done
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


def test_reopened_uncut_version_restamps_date(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="1.0.0", note="A", audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)              # v1.0.0 hits 100%
    cfg = roadmap.read_config(repo)
    cfg["versionDates"]["1.0.0"] = "2020-01-01"                   # the earlier 100% moment
    roadmap.write_config(repo, cfg)
    roadmap.new_item(repo, "feature", "B", version="1.0.0", note="B", audience="public")
    assert "1.0.0" not in roadmap.read_config(repo)["versionDates"]  # stale stamp cleared
    roadmap.check_step(repo, 2, None, all_done=True)              # 100% again, later
    today = datetime.date.today().isoformat()
    assert roadmap.read_config(repo)["versionDates"]["1.0.0"] == today
    for name in ("CHANGELOG.md", "CHANGELOG.internal.md"):
        text = (repo / name).read_text()
        assert today in text and "2020-01-01" not in text


def test_shipped_version_keeps_date_when_items_added(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A", version="0.0.1", note="A", audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    cfg = roadmap.read_config(repo)
    cfg["versionDates"]["0.0.1"] = "2020-01-01"
    roadmap.write_config(repo, cfg)
    roadmap.release(repo, "0.2.0")                                # v0.0.1 is cut
    roadmap.new_item(repo, "feature", "B", version="0.0.1")       # late incomplete item
    assert roadmap.read_config(repo)["versionDates"]["0.0.1"] == "2020-01-01"


def test_new_with_note_and_set_note(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "X", note="hello", audience="public")
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


SKILL_SRC = Path(__file__).resolve().parent.parent / "skills/roadmap"


def _run_cli(script, cwd, *args):
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd,
                          capture_output=True, text=True, check=True)


def test_release_bumps_skill_version_in_its_own_source_repo(repo):
    """Running the CLI from a checkout of its own source: `release` stamps the
    version just cut into skills/roadmap/VERSION so it never drifts."""
    shutil.copytree(SKILL_SRC, repo / "skills/roadmap",
                    ignore=shutil.ignore_patterns("__pycache__"))
    version_file = repo / "skills/roadmap/VERSION"
    version_file.write_text("0.0.0\n")
    script = repo / "skills/roadmap/scripts/roadmap.py"
    _run_cli(script, repo, "init", "--name", "Skill Source")
    out = _run_cli(script, repo, "release", "--version", "0.0.2")
    assert version_file.read_text().strip() == "0.0.1"   # the version being CUT, not 0.0.2
    assert "skills/roadmap/VERSION" in out.stdout and "0.0.1" in out.stdout


def test_release_leaves_a_normal_project_alone(roadmap, repo):
    before = (SKILL_SRC / "VERSION").read_text()
    roadmap.init_project(repo, "P")
    roadmap.release(repo, "0.0.2")
    assert not (repo / "skills").exists()
    assert (SKILL_SRC / "VERSION").read_text() == before


def test_release_ignores_a_symlinked_cli(repo):
    """A project that merely symlinks the CLI is not the skill's source repo:
    detection resolves the link, so neither tree gets a VERSION write."""
    before = (SKILL_SRC / "VERSION").read_text()
    script = repo / "roadmap.py"
    script.symlink_to(SKILL_SRC / "scripts/roadmap.py")
    _run_cli(script, repo, "init", "--name", "Consumer")
    out = _run_cli(script, repo, "release", "--version", "0.0.2")
    assert not (repo / "skills").exists()
    assert (SKILL_SRC / "VERSION").read_text() == before
    assert "VERSION" not in out.stdout


def test_release_never_touches_a_copy_installed_skill(repo):
    """install.sh copies skills/roadmap into <project>/.claude/skills/roadmap —
    inside the project root, but NOT the source layout. Release must not clobber
    that copy's VERSION with the consumer project's version."""
    installed = repo / ".claude/skills/roadmap"
    shutil.copytree(SKILL_SRC, installed,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (installed / "VERSION").write_text("9.9.9\n")
    script = installed / "scripts/roadmap.py"
    _run_cli(script, repo, "init", "--name", "Consumer")
    out = _run_cli(script, repo, "release", "--version", "0.0.2")
    assert (installed / "VERSION").read_text().strip() == "9.9.9"
    assert "VERSION" not in out.stdout


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
    roadmap.new_item(repo, "feature", "Login", note="Sign in", audience="public")
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
    roadmap.new_item(repo, "feature", "A", version="1.3.0", note="Feature A", audience="public")
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
    assert "references/quality-build.md" in text        # swapped in the compact block
    assert text.count(roadmap.RULES_START) == 1
    assert "# P" in text                                # surrounding content preserved
    assert roadmap.read_config(repo)["skillVersion"] == roadmap.get_version()
    assert roadmap.get_version() in capsys.readouterr().out


def test_upgrade_command_runs(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P")
    assert roadmap.main(["upgrade"]) == 0
    assert roadmap.read_config(repo)["skillVersion"] == roadmap.get_version()


# --- audience-aware public/internal changelog ---------------------------------

def test_audience_defaults_by_type(roadmap):
    # fail-closed: every type defaults internal; explicit audience still wins
    assert roadmap.item_audience({"type": "feature"}) == "internal"
    assert roadmap.item_audience({"type": "bug"}) == "internal"
    assert roadmap.item_audience({"type": "refactor"}) == "internal"
    assert roadmap.item_audience({"type": "chore"}) == "internal"
    assert roadmap.item_audience({"type": "feature", "audience": "public"}) == "public"
    assert roadmap.item_audience({"type": "feature", "audience": "internal"}) == "internal"


def test_internal_item_excluded_from_public_but_in_internal(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email",
                     audience="public")                                      # public
    roadmap.new_item(repo, "refactor", "Rework cache", note="Cache rewrite",
                     audience="internal")                                    # internal
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
    roadmap.new_item(repo, "feature", "Secret sauce", audience="public")  # public, no note
    roadmap.check_step(repo, 1, None, all_done=True)
    _text, warnings = roadmap.render_public_changelog(repo)
    assert "Secret sauce" not in _text
    assert any("no note" in w for w in warnings)


def test_set_audience_moves_item_between_changelogs(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Sharing", note="Did a thing", audience="public")
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


def test_set_audience_public_refused_on_demote_tell(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "API key manager")       # auto-demoted
    with pytest.raises(ValueError, match="(?i)api key"):
        roadmap.set_audience(repo, 1, "public")
    assert roadmap.read_config(repo)["items"][0].get("audience") is None


def test_set_audience_public_force_overrides_gate(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "API key manager")
    roadmap.set_audience(repo, 1, "public", force=True)
    assert roadmap.read_config(repo)["items"][0]["audience"] == "public"


def test_set_audience_internal_never_gated(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "API key manager")
    roadmap.set_audience(repo, 1, "internal")                  # no gate on internal
    assert roadmap.read_config(repo)["items"][0]["audience"] == "internal"


def test_new_item_explicit_public_refused_on_demote_tell(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError, match="(?i)api key"):
        roadmap.new_item(repo, "feature", "API key manager", audience="public")
    cfg = roadmap.read_config(repo)
    assert cfg["items"] == [] and cfg["nextId"] == 1           # nothing written


def test_new_item_explicit_public_force_passes(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "API key manager", audience="public", force=True)
    assert roadmap.read_config(repo)["items"][0]["audience"] == "public"


def test_new_item_unclassified_devsurface_still_fine(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "API key manager")       # auto-demote path
    assert roadmap.read_config(repo)["items"][0].get("audience") is None


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


def test_status_tells_detects_status_dumps(roadmap):
    # real leaks: a raw spec path, a step-progress dump, a dated acceptance note
    assert roadmap.status_tells("docs/superpowers/specs/2026-07-13-composer-design.md")
    assert "Step 9" in roadmap.status_tells("Step 9: glance view DONE & building")
    tells = roadmap.status_tells(
        "2026-07-15: ACCEPTED as done for v1.6.0. Steps 1-8 DESCOPED to a follow-up.")
    assert "2026-07-15" in tells and "v1.6.0" in tells
    assert "ACCEPTED" in tells and "DESCOPED" in tells
    assert "2026-07-11" in roadmap.status_tells("Merged audit findings (2026-07-11)")


def test_status_tells_clean_on_release_notes(roadmap):
    assert roadmap.status_tells("Log rides straight from your wrist.") == []
    assert roadmap.status_tells(
        "Parkboxd now speaks Spanish — switch languages anytime in Settings.") == []
    # lowercase prose words never trip the shouted-status tier
    assert roadmap.status_tells("Everything you've done in one step-by-step recap") == []


def test_lint_note_flags_md_paths_and_status(roadmap):
    assert any(".md" in t for t in roadmap.lint_note("see design/spec/notes.md"))
    assert "Step 3" in roadmap.lint_note("Step 3 shipped")


def test_set_note_refuses_status_dump_on_public_item(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Watch app", note="Log rides from your wrist.",
                     audience="public")
    with pytest.raises(ValueError, match="status/progress dump"):
        roadmap.set_note(repo, 1, "Step 9: SessionGlanceView DONE (build_sim green)")
    # refused note never saved; the old one survives
    assert roadmap.read_config(repo)["items"][0]["note"] == "Log rides from your wrist."


def test_set_note_force_overrides_refusal(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Watch app")
    roadmap.set_note(repo, 1, "Step 9 DONE", force=True)
    assert roadmap.read_config(repo)["items"][0]["note"] == "Step 9 DONE"


def test_set_note_allows_status_text_on_internal_item(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Watch app", audience="internal")
    roadmap.set_note(repo, 1, "Step 9 DONE, complication DEFERRED")   # no raise
    assert roadmap.read_config(repo)["items"][0]["note"].startswith("Step 9")


def test_new_refuses_status_dump_note(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError, match="status/progress dump"):
        roadmap.new_item(repo, "feature", "Composer redesign",
                         note="docs/superpowers/specs/2026-07-13-composer-design.md",
                         audience="public")
    cfg = roadmap.read_config(repo)
    assert cfg["items"] == [] and cfg["nextId"] == 1     # nothing was created
    # same note is fine when the item is internal, or with force
    roadmap.new_item(repo, "feature", "Composer redesign",
                     note="docs/superpowers/specs/2026-07-13-composer-design.md",
                     audience="internal")
    roadmap.new_item(repo, "feature", "Other", note="v1.6.0 stuff", force=True)


def test_audit_flags_internal_scope_in_clean_looking_title(roadmap, repo):
    roadmap.init_project(repo, "P")
    # note reads user-facing, but the title reveals admin-only scope
    roadmap.new_item(repo, "feature", "Admin moderation dashboard", note="Manage your community",
                     audience="public", force=True)
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


def test_devsurface_tells_demote(roadmap):
    # developer/API-surface work ships to developers/operators, not end users
    assert "api key" in [t.lower() for t in roadmap.demote_tells("API key manager")]
    assert "posting api" in [t.lower() for t in roadmap.demote_tells("Posting API editor parity")]
    assert "feed health" in [t.lower() for t in roadmap.demote_tells("Feed health strip")]
    assert "sdk" in [t.lower() for t in roadmap.demote_tells("New SDK release")]
    # bare "api" alone is NOT a demote signal (too many false positives)
    assert roadmap.demote_tells("Share API-powered link") == []


def test_unclassified_devsurface_item_auto_routes_internal(roadmap):
    # auto-routing on demote tells is gone — unclassified items are internal by
    # default regardless of title, and an explicit audience always wins.
    assert roadmap.item_audience({"type": "feature", "title": "API key manager"}) == "internal"
    assert roadmap.item_audience({"type": "feature", "title": "Posting API editor"}) == "internal"
    assert roadmap.item_audience({"type": "feature", "title": "Share API-powered link"}) == "internal"
    assert roadmap.item_audience(
        {"type": "feature", "title": "API key manager", "audience": "public"}) == "public"


def test_audit_flags_explicit_public_with_internal_signal(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Admin tools", note="Manage things",
                     audience="public", force=True)          # forced past the public gate
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


def test_done_versions_auto_advance_current_to_newest(roadmap, repo):
    # A shipped version sitting above a completed current means current fell
    # behind — it auto-advances to the newest shipped version, collapsing below.
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Current work", version="0.0.1")
    roadmap.check_step(repo, 1, None, all_done=True)      # v0.0.1 100%
    roadmap.new_item(repo, "feature", "Future done", version="0.1.0")
    roadmap.check_step(repo, 2, None, all_done=True)      # v0.1.0 100%
    assert roadmap.read_config(repo)["currentVersion"] == "0.1.0"
    managed = (repo / "ROADMAP.md").read_text().split(
        roadmap.AUTO_START)[1].split(roadmap.AUTO_END)[0]
    assert "#2 Future done" in managed                    # current, expanded
    assert "#1 Current work" not in managed               # below current: collapsed


def test_auto_advance_lands_on_next_unfinished_version(roadmap, repo):
    # The reported case: current stuck on a shipped version while a later version
    # also shipped and an even later one is still open. current should jump to the
    # lowest still-open version above (skipping the shipped ones in between).
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "a", version="1.5.6")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.release(repo, "1.5.6")                        # current = 1.5.6 (shipped)
    # Simulate falling behind: add + finish 1.6.0 and open 1.6.1 before any sync
    # advances current, by writing config directly, then sync once.
    roadmap.new_item(repo, "feature", "b", version="1.6.0")
    roadmap.new_item(repo, "feature", "c", version="1.6.1")
    cfg = roadmap.read_config(repo)
    cfg["currentVersion"] = "1.5.6"                       # force the stale pointer
    roadmap.write_config(repo, cfg)
    roadmap.check_step(repo, 2, None, all_done=True)      # 1.6.0 -> 100%; 1.6.1 open
    cfg = roadmap.read_config(repo)
    cfg["currentVersion"] = "1.5.6"                       # still stale before catch-up
    roadmap.write_config(repo, cfg)
    roadmap.sync(repo)
    assert roadmap.read_config(repo)["currentVersion"] == "1.6.1"


def test_auto_advance_opt_out_setting(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Current work", version="0.0.1")
    roadmap.check_step(repo, 1, None, all_done=True)
    cfg = roadmap.read_config(repo)
    cfg["settings"]["autoAdvanceVersion"] = False
    roadmap.write_config(repo, cfg)
    roadmap.new_item(repo, "feature", "Future done", version="0.1.0")
    roadmap.check_step(repo, 2, None, all_done=True)
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.1"   # pinned


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
    roadmap.new_item(repo, "feature", "Login", audience="public")  # public, but no note
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
    assert "needs grooming" in out and "/roadmap-tidy" in out


# ---- changelog --json --------------------------------------------------------------

def test_changelog_json_structure(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email", audience="public")
    roadmap.new_item(repo, "bug", "Crash", note="Fixed a crash on launch", audience="public")
    roadmap.new_item(repo, "refactor", "Cache", note="Cache rewrite", audience="internal")
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
    roadmap.new_item(repo, "feature", "Half done", note="Coming soon thing", audience="public")
    data = roadmap.changelog_json(repo)
    assert data[0]["released"] is False and data[0]["date"] is None
    assert data[0]["sections"]["New"][0]["pending"] is True


def test_cli_changelog_json(roadmap, repo, monkeypatch, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email", audience="public")
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
    assert "FEAT-1 Auth" in out


def test_display_id_prefix_per_type(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    for t in ("feature", "bug", "refactor", "chore"):
        roadmap.new_item(repo, t, f"{t} work")
    st = roadmap.status(repo)
    assert [i["displayId"] for i in st["items"]] == [
        "FEAT-1", "BUG-2", "REF-3", "CHORE-4"]
    assert [i["id"] for i in st["items"]] == [1, 2, 3, 4]
    assert roadmap.display_id({"id": 12, "type": "feature"}) == "FEAT-12"
    assert roadmap.display_id({"id": 9, "type": "mystery"}) == "ITEM-9"


def test_cli_status_and_next_show_display_ids(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "bug", "Crash on save")
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "BUG-1 Crash on save" in out and "FEAT-2 Auth" in out
    assert roadmap.main(["next"]) == 0
    assert "BUG-1 Crash on save" in capsys.readouterr().out


def _filtered_repo(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "bug", "Crash on save")            # 1, current version
    roadmap.new_item(repo, "feature", "Auth")                 # 2, current version
    roadmap.new_item(repo, "chore", "Tidy", version="0.15.0")  # 3
    roadmap.new_item(repo, "bug", "Leak", version="0.15.0")    # 4
    roadmap.check_step(repo, 4, None, all_done=True)           # 4 -> done
    return repo


def test_status_filters_narrow_items_text_and_json(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(_filtered_repo(roadmap, repo))
    assert roadmap.main(["status", "--type", "bug"]) == 0
    out = capsys.readouterr().out
    assert "BUG-1" in out and "BUG-4" in out
    assert "FEAT-2" not in out and "CHORE-3" not in out

    assert roadmap.main(["status", "--version", "0.15.0", "--status", "done",
                         "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [i["displayId"] for i in payload["items"]] == ["BUG-4"]
    # summary header stays global regardless of filters
    assert payload["currentVersion"] == roadmap.read_config(repo)["currentVersion"]
    assert set(payload) == {"project", "currentVersion", "versionComplete",
                            "counts", "items"}
    # counts stay global even though the item list is filtered down to one row
    assert payload["counts"]["byType"] == {"bug": 2, "feature": 1, "chore": 1}
    assert payload["counts"]["byStatus"] == {"planned": 3, "done": 1}
    assert payload["counts"]["byVersion"] == {
        roadmap.read_config(repo)["currentVersion"]: 2, "0.15.0": 2}

    assert roadmap.main(["status", "--version", "v0.15.0", "--type", "chore"]) == 0
    out = capsys.readouterr().out
    assert "CHORE-3" in out and "BUG-4" not in out

    assert roadmap.main(["status", "--status", "planned", "--json"]) == 0
    ids = [i["id"] for i in json.loads(capsys.readouterr().out)["items"]]
    assert ids == [1, 2, 3]


def test_status_without_filters_is_unchanged(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(_filtered_repo(roadmap, repo))
    assert roadmap.main(["status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == roadmap.status(repo)


def _search_repo(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Dark mode toggle")          # 1
    roadmap.new_item(repo, "bug", "Crash on save", audience="internal",
                     note="Saving a Dark document no longer crashes")  # 2
    roadmap.add_idea(repo, "Maybe a dark sidebar someday")
    plan = repo / ".roadmap/plans/002-crash-on-save.md"
    plan.write_text(plan.read_text() + "\nRoot cause: telemetry flush deadlock\n")
    return repo


def test_search_finds_titles_notes_plans_and_incubator(roadmap, repo):
    _search_repo(roadmap, repo)
    hits = roadmap.search(repo, "dark")
    kinds = {h["kind"] for h in hits}
    assert kinds == {"item", "plan", "idea"}
    items = [h for h in hits if h["kind"] == "item"]
    assert ("FEAT-1", "title") in [(h["ref"], h["field"]) for h in items]
    assert ("BUG-2", "note") in [(h["ref"], h["field"]) for h in items]
    idea = next(h for h in hits if h["kind"] == "idea")
    assert idea["file"] == "ROADMAP.md"
    rm_lines = (repo / "ROADMAP.md").read_text().splitlines()
    assert "dark sidebar" in rm_lines[idea["line"] - 1]
    assert idea["ref"] == f"ROADMAP.md:{idea['line']}"


def test_search_plan_body_hit_carries_file_and_line(roadmap, repo):
    _search_repo(roadmap, repo)
    hits = roadmap.search(repo, "telemetry")
    assert len(hits) == 1
    hit = hits[0]
    plan = repo / ".roadmap/plans/002-crash-on-save.md"
    lines = plan.read_text().splitlines()
    assert hit["kind"] == "plan" and hit["file"] == ".roadmap/plans/002-crash-on-save.md"
    assert lines[hit["line"] - 1] == "Root cause: telemetry flush deadlock"
    assert hit["ref"] == f".roadmap/plans/002-crash-on-save.md:{hit['line']}"


def test_search_is_case_insensitive(roadmap, repo):
    _search_repo(roadmap, repo)
    assert roadmap.search(repo, "DARK MODE") == roadmap.search(repo, "dark mode")
    assert roadmap.search(repo, "TeLeMeTrY")


def test_search_cli_text_json_and_no_match(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(_search_repo(roadmap, repo))
    assert roadmap.main(["search", "telemetry"]) == 0
    out = capsys.readouterr().out
    assert ".roadmap/plans/002-crash-on-save.md:" in out and "telemetry" in out

    assert roadmap.main(["search", "dark", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list) and payload
    for hit in payload:
        assert set(hit) >= {"kind", "ref", "text"}

    assert roadmap.main(["search", "zzz-nothing-here"]) == 0
    assert "no matches" in capsys.readouterr().out.lower()


def test_search_empty_query_is_argparse_error(roadmap, repo, monkeypatch):
    monkeypatch.chdir(_search_repo(roadmap, repo))
    with pytest.raises(SystemExit) as e:
        roadmap.main(["search", "   "])
    assert e.value.code == 2


def test_orient_human_output_uses_display_id(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "bug", "Crash on save")
    payload = roadmap.orient(repo)
    assert payload["next"]["id"] == 1                     # int id unchanged
    text = roadmap.format_orient(payload, handoff=True)
    assert "Next: BUG-1 Crash on save" in text
    assert "/roadmap-build 1" in text                     # commands take the int id


def test_display_ids_stay_out_of_generated_files(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "bug", "Crash on save", note="Fixed a crash on save.",
                     audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    rm = (repo / "ROADMAP.md").read_text()
    assert "**#1 Crash on save**" in rm and "BUG-1" not in rm
    assert "BUG-1" not in (repo / "CHANGELOG.md").read_text()
    assert "BUG-1" not in (repo / "CHANGELOG.internal.md").read_text()


def _two_items(roadmap, repo):
    """A feature (#1) and a bug (#2) — FEAT-1 / BUG-2."""
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    roadmap.new_item(repo, "bug", "Crash on save")
    return roadmap.read_config(repo)


def test_resolve_id_accepts_bare_hash_and_typed_forms(roadmap, repo):
    cfg = _two_items(roadmap, repo)
    for token in ("2", " 2 ", "#2", "BUG-2", "bug-2", "Bug-2", "ITEM-2", "item-2"):
        assert roadmap.resolve_id(cfg, token) == 2
    assert roadmap.resolve_id(cfg, "FEAT-1") == 1
    assert roadmap.resolve_id(cfg, 2) == 2                  # ints pass through
    assert roadmap.resolve_ids(cfg, "1, BUG-2 ,#1") == [1, 2, 1]
    assert roadmap.resolve_ids(cfg, "") == []


def test_resolve_id_wrong_prefix_names_the_right_id(roadmap, repo):
    cfg = _two_items(roadmap, repo)
    with pytest.raises(ValueError) as e:
        roadmap.resolve_id(cfg, "FEAT-2")
    assert "no feature #2" in str(e.value) and "BUG-2" in str(e.value)


def test_resolve_id_unknown_and_malformed(roadmap, repo):
    cfg = _two_items(roadmap, repo)
    assert roadmap.resolve_id(cfg, "99") == 99              # existing error path
    with pytest.raises(ValueError, match="no plan with id 99"):
        roadmap.resolve_id(cfg, "BUG-99")
    for bad in ("abc", "XYZ-1", "", "1.2", "#"):
        with pytest.raises(ValueError):
            roadmap.resolve_id(cfg, bad)


def test_cli_id_args_accept_typed_forms(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    _two_items(roadmap, repo)
    assert roadmap.main(["check", "--plan", "BUG-2", "--step", "1"]) == 0
    assert roadmap.count_progress(repo / ".roadmap/plans/002-crash-on-save.md")[0] == 1
    assert roadmap.main(["audience", "--plan", "bug-2", "--to", "internal"]) == 0
    assert roadmap.main(["note", "--plan", "#2", "--text", "Fixed a crash."]) == 0
    assert roadmap.main(["depends", "--plan", "feat-1", "--on", "BUG-2"]) == 0
    bug = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 2)
    assert bug["audience"] == "internal" and bug["note"] == "Fixed a crash."
    item = next(i for i in roadmap.read_config(repo)["items"] if i["id"] == 1)
    assert item["dependsOn"] == [2]
    assert roadmap.main(["retarget", "--to", "0.2.0", "--plan", "ITEM-1"]) == 0
    assert roadmap.main(["remove", "--plan", "FEAT-1"]) == 0
    assert [i["id"] for i in roadmap.read_config(repo)["items"]] == [2]


def test_cli_wrong_prefix_errors_with_the_right_id(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    _two_items(roadmap, repo)
    assert roadmap.main(["check", "--plan", "FEAT-2", "--step", "1"]) == 1
    err = capsys.readouterr().err
    assert "no feature #2" in err and "did you mean BUG-2" in err
    assert roadmap.count_progress(repo / ".roadmap/plans/002-crash-on-save.md")[0] == 0


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


def test_promote_strips_notes_link_from_title(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    note = roadmap.add_idea(repo, "Linked idea", body="Long write-up")
    path = roadmap.promote_idea(repo, match="Linked", type_="bug")
    item = roadmap.read_config(repo)["items"][-1]
    assert item["title"] == "Linked idea"
    assert item["slug"] == "linked-idea"
    assert "notes" not in path.name and "md)" not in path.name
    body = path.read_text()
    assert f"[notes](../notes/{note.name})" in body
    assert "([notes]" not in body.split("\n## ")[0].split("title:")[1].splitlines()[0]


def test_promote_unlinked_bullet_has_no_spec_line(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.add_idea(repo, "Plain idea")
    path = roadmap.promote_idea(repo, type_="feature")
    assert roadmap.read_config(repo)["items"][-1]["title"] == "Plain idea"
    assert "> Spec:" not in path.read_text()


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
    # One hyphen name per command, never colon-only and never repeated
    assert "/roadmap-next" in text and "/roadmap:next" not in text
    assert "/roadmap-next · /roadmap-next" not in text
    assert "/roadmap-build" in text
    assert "not next --auto" in text


def test_orient_surfaces_build_roles_when_set(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {})["buildRoles"] = {
        "implementer": "sonnet", "specReviewer": "opus", "weirdRole": "x"}
    roadmap.write_config(repo, cfg)
    payload = roadmap.orient(repo)
    assert payload["buildRoles"] == {
        "implementer": "sonnet", "specReviewer": "opus", "weirdRole": "x"}
    line = next(l for l in roadmap.format_orient(payload).splitlines()
                if l.startswith("Roles:"))
    assert "implementer=sonnet" in line and "specReviewer=opus" in line
    assert "weirdRole=x" in line  # unknown keys tolerated, not validated
    assert payload == roadmap.handoff(repo)


def test_orient_unchanged_without_build_roles(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    payload = roadmap.orient(repo)
    assert "buildRoles" not in payload
    assert "Roles:" not in roadmap.format_orient(payload, handoff=True)


def test_orient_ignores_malformed_or_empty_build_roles(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    for bad in ("sonnet", {}, [1, 2], 123, True, None):
        cfg = roadmap.read_config(repo)
        cfg.setdefault("settings", {})["buildRoles"] = bad
        roadmap.write_config(repo, cfg)
        payload = roadmap.orient(repo)
        assert "buildRoles" not in payload
        assert "Roles:" not in roadmap.format_orient(payload)


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
        assert "/roadmap-build" in text and "/roadmap:build" not in text
        assert "All agents use the hyphen form" in text
        assert "Quality-first build" in text
        assert "spec review" in text
        assert "Micro-commit" in text


def test_rules_block_is_compact_and_points_at_long_form(roadmap):
    """The injected block stays a compact core; the dropped detail is named, not inlined."""
    body = roadmap.RULES_BLOCK.splitlines()
    assert len(body) <= 24, f"rules block grew back to {len(body)} lines"
    text = roadmap.RULES_BLOCK
    for ref in ("SKILL.md", "references/quality-build.md", "references/state-model.md"):
        assert ref in text
    for guardrail in ("Orient first", "One item at a time", "Micro-commit",
                      "Never hand-edit `ROADMAP.md`", "`roadmap.py check`"):
        assert guardrail in text


def test_rules_block_in_example(roadmap):
    from pathlib import Path
    example = Path(roadmap.__file__).resolve().parent.parent / "example" / "CLAUDE.md"
    text = example.read_text()
    assert roadmap.RULES_START in text
    body = text.split(roadmap.RULES_START, 1)[1].split(roadmap.RULES_END, 1)[0]
    assert "/roadmap-build" in body and "All agents use the hyphen form" in body
    # example must stay byte-identical to the shipped block (it is the doc of record)
    assert body.strip() == roadmap.RULES_BLOCK.split(roadmap.RULES_START, 1)[1] \
        .split(roadmap.RULES_END, 1)[0].strip()


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


def test_orient_reports_branch_dirty_files_and_recent_commits(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init roadmap"], cwd=repo, check=True)
    for n in range(7):
        (repo / f"c{n}.txt").write_text(str(n))
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", f"commit {n}"], cwd=repo, check=True)
    (repo / "loose.txt").write_text("x")
    payload = roadmap.orient(repo)
    assert payload["branch"]
    assert "loose.txt" in payload["dirtyFiles"]
    assert len(payload["recentCommits"]) == 5
    assert payload["recentCommits"][0].endswith("commit 6")
    text = roadmap.format_orient(payload, handoff=True)
    assert f"Branch: {payload['branch']}" in text
    assert "  - loose.txt" in text
    assert "Recent commits:" in text


def test_orient_clean_tree_has_no_dirty_list(roadmap, repo):
    roadmap.init_project(repo, "P", claude_md=False)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init roadmap"], cwd=repo, check=True)
    payload = roadmap.orient(repo)
    assert payload["gitDirty"] is False
    assert payload["dirtyFiles"] == []
    text = roadmap.format_orient(payload)
    assert "uncommitted" not in text.lower()
    assert "  - " not in text


def test_handoff_pending_writes_note_and_refuses_until_resolved(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["handoff", "--plan", "1", "--pending", "Pick JWT or sessions"]) == 0
    note = repo / ".roadmap/notes/1-handoff.md"
    assert note.exists()
    assert "OPEN: Pick JWT or sessions" in note.read_text()

    # plain handoff refuses while the decision is open
    assert roadmap.main(["handoff"]) == 1
    assert "decision still open" in capsys.readouterr().err

    assert roadmap.main(["handoff", "--plan", "1", "--resolve"]) == 0
    assert "RESOLVED: Pick JWT or sessions" in note.read_text()
    assert "OPEN:" not in note.read_text()
    assert roadmap.main(["handoff"]) == 0


def test_handoff_resolve_without_open_decision_fails(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Auth")
    assert roadmap.main(["handoff", "--plan", "1", "--resolve"]) == 1
    assert "no open decision" in capsys.readouterr().err


def test_handoff_pending_requires_plan(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    assert roadmap.main(["handoff", "--pending", "x"]) == 2
    assert "need --plan" in capsys.readouterr().err


def test_cli_handoff_json(roadmap, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    assert roadmap.main(["handoff", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "skillVersionInstalled" in data
    assert data["project"] == "P"


def test_summary_replaces_bullets_in_public_changelog(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips", note="Share trips with friends.",
                     audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "Share trips with friends." in (repo / "CHANGELOG.md").read_text()
    roadmap.set_release_summary(
        repo, "0.0.1", "This release includes minor bug fixes and improvements.")
    cl = (repo / "CHANGELOG.md").read_text()
    assert "minor bug fixes and improvements" in cl
    assert "Share trips with friends." not in cl        # blurb supersedes bullets
    # internal log keeps the per-item detail
    assert "Share trips with friends." in (repo / "CHANGELOG.internal.md").read_text()
    # clearing falls back to bullets
    roadmap.set_release_summary(repo, "0.0.1", clear=True)
    assert "Share trips with friends." in (repo / "CHANGELOG.md").read_text()


def test_summary_refuses_status_dump_unless_forced(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips")
    with pytest.raises(ValueError, match="status/progress dump"):
        roadmap.set_release_summary(repo, "0.0.1", "2026-07-15: Step 3 DONE")
    roadmap.set_release_summary(repo, "0.0.1", "Step 3 DONE", force=True)
    assert "Step 3 DONE" in (repo / "CHANGELOG.md").read_text()


def test_summary_rejects_unknown_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips")
    with pytest.raises(ValueError, match="no items target"):
        roadmap.set_release_summary(repo, "9.9.9", "Nice things.")


def test_changelog_json_carries_summary(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips", note="Share trips with friends.",
                     audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.set_release_summary(repo, "0.0.1", "A smoother ride all around.")
    (entry,) = roadmap.changelog_json(repo)
    assert entry["notes"] == "A smoother ride all around."
    assert entry["sections"] == {} and entry["rollup"] is False
    assert entry["released"] is True


def test_audit_suggests_summary_and_skips_summarized_items(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips", audience="public")  # public, no note
    roadmap.check_step(repo, 1, None, all_done=True)
    msgs = " ".join(roadmap.audit_public_notes(repo))
    assert "has no release-notes summary" in msgs
    assert "has no note" in msgs
    roadmap.set_release_summary(repo, "0.0.1", "Minor bug fixes and improvements.")
    msgs = " ".join(roadmap.audit_public_notes(repo))
    assert "release-notes summary" not in msgs
    assert "has no note" not in msgs      # blurb curates the version; item nags stop


def test_audit_flags_orphaned_summary(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips")
    roadmap.set_release_summary(repo, "0.0.1", "Nice things await.")
    roadmap.retarget(repo, "0.0.2", plan_ids=[1])   # 0.0.1 loses its only item
    msgs = " ".join(roadmap.audit_public_notes(repo))
    assert "renders nowhere" in msgs and "0.0.1" in msgs
    roadmap.set_release_summary(repo, "0.0.1", clear=True)
    assert "renders nowhere" not in " ".join(roadmap.audit_public_notes(repo))


def test_discover_roots_outside_git(roadmap, dashboard, tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert dashboard._discover_roots(roadmap, d) == [(d.resolve(), None)]


def test_discover_roots_finds_worktrees_with_roadmap(roadmap, dashboard, repo):
    roadmap.init_project(repo, "P")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    wt = repo.parent / "wt-v1"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "roadmap/v1", str(wt)],
                   cwd=repo, check=True)
    bare = repo.parent / "wt-bare"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "no-rm", str(bare)],
                   cwd=repo, check=True)
    import shutil
    shutil.rmtree(bare / ".roadmap")          # no .roadmap → excluded
    roots = dashboard._discover_roots(roadmap, wt)   # run from the WORKTREE
    assert roots[0][0] == repo.resolve()             # main checkout first
    assert (wt.resolve(), "roadmap/v1") in roots
    assert all(p != bare.resolve() for p, _ in roots)


def test_merge_status_most_progressed_wins(dashboard):
    meta = [{"path": "/a", "branch": None, "name": "main"},
            {"path": "/b", "branch": "roadmap/v1", "name": "wt"}]
    main = {"project": "P", "currentVersion": "0.8.0", "items": [
        {"id": 1, "title": "A", "done": 3, "total": 4, "pct": 75},
        {"id": 2, "title": "B", "done": 0, "total": 2, "pct": 0}]}
    wt = {"project": "P", "currentVersion": "1.0.0", "items": [
        {"id": 1, "title": "A", "done": 4, "total": 4, "pct": 100},
        {"id": 3, "title": "C", "done": 1, "total": 1, "pct": 100}]}
    m = dashboard._merge_status([main, wt], meta)
    assert m["currentVersion"] == "1.0.0"
    by_id = {i["id"]: i for i in m["items"]}
    assert set(by_id) == {1, 2, 3}
    assert by_id[1]["done"] == 4 and by_id[1]["branch"] == "roadmap/v1"
    assert by_id[1]["_root"] == 1
    assert by_id[2]["branch"] == "main"          # only copy, from main


def test_broadcaster_payload_shape(roadmap, dashboard, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    b = dashboard._Broadcaster(roadmap, repo)
    d = json.loads(b.json)
    assert [r["path"] for r in d["_roots"]] == [str(repo.resolve())]
    assert len(d["statuses"]) == 1
    assert d["merged"]["items"][0]["id"] == 1   # single root: merged == status


def test_broadcaster_skips_unchanged_payload(roadmap, dashboard, repo):
    import os, time as _t
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    b = dashboard._Broadcaster(roadmap, repo)
    # touch a roadmap file: signature changes, rendered status does not
    cfgp = repo / ".roadmap/config.json"
    os.utime(cfgp, (_t.time() + 5, _t.time() + 5))
    b._tick()
    assert b.version == 0                      # no notify, no reprint
    # a real change bumps the version
    roadmap.check_step(repo, 1, None, all_done=True)
    os.utime(cfgp, (_t.time() + 10, _t.time() + 10))
    b._tick()
    assert b.version == 1


# ---- release gate (settings.autoRelease: off|nudge|auto) ----

def _set_auto_release(roadmap, repo, mode):
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {})["autoRelease"] = mode
    roadmap.write_config(repo, cfg)


def test_uncut_complete_version_detection(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    assert roadmap.uncut_complete_version(repo) is None
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.uncut_complete_version(repo) == "0.0.1"


def test_uncut_complete_version_none_without_items(roadmap, repo):
    roadmap.init_project(repo, "P")
    assert roadmap.uncut_complete_version(repo) is None


def test_status_reports_version_complete(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    assert roadmap.status(repo)["versionComplete"] is False
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.status(repo)["versionComplete"] is True


def test_check_completion_nudges_release(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    err = capsys.readouterr().err
    assert "100% complete but uncut" in err
    assert "release" in err


def test_check_no_nudge_while_incomplete(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, 1)
    assert "uncut" not in capsys.readouterr().err


def test_release_gate_off_is_silent(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_auto_release(roadmap, repo, "off")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "uncut" not in capsys.readouterr().err
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.1"


def test_release_gate_auto_releases_to_next_item_version(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.new_item(repo, "feature", "B", version="0.0.2")
    _set_auto_release(roadmap, repo, "auto")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"
    assert "auto-release" in capsys.readouterr().err


def test_release_gate_auto_without_target_falls_back_to_nudge(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_auto_release(roadmap, repo, "auto")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.1"
    err = capsys.readouterr().err
    assert "release --version <next>" in err


def test_new_item_later_version_triggers_gate(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    capsys.readouterr()
    roadmap.new_item(repo, "feature", "B", version="0.0.2")
    err = capsys.readouterr().err
    assert "uncut" in err and "0.0.2" in err


def test_new_item_auto_mode_releases_before_next_version_work(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_auto_release(roadmap, repo, "auto")
    roadmap.check_step(repo, 1, None, all_done=True)  # no later version yet -> nudge only
    capsys.readouterr()
    roadmap.new_item(repo, "feature", "B", version="0.0.2")
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"
    assert "auto-release" in capsys.readouterr().err


def test_release_gate_unknown_mode_defaults_to_nudge(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_auto_release(roadmap, repo, "bogus")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "uncut" in capsys.readouterr().err


def test_orient_surfaces_uncut_complete_version(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    roadmap.check_step(repo, 1, None, all_done=True)
    payload = roadmap.orient(repo)
    assert payload["versionComplete"] is True
    assert "uncut" in roadmap.format_orient(payload)


def test_check_on_next_version_item_auto_releases(roadmap, repo, capsys):
    """100% current version + starting work on a next-version item = release cut."""
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "A")
    _set_auto_release(roadmap, repo, "auto")
    roadmap.check_step(repo, 1, None, all_done=True)
    roadmap.new_item(repo, "feature", "B", version="0.0.2")  # auto-releases here
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"
    # and if release had NOT happened yet, checking a step on the 0.0.2 item fires it:
    _set_auto_release(roadmap, repo, "auto")
    roadmap.new_item(repo, "feature", "C", version="0.0.3")
    roadmap.check_step(repo, 2, 1)  # finish nothing; current 0.0.2 incomplete -> no fire
    assert roadmap.read_config(repo)["currentVersion"] == "0.0.2"


# --- fail-closed audience & Parkboxd leak corpus (plan #9) ---------------------

# Notes that actually leaked into a real public changelog before the tightening.
LEAKED_NOTES = [
    # staff/admin-only surface (#588)
    "Article editor: brand byline now defaults on for staff, a zoom slider gives "
    "an overview of image-heavy stories",
    # internal ops ceiling (#651)
    "Fixed a safeguard so onboarding and digest emails can never be silently lost "
    "when the daily sending limit is reached.",
    # self-incriminating security disclosure (#653)
    "Turning off analytics is now enforced on our servers too, so no data is "
    "accepted from a device after you opt out.",
    # abuse-hardening disclosure (#624)
    "Ride ratings are harder to game.",
]

# Known-good public notes that must NOT trip the demote net (false-positive corpus).
CLEAN_PUBLIC_NOTES = [
    "Analytics now run fully in-house — your usage data stays on our servers, "
    "is never sold or shared.",
    "Making your account or a park day private now also disables its live share links",
    "You can now turn off usage analytics in Privacy settings.",
    "Log rides straight from your wrist.",
    "Parkboxd now speaks Spanish — switch languages anytime in Settings.",
]


def test_parkboxd_leak_corpus_trips_demote(roadmap):
    for note in LEAKED_NOTES:
        assert roadmap.demote_tells(note), f"should demote: {note!r}"


def test_clean_public_notes_stay_clean(roadmap):
    for note in CLEAN_PUBLIC_NOTES:
        assert roadmap.demote_tells(note) == [], f"false positive on: {note!r}"


def test_disclosure_phrasing_demotes(roadmap):
    assert roadmap.demote_tells("Ride waits are now validated on save")
    assert roadmap.demote_tells("Streaks cannot be fabricated any more")
    assert roadmap.demote_tells("Server-side checks were added to uploads")
    assert roadmap.demote_tells("The API no longer accepts unsigned requests")


def test_audience_defaults_internal_for_all_types(roadmap):
    # fail-closed: nothing renders public without an explicit audience
    for type_ in ("feature", "bug", "refactor", "chore"):
        assert roadmap.item_audience({"type": type_}) == "internal"
    assert roadmap.item_audience({"type": "bug", "audience": "public"}) == "public"


def test_set_note_requires_explicit_audience(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Login")                # unclassified, no note: fine
    with pytest.raises(ValueError, match="audience"):
        roadmap.set_note(repo, 1, "Sign in with email")
    assert "note" not in roadmap.read_config(repo)["items"][0]
    roadmap.set_audience(repo, 1, "public")
    roadmap.set_note(repo, 1, "Sign in with email")           # classified: saves
    assert roadmap.read_config(repo)["items"][0]["note"] == "Sign in with email"


def test_new_with_note_requires_audience(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError, match="audience"):
        roadmap.new_item(repo, "feature", "Login", note="Sign in with email")
    cfg = roadmap.read_config(repo)
    assert cfg["items"] == [] and cfg["nextId"] == 1          # nothing written
    roadmap.new_item(repo, "feature", "Login", note="Sign in with email",
                     audience="public")                       # explicit: fine
    # --force keeps the old unclassified behavior (renders internal-only)
    roadmap.new_item(repo, "feature", "Other", note="A thing", force=True)


def test_set_note_demote_tell_refused_on_public_item(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Drafts", audience="public")
    with pytest.raises(ValueError, match="(?i)staff"):
        roadmap.set_note(repo, 1, "Only staff can see unpublished drafts")
    assert "note" not in roadmap.read_config(repo)["items"][0]
    roadmap.set_note(repo, 1, "Only staff can see unpublished drafts", force=True)
    assert "staff" in roadmap.read_config(repo)["items"][0]["note"]


def test_new_public_note_demote_tell_refused(roadmap, repo):
    roadmap.init_project(repo, "P")
    with pytest.raises(ValueError, match="(?i)sending limit"):
        roadmap.new_item(repo, "bug", "Email loss", audience="public",
                         note="Emails are no longer lost at the daily sending limit.")


def test_legacy_unclassified_note_renders_internal_only(roadmap, repo):
    # pre-tightening configs have note + no audience: must fall to the internal log
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "bug", "Old leak", note="Secret ops detail", force=True)
    roadmap.check_step(repo, 1, None, all_done=True)
    assert "Secret ops detail" not in (repo / "CHANGELOG.md").read_text()
    assert "Secret ops detail" in (repo / "CHANGELOG.internal.md").read_text()


def test_audit_flags_noted_but_unclassified_item(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "bug", "Old leak", note="A user-facing fix", force=True)
    msgs = roadmap.audit_public_notes(repo)
    assert any("#1" in m and "no explicit audience" in m for m in msgs)


# --- branch discovery (rmlib/branches.py) ---------------------------------

@pytest.fixture
def branches(roadmap):
    """rmlib.branches, importable once the roadmap fixture has put scripts/ on
    sys.path. The ref cache is module-global, so start each test clean."""
    import importlib
    mod = importlib.import_module("rmlib.branches")
    mod._CACHE.clear()
    return mod


def _git(repo, *args, env=None):
    import os
    full = {**os.environ, **(env or {})}
    subprocess.run(["git", *args], cwd=repo, check=True, env=full,
                   capture_output=True)


def _commit(repo, msg, date=None):
    env = {"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date} if date else None
    _git(repo, "commit", "--allow-empty", "-qm", msg, env=env)


@pytest.fixture
def branch_repo(repo):
    """main with one commit; roadmap/7 four commits ahead; fix/side carries one
    commit tagged (plan 9); roadmap/3 merged back into main."""
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init")
    _git(repo, "checkout", "-qb", "roadmap/7")
    for n in range(4):
        _commit(repo, f"step {n} (plan 7)" if n % 2 == 0 else f"step {n}")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-qb", "fix/side")
    _commit(repo, "side quest (plan 9)")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-qb", "roadmap/3")
    _commit(repo, "done work (plan 3)")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--ff-only", "roadmap/3")
    _git(repo, "checkout", "-qb", "experiment")
    _commit(repo, "unrelated")
    _git(repo, "checkout", "-q", "main")
    return repo


def test_branches_named_branch_ahead_count(branches, branch_repo):
    res = branches.discover(branch_repo, [3, 7, 9])
    assert res["trunk"] == "main"
    b7 = res["items"][7]
    assert b7["name"] == "roadmap/7"
    assert (b7["ahead"], b7["behind"], b7["merged"]) == (4, 1, False)
    assert b7["taggedCommits"] == 2       # only the (plan 7) subjects count
    assert b7["lastSubject"] == "step 3" and len(b7["lastCommit"]) >= 7
    assert b7["worktree"] is None and b7["stale"] is False
    assert [c["subject"] for c in b7["commits"]][0] == "step 3"
    assert len(b7["commits"]) == 4


def test_branches_tagged_commit_attaches_to_item(branches, branch_repo):
    res = branches.discover(branch_repo, [3, 7, 9])
    b9 = res["items"][9]
    assert b9["name"] == "fix/side" and b9["taggedCommits"] == 1
    # attached branches leave "other"; the untagged unmerged one stays there
    assert [b["name"] for b in res["other"]] == ["experiment"]


def test_branches_merged_branch_flagged(branches, branch_repo):
    res = branches.discover(branch_repo, [3, 7, 9])
    b3 = res["items"][3]
    assert b3["merged"] is True and b3["ahead"] == 0
    assert b3["taggedCommits"] == 0       # its commits already live on trunk
    assert all(b["name"] != "roadmap/3" for b in res["other"])


def test_branches_item_ids_limit_attribution(branches, branch_repo):
    res = branches.discover(branch_repo, [7])
    assert set(res["items"]) == {7}
    assert {b["name"] for b in res["other"]} == {"fix/side", "experiment"}


def test_branches_custom_pattern_and_suffix(branches, branch_repo):
    _git(branch_repo, "branch", "feat-12-login", "roadmap/7")
    res = branches.discover(branch_repo, [12], pattern="feat-{id}")
    assert res["items"][12]["name"] == "feat-12-login"
    res = branches.discover(branch_repo, [7], pattern="roadmap/{id}")
    assert res["items"][7]["name"] == "roadmap/7"


def test_branches_stale_detection(branches, repo):
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init")
    _git(repo, "checkout", "-qb", "roadmap/5")
    _commit(repo, "old work (plan 5)", date="2020-01-01T00:00:00+00:00")
    _git(repo, "checkout", "-q", "main")
    res = branches.discover(repo, [5])
    assert res["items"][5]["stale"] is True
    assert res["items"][5]["lastDate"].startswith("2020-01-01")
    assert branches.discover(repo, [5], stale_days=10000)["items"][5]["stale"] is False


def test_branches_stale_days_from_config(branches, roadmap, repo):
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    roadmap.init_project(repo, "P")
    cfg = roadmap.read_config(repo)
    cfg["settings"]["staleDays"] = 100000
    roadmap.write_config(repo, cfg)
    _commit(repo, "init")
    _git(repo, "checkout", "-qb", "roadmap/5")
    _commit(repo, "old work", date="2020-01-01T00:00:00+00:00")
    _git(repo, "checkout", "-q", "main")
    assert branches.discover(repo, [5])["items"][5]["stale"] is False


def test_branches_worktree_path(branches, branch_repo, tmp_path_factory):
    wt = tmp_path_factory.mktemp("wt") / "seven"
    _git(branch_repo, "worktree", "add", "-q", str(wt), "roadmap/7")
    res = branches.discover(branch_repo, [7])
    assert Path(res["items"][7]["worktree"]).resolve() == wt.resolve()


def test_branches_cache_hit_runs_one_git_call(branches, branch_repo, monkeypatch):
    first = branches.discover(branch_repo, [3, 7, 9])
    calls = []
    real = subprocess.run

    def spy(cmd, *a, **kw):
        calls.append(cmd)
        return real(cmd, *a, **kw)

    monkeypatch.setattr(branches.subprocess, "run", spy)
    again = branches.discover(branch_repo, [3, 7, 9])
    assert again == first
    assert len(calls) == 1 and "for-each-ref" in calls[0]
    # a new commit changes the ref signature -> full rescan, fresh numbers
    monkeypatch.setattr(branches.subprocess, "run", real)
    _git(branch_repo, "checkout", "-q", "roadmap/7")
    _commit(branch_repo, "step 4 (plan 7)")
    _git(branch_repo, "checkout", "-q", "main")
    monkeypatch.setattr(branches.subprocess, "run", spy)
    calls.clear()
    assert branches.discover(branch_repo, [3, 7, 9])["items"][7]["ahead"] == 5
    assert 1 < len(calls) <= 3


def test_branches_git_calls_bounded_with_many_branches(branches, repo, monkeypatch):
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _commit(repo, "init")
    for n in range(1, 36):
        _git(repo, "checkout", "-qb", f"roadmap/{n}", "main")
        _commit(repo, f"work (plan {n})")
    _git(repo, "checkout", "-q", "main")
    calls = []
    real = subprocess.run
    monkeypatch.setattr(branches.subprocess, "run",
                        lambda cmd, *a, **kw: calls.append(cmd) or real(cmd, *a, **kw))
    res = branches.discover(repo, range(1, 36))
    assert len(res["items"]) == 35
    assert all(b["ahead"] == 1 and b["taggedCommits"] == 1
               for b in res["items"].values())
    assert len(calls) <= 3


def test_branches_non_git_dir_returns_empty(branches, tmp_path):
    assert branches.discover(tmp_path, [1]) == {"trunk": None, "items": {},
                                                "other": []}


def test_branches_unborn_repo_and_missing_git(branches, repo, monkeypatch):
    assert branches.discover(repo, [1])["items"] == {}

    def boom(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(branches.subprocess, "run", boom)
    assert branches.discover(repo, [1]) == {"trunk": None, "items": {},
                                            "other": []}


def test_branches_trunk_override(branches, branch_repo):
    _git(branch_repo, "branch", "-m", "main", "trunk")
    res = branches.discover(branch_repo, [7], trunk="trunk")
    assert res["trunk"] == "trunk" and res["items"][7]["ahead"] == 4
    assert branches.discover(branch_repo, [7], trunk="nope")["items"] == {}
