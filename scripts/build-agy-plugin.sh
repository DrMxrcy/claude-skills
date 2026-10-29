#!/usr/bin/env bash
# build-agy-plugin.sh — assemble the Antigravity (agy) plugin packages under agy-plugin/.
#
# Packages both roadmap and agent as native Antigravity plugins:
# - agy-plugin/plugins/roadmap (skill + commands + hooks + rules)
# - agy-plugin/plugins/agent   (skill + subagents + rules)
#
# Usage: scripts/build-agy-plugin.sh
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pkg="$repo/agy-plugin"
roadmap_pkg="$pkg/plugins/roadmap"
agent_pkg="$pkg/plugins/agent"

roadmap_src="$repo/skills/roadmap"
agent_src="$repo/skills/agent"
commands_src="$repo/commands"

[ -f "$roadmap_src/SKILL.md" ] || { echo "roadmap skill not found at $roadmap_src" >&2; exit 1; }
[ -f "$agent_src/SKILL.md" ] || { echo "agent skill not found at $agent_src" >&2; exit 1; }

PYTHON="${PYTHON:-python3}"
roadmap_version="$(cat "$roadmap_src/VERSION")"
agent_version="$(cat "$agent_src/VERSION")"

echo "=== Building Antigravity (agy) plugins ==="

# --- 1. Roadmap Plugin ---
mkdir -p "$roadmap_pkg/skills" "$roadmap_pkg/commands" "$roadmap_pkg/rules"

# Bundle skill
rm -rf "$roadmap_pkg/skills/roadmap"
cp -R "$roadmap_src" "$roadmap_pkg/skills/roadmap"
echo "Bundled skill: skills/roadmap -> $roadmap_pkg/skills/roadmap (v$roadmap_version)"

# Copy flat slash commands
rm -f "$roadmap_pkg/commands"/*.md
for cmd_file in "$commands_src"/roadmap-*.md; do
  [ -f "$cmd_file" ] || continue
  cp "$cmd_file" "$roadmap_pkg/commands/$(basename "$cmd_file")"
done
echo "Copied commands -> $roadmap_pkg/commands/ (flat /roadmap-*)"

# Extract canonical roadmap rules block for rules/AGENTS.md
"$PYTHON" - "$repo" "$roadmap_pkg/rules/AGENTS.md" <<'PY'
import sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "skills/roadmap/scripts"))
try:
    from rmlib.core import RULES_BLOCK
    out_file = Path(sys.argv[2])
    out_file.write_text(RULES_BLOCK.strip() + "\n", encoding="utf-8")
    print(f"Generated rules -> {out_file}")
except Exception as e:
    print(f"Warning: could not import RULES_BLOCK: {e}", file=sys.stderr)
PY

# Stamp roadmap plugin.json version
"$PYTHON" - "$roadmap_pkg/plugin.json" "$roadmap_version" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
if data.get("version") != version:
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Stamped roadmap plugin.json version -> {version}")
else:
    print(f"roadmap plugin.json version already {version}")
PY

# --- 2. Agent Plugin ---
mkdir -p "$agent_pkg/skills" "$agent_pkg/agents" "$agent_pkg/rules"

# Bundle skill
rm -rf "$agent_pkg/skills/agent"
cp -R "$agent_src" "$agent_pkg/skills/agent"
echo "Bundled skill: skills/agent -> $agent_pkg/skills/agent (v$agent_version)"

# Copy subagents fleet
rm -f "$agent_pkg/agents"/*.md
if [ -d "$agent_src/.claude/agents" ]; then
  # agy's agent frontmatter wants `tools` as a YAML list and `model` as an agy tier
  # (pro | flash | flash_lite | inherit), so convert the Claude-format files on copy.
  "$PYTHON" - "$agent_src/.claude/agents" "$agent_pkg/agents" <<'PY'
import re, sys
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
TIERS = {"opus": "pro", "sonnet": "pro", "haiku": "flash"}
for f in sorted(src.glob("*.md")):
    text = f.read_text()
    m = re.match(r"---\n(.*?\n)---\n", text, re.S)
    if m:
        fm = re.sub(r"^model: *(\S+) *$",
                    lambda x: f"model: {TIERS.get(x.group(1), 'inherit')}", m.group(1), flags=re.M)
        fm = re.sub(r"^tools: *([^\n\[]+?) *$",
                    lambda x: "tools:\n" + "\n".join(f"  - {t.strip()}" for t in x.group(1).split(",") if t.strip()),
                    fm, flags=re.M)
        text = f"---\n{fm}---\n" + text[m.end():]
    (dest / f.name).write_text(text)
PY
  echo "Converted subagent fleet -> $agent_pkg/agents/ (agy tools list + model tiers)"
fi

# Copy orchestration rules
if [ -f "$agent_src/references/orchestration-policy.md" ]; then
  cp "$agent_src/references/orchestration-policy.md" "$agent_pkg/rules/AGENTS.md"
  echo "Copied orchestration policy -> $agent_pkg/rules/AGENTS.md"
fi

# Stamp agent plugin.json version
"$PYTHON" - "$agent_pkg/plugin.json" "$agent_version" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
if data.get("version") != version:
    data["version"] = version
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Stamped agent plugin.json version -> {version}")
else:
    print(f"agent plugin.json version already {version}")
PY

echo ""
echo "Built Antigravity plugins successfully."
echo "Install with:"
echo "  agy plugin install $roadmap_pkg"
echo "  agy plugin install $agent_pkg"
