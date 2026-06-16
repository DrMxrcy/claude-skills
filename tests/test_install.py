import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"


def _run(tmp_path, *args):
    env = {**os.environ, "PYTHON": "python3.11"}
    return subprocess.run(["bash", str(INSTALL), *args],
                          cwd=tmp_path, env=env, capture_output=True, text=True)


def _stop_commands(settings_path):
    data = json.loads(settings_path.read_text())
    return [h["command"]
            for entry in data["hooks"]["Stop"]
            for h in entry["hooks"]]


def test_install_project_copies_skill_and_wires_hook(tmp_path):
    res = _run(tmp_path, "--project")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".claude/skills/roadmap/scripts/roadmap.py").exists()
    cmds = _stop_commands(tmp_path / ".claude/settings.json")
    assert any("roadmap-sync.sh" in c for c in cmds)


def test_install_hook_is_idempotent(tmp_path):
    _run(tmp_path, "--project")
    _run(tmp_path, "--project")
    cmds = _stop_commands(tmp_path / ".claude/settings.json")
    assert sum("roadmap-sync.sh" in c for c in cmds) == 1


def test_install_no_hook_leaves_settings_untouched(tmp_path):
    res = _run(tmp_path, "--project", "--no-hook")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / ".claude/settings.json").exists()


def test_install_preserves_existing_settings(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({"model": "opus", "hooks": {"Stop": []}}))
    _run(tmp_path, "--project")
    data = json.loads((claude / "settings.json").read_text())
    assert data["model"] == "opus"            # existing keys preserved
    assert any("roadmap-sync.sh" in h["command"]
               for e in data["hooks"]["Stop"] for h in e["hooks"])


def test_install_piped_without_local_repo(tmp_path):
    # Simulate `curl ... | bash`: the script arrives on stdin (no file on disk
    # next to a skills/ dir). SKILLS_SRC stands in for the downloaded tarball so
    # the test needs no network.
    env = {**os.environ, "PYTHON": "python3.11", "SKILLS_SRC": str(REPO / "skills")}
    script = INSTALL.read_text()
    res = subprocess.run(["bash", "-s", "--", "--project", "--no-hook"],
                         input=script, cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()


def test_install_global_uses_home(tmp_path):
    env = {**os.environ, "PYTHON": "python3.11", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()


def test_install_copies_slash_commands(tmp_path):
    _run(tmp_path, "--project")
    cmds = tmp_path / ".claude/commands/roadmap"
    assert (cmds / "init.md").exists()
    assert (cmds / "plan.md").exists()
    assert (cmds / "status.md").exists()


def test_install_no_commands_flag(tmp_path):
    _run(tmp_path, "--project", "--no-commands")
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / ".claude/commands").exists()


def test_install_writes_claude_md_rules(tmp_path):
    res = _run(tmp_path, "--project")
    assert res.returncode == 0, res.stderr
    cm = (tmp_path / "CLAUDE.md").read_text()
    assert "roadmap:rules:start" in cm
    assert "Work one checklist item at a time" in cm


def test_install_claude_md_is_idempotent(tmp_path):
    _run(tmp_path, "--project")
    _run(tmp_path, "--project")
    cm = (tmp_path / "CLAUDE.md").read_text()
    assert cm.count("roadmap:rules:start") == 1


def test_install_preserves_existing_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# My Project rules\n\n- keep this rule\n")
    _run(tmp_path, "--project")
    cm = (tmp_path / "CLAUDE.md").read_text()
    assert "keep this rule" in cm           # existing content preserved
    assert "roadmap:rules:start" in cm      # block appended


def test_install_no_claude_md_flag(tmp_path):
    _run(tmp_path, "--project", "--no-claude-md")
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()


def test_install_global_skips_claude_md(tmp_path):
    env = {**os.environ, "PYTHON": "python3.11", "HOME": str(tmp_path)}
    subprocess.run(["bash", str(INSTALL), "--global"],
                   cwd=tmp_path, env=env, check=True, capture_output=True, text=True)
    assert not (tmp_path / "CLAUDE.md").exists()
