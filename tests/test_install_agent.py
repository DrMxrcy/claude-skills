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


def test_model_wired_by_default(tmp_path):
    _run(tmp_path, "--project")
    data = json.loads((tmp_path / ".claude/settings.json").read_text())
    assert data["model"] == "opus"
    assert data["fallbackModel"] == ["sonnet", "haiku"]


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
