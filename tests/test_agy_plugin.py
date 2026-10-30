"""Coverage for the Antigravity (agy) plugin packages (agy-plugin/) and build script."""
import re
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "agy-plugin"
ROADMAP_PLUGIN = PKG / "plugins" / "roadmap"
AGENT_PLUGIN = PKG / "plugins" / "agent"
BUILD = REPO / "scripts" / "build-agy-plugin.sh"


def _build():
    return subprocess.run(["bash", str(BUILD)], cwd=REPO, capture_output=True, text=True)


def test_build_script_runs_and_bundles_roadmap_and_agent():
    res = _build()
    assert res.returncode == 0, res.stderr

    # Roadmap bundle
    assert (ROADMAP_PLUGIN / "skills" / "roadmap" / "SKILL.md").exists()
    assert (ROADMAP_PLUGIN / "commands" / "roadmap-status.md").exists()
    assert (ROADMAP_PLUGIN / "commands" / "roadmap-next.md").exists()
    assert (ROADMAP_PLUGIN / "commands" / "roadmap-build.md").exists()
    assert (ROADMAP_PLUGIN / "rules" / "AGENTS.md").exists()
    roadmap_rules = (ROADMAP_PLUGIN / "rules" / "AGENTS.md").read_text(encoding="utf-8")
    assert "Roadmap tracking" in roadmap_rules
    assert "Orient first:" in roadmap_rules

    # Agent bundle
    assert (AGENT_PLUGIN / "skills" / "agent" / "SKILL.md").exists()
    assert not (AGENT_PLUGIN / "skills" / "agent" / "evals").exists()   # dev-only
    assert (AGENT_PLUGIN / "agents" / "executor.md").exists()
    assert (AGENT_PLUGIN / "agents" / "verifier.md").exists()
    assert (AGENT_PLUGIN / "agents" / "scout.md").exists()
    assert (AGENT_PLUGIN / "rules" / "AGENTS.md").exists()


def test_plugin_manifests_valid_and_versions_synced():
    _build()

    # Roadmap manifest
    roadmap_data = json.loads((ROADMAP_PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert roadmap_data["name"] == "roadmap"
    assert roadmap_data["skills"] == "./skills/"
    assert roadmap_data["hooks"] == "./hooks.json"
    assert roadmap_data["commands"] == "./commands/"
    assert roadmap_data["rules"] == "./rules/"
    roadmap_version = (REPO / "skills" / "roadmap" / "VERSION").read_text(encoding="utf-8").strip()
    assert roadmap_data["version"] == roadmap_version

    # Agent manifest
    agent_data = json.loads((AGENT_PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    assert agent_data["name"] == "agent"
    assert agent_data["skills"] == "./skills/"
    assert agent_data["agents"] == "./agents/"
    assert agent_data["rules"] == "./rules/"
    agent_version = (REPO / "skills" / "agent" / "VERSION").read_text(encoding="utf-8").strip()
    assert agent_data["version"] == agent_version


def test_agy_hooks_json_format():
    _build()
    data = json.loads((ROADMAP_PLUGIN / "hooks.json").read_text(encoding="utf-8"))

    # Stop hook in AGY format: named hook mapping to Stop event with command
    assert "roadmap-sync" in data
    stop_handlers = data["roadmap-sync"]["Stop"]
    assert isinstance(stop_handlers, list)
    assert any("roadmap-sync.sh" in h["command"] for h in stop_handlers)

    # PreInvocation orient hook in AGY format
    assert "roadmap-orient" in data
    orient_handlers = data["roadmap-orient"]["PreInvocation"]
    assert isinstance(orient_handlers, list)
    assert any("roadmap-orient.sh" in h["command"] for h in orient_handlers)


def test_hooks_scripts_handle_agy_and_legacy_contracts():
    _build()
    sync_script = REPO / "skills" / "roadmap" / "hooks" / "roadmap-sync.sh"
    orient_script = REPO / "skills" / "roadmap" / "hooks" / "roadmap-orient.sh"

    env = os.environ.copy()
    env["ANTIGRAVITY_AGENT"] = "1"

    # Stop hook under AGY: expects JSON stdout ({})
    payload = json.dumps({"workspacePaths": [str(REPO)]})
    res_sync = subprocess.run(
        ["bash", str(sync_script)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(ROADMAP_PLUGIN),
    )
    assert res_sync.returncode == 0, res_sync.stderr
    sync_out = json.loads(res_sync.stdout.strip())
    assert isinstance(sync_out, dict)

    # PreInvocation hook under AGY: invocation 1 injects ephemeral orientation
    payload_inv1 = json.dumps({"invocationNum": 1, "workspacePaths": [str(REPO)]})
    res_orient1 = subprocess.run(
        ["bash", str(orient_script)],
        input=payload_inv1,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(ROADMAP_PLUGIN),
    )
    assert res_orient1.returncode == 0, res_orient1.stderr
    orient1_out = json.loads(res_orient1.stdout.strip())
    assert "injectSteps" in orient1_out
    assert len(orient1_out["injectSteps"]) > 0
    assert "ephemeralMessage" in orient1_out["injectSteps"][0]
    assert "Roadmap:" in orient1_out["injectSteps"][0]["ephemeralMessage"]

    # PreInvocation hook under AGY: invocation 2 returns empty steps
    payload_inv2 = json.dumps({"invocationNum": 2, "workspacePaths": [str(REPO)]})
    res_orient2 = subprocess.run(
        ["bash", str(orient_script)],
        input=payload_inv2,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(ROADMAP_PLUGIN),
    )
    assert res_orient2.returncode == 0, res_orient2.stderr
    orient2_out = json.loads(res_orient2.stdout.strip())
    assert orient2_out == {"injectSteps": []}


def test_marketplace_references_local_plugins():
    manifest_path = PKG / ".agents" / "plugins" / "marketplace.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    roadmap_entry = next(p for p in data["plugins"] if p["name"] == "roadmap")
    assert roadmap_entry["source"] == {"source": "local", "path": "./plugins/roadmap"}
    assert roadmap_entry["policy"]["installation"] == "AVAILABLE"

    agent_entry = next(p for p in data["plugins"] if p["name"] == "agent")
    assert agent_entry["source"] == {"source": "local", "path": "./plugins/agent"}
    assert agent_entry["policy"]["installation"] == "AVAILABLE"


def _validated(stdout):
    # agy <= 1.4.5 printed "[ok]"; 1.4.6 prints "Validation passed" (warnings are
    # tracked separately, not failed here)
    return "[ok]" in stdout or "Validation passed" in stdout


def test_agy_cli_plugin_validate():
    agy_bin = shutil.which("agy")
    if not agy_bin:
        return

    _build()

    # Validate roadmap plugin
    res_rm = subprocess.run([agy_bin, "plugin", "validate", str(ROADMAP_PLUGIN)], capture_output=True, text=True)
    assert res_rm.returncode == 0, res_rm.stderr
    assert _validated(res_rm.stdout), res_rm.stdout

    # Validate agent plugin
    res_ag = subprocess.run([agy_bin, "plugin", "validate", str(AGENT_PLUGIN)], capture_output=True, text=True)
    assert res_ag.returncode == 0, res_ag.stderr
    assert _validated(res_ag.stdout), res_ag.stdout


def test_agent_fleet_frontmatter_is_agy_shaped():
    # agy 1.4.6 skips an agent whose `tools` is a comma string or whose `model` is not
    # an agy tier; the Claude source files keep their own format.
    assert _build().returncode == 0
    agents = sorted((AGENT_PLUGIN / "agents").glob("*.md"))
    assert agents
    for f in agents:
        fm = f.read_text().split("---\n")[1]
        model = re.search(r"^model: *(\S+)", fm, re.M)
        assert model and model.group(1) in {"pro", "flash", "flash_lite", "inherit"}, f.name
        assert not re.search(r"^tools: *\S", fm, re.M), f"{f.name}: tools must be a YAML list"
    src = (REPO / "skills/agent/.claude/agents/executor.md").read_text()
    assert "model: opus" in src
