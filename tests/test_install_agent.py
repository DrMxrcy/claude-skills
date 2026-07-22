"""Coverage for the cost-tiered agent orchestration fleet installed by install.sh."""
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"

FLEET = {"executor.md", "verifier.md", "security-executor.md",
         "mech-executor.md", "scout.md", "Explore.md"}
START = "<!-- agent:orchestration:start -->"


def _run(tmp_path, *args):
    env = {**os.environ, "PYTHON": "python3.11"}
    return subprocess.run(["bash", str(INSTALL), *args],
                          cwd=tmp_path, env=env, capture_output=True, text=True)


def test_agent_fleet_installed_by_default(tmp_path):
    res = _run(tmp_path, "--project")
    assert res.returncode == 0, res.stderr
    agents = {p.name for p in (tmp_path / ".claude/agents").glob("*.md")}
    assert FLEET <= agents


def test_agent_policy_merged_into_instruction_files(tmp_path):
    _run(tmp_path, "--project")
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (tmp_path / name).read_text()
        assert START in text
        assert "Delegation tiers" in text
        assert "security-executor" in text
        assert "roadmap:rules:start" in text     # coexists with roadmap rules block


def test_agent_policy_is_idempotent_and_preserves_content(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# House rules\n\n- keep this line\n")
    _run(tmp_path, "--project")
    _run(tmp_path, "--project")
    cm = (tmp_path / "CLAUDE.md").read_text()
    assert cm.count(START) == 1                  # merged once, not duplicated
    assert "keep this line" in cm                # existing content preserved


def test_agents_carry_no_project_specifics(tmp_path):
    # The whole point of decoupling: shipped agents name no stack/framework/product.
    _run(tmp_path, "--project")
    blob = "\n".join(p.read_text().lower()
                     for p in (tmp_path / ".claude/agents").glob("*.md"))
    for token in ("parkboxd", "convex", "clerk"):
        assert token not in blob


def test_no_agent_flag_skips_fleet_and_policy(tmp_path):
    _run(tmp_path, "--project", "--no-agent")
    assert not (tmp_path / ".claude/agents").exists()
    cm = tmp_path / "CLAUDE.md"
    assert not cm.exists() or START not in cm.read_text()


def test_no_claude_md_flag_skips_policy_but_keeps_fleet(tmp_path):
    _run(tmp_path, "--project", "--no-claude-md")
    agents = {p.name for p in (tmp_path / ".claude/agents").glob("*.md")}
    assert FLEET <= agents                        # fleet still installs
    assert not (tmp_path / "CLAUDE.md").exists()   # but no policy written


def test_grok_install_skips_fleet(tmp_path):
    _run(tmp_path, "--project", "--grok")
    assert not (tmp_path / ".grok/agents").exists()
    cm = (tmp_path / "CLAUDE.md").read_text()      # grok writes roadmap rules...
    assert START not in cm                          # ...but not the claude-only fleet policy


def test_codex_install_skips_fleet(tmp_path):
    _run(tmp_path, "--project", "--codex")
    assert not (tmp_path / ".codex/agents").exists()   # no claude-only fleet
    agents_md = (tmp_path / "AGENTS.md").read_text()    # codex reads AGENTS.md...
    assert "roadmap:rules:start" in agents_md           # ...roadmap rules land there...
    assert START not in agents_md                        # ...but not the fleet policy


def test_codex_wires_hooks_json(tmp_path):
    _run(tmp_path, "--project", "--codex")
    hooks_json = tmp_path / ".codex/hooks.json"          # codex config-folder root
    assert hooks_json.exists()
    data = json.loads(hooks_json.read_text())
    hooks = data.get("hooks", {})
    stop = json.dumps(hooks.get("Stop", []))             # PascalCase event keys
    start = json.dumps(hooks.get("SessionStart", []))
    assert "roadmap-sync.sh" in stop
    assert "roadmap-orient.sh" in start
    # no claude settings.json is created for a codex install
    assert not (tmp_path / ".codex/settings.json").exists()


def test_codex_installs_flat_prompts(tmp_path):
    _run(tmp_path, "--project", "--codex")
    prompts = tmp_path / ".codex/prompts"                # codex discovers /<name> here
    assert (prompts / "roadmap-next.md").exists()        # flat <ns>-<cmd> layout
    assert not (prompts / "roadmap").exists()            # codex ignores nested dirs
    assert not (tmp_path / ".codex/commands").exists()   # prompts, not commands


def test_model_wired_by_default(tmp_path):
    _run(tmp_path, "--project")
    data = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert data["model"] == "fable"
    assert data["fallbackModel"] == ["opus"]


def test_no_model_flag_leaves_model_unset(tmp_path):
    _run(tmp_path, "--project", "--no-model")
    data = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert "model" not in data                    # hooks still wired, no model key


def test_existing_model_is_never_overridden(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({"model": "fable"}))
    _run(tmp_path, "--project")
    data = json.loads((claude / "settings.json").read_text())
    assert data["model"] == "fable"


def test_only_agent_skips_all_roadmap_wiring(tmp_path):
    res = _run(tmp_path, "--project", "--only=agent")
    assert res.returncode == 0, res.stderr
    # agent skill + fleet + policy installed
    assert (tmp_path / ".claude/skills/agent/SKILL.md").exists()
    assert FLEET <= {p.name for p in (tmp_path / ".claude/agents").glob("*.md")}
    assert START in (tmp_path / "CLAUDE.md").read_text()
    # nothing roadmap: no skill copy, no commands, no roadmap hooks, no rules block
    assert not (tmp_path / ".claude/skills/roadmap").exists()
    assert not (tmp_path / ".claude/commands").exists()
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert "roadmap" not in json.dumps(settings.get("hooks", {}))
    assert "roadmap" not in (tmp_path / "CLAUDE.md").read_text().lower()


def test_only_roadmap_skips_fleet_and_policy(tmp_path):
    res = _run(tmp_path, "--project", "--only=roadmap")
    assert res.returncode == 0, res.stderr
    assert (tmp_path / ".claude/skills/roadmap/SKILL.md").exists()
    assert not (tmp_path / ".claude/skills/agent").exists()
    assert not (tmp_path / ".claude/agents").exists()
    assert START not in (tmp_path / "CLAUDE.md").read_text()


def test_agent_install_wires_caveman_level_hook(tmp_path):
    res = _run(tmp_path, "--project", "--only=agent")
    assert res.returncode == 0, res.stderr
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    blob = json.dumps(settings.get("hooks", {}).get("SessionStart", []))
    assert "caveman-level.sh" in blob
    hook = tmp_path / ".claude/skills/agent/hooks/caveman-level.sh"
    assert hook.exists() and os.access(hook, os.X_OK)


def test_caveman_hook_noops_without_plugin(tmp_path):
    _run(tmp_path, "--project", "--only=agent")
    hook = tmp_path / ".claude/skills/agent/hooks/caveman-level.sh"
    env = {**os.environ, "HOME": str(tmp_path / "fakehome")}
    res = subprocess.run(["bash", str(hook)], env=env, capture_output=True, text=True)
    assert res.returncode == 0 and res.stdout.strip() == ""


def test_caveman_hook_sets_level_from_project_preference(tmp_path):
    _run(tmp_path, "--project", "--only=agent")
    hook = tmp_path / ".claude/skills/agent/hooks/caveman-level.sh"
    home = tmp_path / "fakehome"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/.caveman-active").write_text("full")
    (tmp_path / ".claude/caveman-level").write_text("ultra\n")
    env = {**os.environ, "HOME": str(home), "CLAUDE_PROJECT_DIR": str(tmp_path)}
    res = subprocess.run(["bash", str(hook)], env=env, cwd=tmp_path,
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert (home / ".claude/.caveman-active").read_text() == "ultra"
    assert "project preference" in res.stdout
    # invalid preference falls back to the decision prompt, flag untouched
    (tmp_path / ".claude/caveman-level").write_text("shouty\n")
    (home / ".claude/.caveman-active").write_text("full")
    res = subprocess.run(["bash", str(hook)], env=env, cwd=tmp_path,
                         capture_output=True, text=True)
    assert (home / ".claude/.caveman-active").read_text() == "full"
    assert "decide the level NOW" in res.stdout
