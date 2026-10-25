"""Coverage for scripts/validate_skills.py (the skills/ install-layout enforcer)."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "validate_skills.py"
SCHEMA = REPO / "schemas" / "skill.schema.json"


@pytest.fixture
def validator():
    spec = importlib.util.spec_from_file_location("validate_skills", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_repo(tmp_path):
    """A minimal but valid repo layout the tests can then break."""
    pkg = tmp_path / "skills" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text(
        "---\nname: demo\ndescription: >\n  Does a demo thing.\n---\n\n# Demo\n")
    (pkg / "README.md").write_text("# demo\n")
    (pkg / "VERSION").write_text("1.2.3\n")
    return tmp_path


def _run(root):
    return subprocess.run([sys.executable, str(SCRIPT), str(root)],
                          capture_output=True, text=True)


def test_current_repo_passes():
    res = _run(REPO)
    assert res.returncode == 0, res.stderr
    assert "ok" in res.stdout


def test_schema_is_valid_json_and_lists_required_files():
    schema = json.loads(SCHEMA.read_text())
    assert set(schema["required"]) >= {"SKILL.md", "README.md", "VERSION"}


def test_fixture_repo_passes(fake_repo, validator):
    assert validator.validate(fake_repo) == []


@pytest.mark.parametrize("missing", ["SKILL.md", "README.md", "VERSION"])
def test_missing_required_file_fails_with_named_violation(fake_repo, missing):
    (fake_repo / "skills" / "demo" / missing).unlink()
    res = _run(fake_repo)
    assert res.returncode == 1
    assert f"skills/demo: missing required file {missing}" in res.stderr


def test_bad_version_fails_with_named_violation(fake_repo):
    (fake_repo / "skills" / "demo" / "VERSION").write_text("v1.2\n")
    res = _run(fake_repo)
    assert res.returncode == 1
    assert "skills/demo: VERSION 'v1.2' is not semver" in res.stderr


def test_frontmatter_name_must_match_directory(fake_repo, validator):
    (fake_repo / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: other\ndescription: x\n---\n")
    assert any("does not match directory name" in v
               for v in validator.validate(fake_repo))


def test_missing_frontmatter_and_description_are_reported(fake_repo, validator):
    skill = fake_repo / "skills" / "demo" / "SKILL.md"
    skill.write_text("# no frontmatter\n")
    assert any("no YAML frontmatter" in v for v in validator.validate(fake_repo))
    skill.write_text("---\nname: demo\n---\n")
    assert any("missing 'description'" in v for v in validator.validate(fake_repo))


def test_non_md_slash_command_is_reported(fake_repo, validator):
    commands = fake_repo / "commands" / "demo"
    commands.mkdir(parents=True)
    (commands / "status.md").write_text("ok\n")
    (commands / "status.txt").write_text("nope\n")
    violations = validator.validate(fake_repo)
    assert violations == ["commands/demo/status.txt: slash commands must be .md"]


def test_dotfiles_under_skills_are_not_treated_as_packages(fake_repo, validator):
    (fake_repo / "skills" / ".DS_Store").write_bytes(b"\x00")
    assert validator.validate(fake_repo) == []


def test_multiline_block_scalar_description_is_parsed(validator):
    meta = validator.parse_frontmatter(
        "---\nname: demo\ndescription: >\n  line one\n  line two\nargument-hint: x\n---\n")
    assert meta["description"] == "line one line two"
    assert meta["argument-hint"] == "x"


def test_empty_skills_dir_fails(tmp_path, validator):
    (tmp_path / "skills").mkdir()
    assert validator.validate(tmp_path) == ["skills/: no skill packages found"]


def test_real_skill_copy_still_validates(tmp_path):
    """Guards against the validator only ever seeing synthetic fixtures."""
    dest = tmp_path / "skills" / "roadmap"
    shutil.copytree(REPO / "skills" / "roadmap", dest)
    assert _run(tmp_path).returncode == 0
