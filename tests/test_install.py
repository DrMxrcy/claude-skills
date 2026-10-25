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
    res = _run(tmp_path, "--project", "--no-hook", "--no-orient")
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


def test_install_global_adds_claude_roadmap_cli(tmp_path):
    env = {**os.environ, "PYTHON": "python3", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global", "--only=roadmap"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    shim = tmp_path / ".local/bin/claude-roadmap"
    assert shim.exists(), res.stdout
    body = shim.read_text()
    assert "roadmap/scripts/roadmap.py" in body
    assert os.access(shim, os.X_OK)


def test_install_project_skips_cli_by_default(tmp_path):
    env = {**os.environ, "PYTHON": "python3", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--project"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert not (tmp_path / ".local/bin/claude-roadmap").exists()


def test_install_no_cli_flag_suppresses_shim(tmp_path):
    env = {**os.environ, "PYTHON": "python3", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global", "--only=roadmap",
                          "--no-cli"], cwd=tmp_path, env=env,
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert not (tmp_path / ".local/bin/claude-roadmap").exists()


def test_install_global_uses_home(tmp_path):
    env = {**os.environ, "PYTHON": "python3.11", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()


def test_install_copies_slash_commands(tmp_path):
    _run(tmp_path, "--project")
    flat = tmp_path / ".claude/commands"
    assert (flat / "roadmap-init.md").exists()
    assert (flat / "roadmap-next.md").exists()
    assert (flat / "roadmap-build.md").exists()
    assert (flat / "roadmap-status.md").exists()
    # One layout only: the nested Claude directory is no longer written.
    assert not (tmp_path / ".claude/commands/roadmap").exists()


def test_install_no_commands_flag(tmp_path):
    _run(tmp_path, "--project", "--no-commands")
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / ".claude/commands").exists()


def test_install_ships_all_commands(tmp_path):
    _run(tmp_path, "--project")
    src = {p.name for p in (REPO / "commands").glob("roadmap-*.md")}
    flat = {p.name for p in (tmp_path / ".claude/commands").glob("roadmap-*.md")}
    assert src and src == flat          # every command in the repo gets installed


def test_install_grok_project_copies_skill_and_wires_native_hook(tmp_path):
    res = _run(tmp_path, "--project", "--grok")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".grok/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".grok/skills/roadmap/scripts/roadmap.py").exists()
    assert not (tmp_path / ".claude").exists()
    data = json.loads((tmp_path / ".grok/hooks/roadmap-sync.json").read_text())
    cmds = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
    assert any("roadmap-sync.sh" in c for c in cmds)
    orient = json.loads((tmp_path / ".grok/hooks/roadmap-orient.json").read_text())
    ocmds = [h["command"] for e in orient["hooks"]["SessionStart"] for h in e["hooks"]]
    assert any("roadmap-orient.sh" in c for c in ocmds)


def test_install_grok_no_hook_flag(tmp_path):
    _run(tmp_path, "--project", "--grok", "--no-hook", "--no-orient")
    assert (tmp_path / ".grok/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / ".grok/hooks").exists()


def test_install_claude_wires_session_start_orient(tmp_path):
    _run(tmp_path, "--project")
    data = json.loads((tmp_path / ".claude/settings.json").read_text())
    start = data["hooks"]["SessionStart"]
    cmds = [h["command"] for e in start for h in e["hooks"]]
    assert any("roadmap-orient.sh" in c for c in cmds)


def test_install_grok_flat_command_files(tmp_path):
    # Grok only discovers flat commands/*.md (not nested ns/cmd.md → /ns:cmd).
    # Installer ships roadmap-<cmd>.md → /roadmap-<cmd> (e.g. /roadmap-next).
    _run(tmp_path, "--project", "--grok")
    cmds = tmp_path / ".grok/commands"
    assert (cmds / "roadmap-init.md").exists()
    assert (cmds / "roadmap-next.md").exists()
    assert (cmds / "roadmap-build.md").exists()
    assert (cmds / "roadmap-status.md").exists()
    # Nested Claude layout is intentionally omitted on pure Grok installs
    assert not (cmds / "roadmap").exists()
    src = {p.stem for p in (REPO / "commands").glob("roadmap-*.md")}
    flat = {p.stem for p in cmds.glob("roadmap-*.md")}
    assert src and src == flat


def test_install_grok_writes_claude_md_rules(tmp_path):
    # Grok Build reads CLAUDE.md + AGENTS.md; both get the dual-name rules block.
    _run(tmp_path, "--project", "--grok")
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (tmp_path / name).read_text()
        assert "roadmap:rules:start" in text
        assert "/roadmap-build" in text
        assert "/roadmap:build" not in text
        assert "All agents use the hyphen form" in text


def test_install_grok_global_uses_home(tmp_path):
    env = {**os.environ, "PYTHON": "python3.11", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global", "--grok"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".grok/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".grok/hooks/roadmap-sync.json").exists()


def test_skill_resolver_finds_grok_install(tmp_path):
    # The $RM resolver documented in SKILL.md must locate the CLI in a
    # pure-Grok install (no .claude anywhere, HOME empty).
    _run(tmp_path, "--project", "--grok")
    skill = (REPO / "skills/roadmap/SKILL.md").read_text()
    resolver = next(l for l in skill.splitlines() if l.startswith("for d in .claude"))
    home = tmp_path / "empty-home"
    home.mkdir()
    out = subprocess.run(["bash", "-c", resolver + '; echo "$RM"'],
                         cwd=tmp_path, env={**os.environ, "HOME": str(home)},
                         capture_output=True, text=True)
    assert out.stdout.strip() == ".grok/skills/roadmap/scripts/roadmap.py"


def test_install_writes_claude_md_rules(tmp_path):
    res = _run(tmp_path, "--project")
    assert res.returncode == 0, res.stderr
    cm = (tmp_path / "CLAUDE.md").read_text()
    assert "roadmap:rules:start" in cm
    assert "One item at a time" in cm
    assert "Quality-first build" in cm
    assert "Micro-commit" in cm
    assert "Orient first" in cm
    assert "/roadmap-build" in cm and "All agents use the hyphen form" in cm
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "roadmap:rules:start" in agents
    assert "high-quality" in agents
    assert "references/quality-build.md" in agents      # long form is pointed at, not inlined


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


def test_install_both_agents(tmp_path):
    res = _run(tmp_path, "--project", "--both", "--no-hook", "--no-orient", "--no-claude-md")
    assert res.returncode == 0, res.stderr + res.stdout
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".grok/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".claude/commands/roadmap-handoff.md").exists()
    assert (tmp_path / ".grok/commands/roadmap-handoff.md").exists()


def test_install_agy_project(tmp_path):
    res = _run(tmp_path, "--project", "--agy")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".agents/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".agents/skills/agent/SKILL.md").exists()
    assert (tmp_path / ".agents/commands/roadmap-status.md").exists()
    assert (tmp_path / ".agents/agents/executor.md").exists()
    assert (tmp_path / ".agents/hooks.json").exists()
    hooks_data = json.loads((tmp_path / ".agents/hooks.json").read_text())
    assert "roadmap-sync" in hooks_data
    assert "roadmap-orient" in hooks_data
    assert (tmp_path / "AGENTS.md").exists()
    assert "roadmap:rules:start" in (tmp_path / "AGENTS.md").read_text()


def test_install_agy_global_uses_gemini_config(tmp_path):
    env = {**os.environ, "PYTHON": "python3.11", "HOME": str(tmp_path)}
    res = subprocess.run(["bash", str(INSTALL), "--global", "--agy", "--only=roadmap"],
                         cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".gemini/config/skills/roadmap/SKILL.md").exists()
    assert (tmp_path / ".gemini/config/hooks.json").exists()
    assert (tmp_path / ".gemini/config/AGENTS.md").exists()



def test_claude_roadmap_shim_resolution_and_home_default(tmp_path):
    """Plan 48: the shim prefers a project's own skill copy, then the installed
    one; a bare `claude-roadmap` outside every roadmap project runs `serve --all`."""
    fake_py = tmp_path / "fakepy"
    fake_py.write_text('#!/usr/bin/env bash\necho "$1|${*:2}"\n')
    fake_py.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "PYTHON": str(fake_py), "HOME": str(home)}
    res = subprocess.run(["bash", str(INSTALL), "--global", "--only=roadmap"],
                         cwd=home, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    shim = home / ".local/bin/claude-roadmap"
    installed = home / ".claude/skills/roadmap/scripts/roadmap.py"
    (home / ".roadmap").mkdir()          # the registry home is not a project
    plain = home / "work" / "plain"
    plain.mkdir(parents=True)
    proj = home / "work" / "proj"
    (proj / ".roadmap").mkdir(parents=True)
    (proj / ".roadmap/config.json").write_text("{}")
    (proj / "src").mkdir()
    local = proj / ".claude/skills/roadmap/scripts/roadmap.py"
    local.parent.mkdir(parents=True)
    local.write_text("")

    def run(cwd, *args):
        r = subprocess.run([str(shim), *args], cwd=cwd, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    assert run(plain) == f"{installed}|serve --all"
    assert run(plain, "status") == f"{installed}|status"
    assert run(proj / "src") == f"{local}|"              # inside a project: as typed
    assert run(proj / "src", "serve") == f"{local}|serve"
