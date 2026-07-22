"""Coverage for the Codex plugin package (codex-plugin/) and its build script."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "codex-plugin"
PLUGIN = PKG / "plugins" / "roadmap"
BUILD = REPO / "scripts" / "build-codex-plugin.sh"


def _build():
    return subprocess.run(["bash", str(BUILD)], cwd=REPO, capture_output=True, text=True)


def test_build_script_runs_and_bundles_skill():
    res = _build()
    assert res.returncode == 0, res.stderr
    assert (PLUGIN / "skills" / "roadmap" / "SKILL.md").exists()


def test_plugin_manifest_valid_and_version_synced():
    _build()
    data = json.loads((PLUGIN / "plugin.json").read_text())
    assert data["name"] == "roadmap"
    assert data["skills"] == "./skills/"        # bundled skill dir
    assert data["hooks"] == "./hooks.json"
    version = (REPO / "skills" / "roadmap" / "VERSION").read_text().strip()
    assert data["version"] == version           # stamped from VERSION, no drift


def test_hooks_json_uses_plugin_root_and_both_events():
    data = json.loads((PLUGIN / "hooks.json").read_text())
    hooks = data["hooks"]
    stop = json.dumps(hooks["Stop"])
    start = json.dumps(hooks["SessionStart"])
    # Paths resolve wherever Codex installs the plugin.
    assert "CLAUDE_PLUGIN_ROOT" in stop and "roadmap-sync.sh" in stop
    assert "CLAUDE_PLUGIN_ROOT" in start and "roadmap-orient.sh" in start


def test_marketplace_references_local_plugin():
    # Codex discovers the marketplace manifest at <root>/.agents/plugins/marketplace.json
    # (a root-level marketplace.json is not a supported discovery location).
    data = json.loads((PKG / ".agents/plugins/marketplace.json").read_text())
    entry = next(p for p in data["plugins"] if p["name"] == "roadmap")
    # Source path is relative to the marketplace ROOT (codex-plugin/), not the manifest dir.
    assert entry["source"] == {"source": "local", "path": "./plugins/roadmap"}
    assert entry["policy"]["installation"] == "AVAILABLE"
    assert entry["category"]                      # required for display
