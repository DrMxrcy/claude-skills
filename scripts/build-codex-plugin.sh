#!/usr/bin/env bash
# build-codex-plugin.sh — assemble the Codex plugin package under codex-plugin/.
#
# The roadmap skill lives at skills/roadmap (single source of truth). This script
# copies it into the plugin's bundled skills/ dir and stamps plugin.json's version
# from skills/roadmap/VERSION, so the committed manifest never drifts from the skill.
#
# After building, install into Codex CLI:
#   codex plugin marketplace add ./codex-plugin        # register the local marketplace
#   codex plugin add roadmap@claude-skills             # install the plugin
# or open a Codex session and run /plugins.
#
# Usage: scripts/build-codex-plugin.sh
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pkg="$repo/codex-plugin/plugins/roadmap"
src="$repo/skills/roadmap"

[ -f "$src/SKILL.md" ] || { echo "roadmap skill not found at $src" >&2; exit 1; }
[ -f "$pkg/plugin.json" ] || { echo "plugin manifest not found at $pkg/plugin.json" >&2; exit 1; }

PYTHON="${PYTHON:-python3}"
version="$(cat "$src/VERSION")"

# Bundle the skill (fresh copy each build).
dest="$pkg/skills/roadmap"
rm -rf "$dest"
mkdir -p "$pkg/skills"
cp -R "$src" "$dest"
echo "Bundled skill: skills/roadmap -> codex-plugin/plugins/roadmap/skills/roadmap (v$version)"

# Stamp the manifest version from the skill's VERSION file.
"$PYTHON" - "$pkg/plugin.json" "$version" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
if data.get("version") != version:
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Stamped plugin.json version -> {version}")
else:
    print(f"plugin.json version already {version}")
PY

echo ""
echo "Built Codex plugin. Install with:"
echo "  codex plugin marketplace add $repo/codex-plugin"
echo "  codex plugin add roadmap@claude-skills"
