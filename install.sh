#!/usr/bin/env bash
# install.sh — import the skills in this repo into a Claude Code skills directory
# and (optionally) wire the roadmap auto-sync Stop hook into settings.json, so
# there is nothing to copy or edit by hand.
#
# Run locally (cloned repo) OR straight from GitHub without cloning:
#   curl -fsSL https://raw.githubusercontent.com/<owner>/claude-skills/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/<owner>/claude-skills/main/install.sh | bash -s -- --global
#
# Usage:
#   ./install.sh                 # install into ./.claude/skills (this project) + hook
#   ./install.sh --global        # install into ~/.claude/skills (all projects) + hook
#   ./install.sh --link          # symlink instead of copy (good for development)
#   ./install.sh --no-hook       # do not touch settings.json
#   ./install.sh --init          # also run `roadmap init` in the current directory
#   ./install.sh -h | --help     # show this help
#
# Env overrides:
#   SKILLS_REPO   GitHub owner/repo to fetch in remote mode (default: DrMxrcy/claude-skills)
#   SKILLS_REF    branch/tag to fetch in remote mode (default: main)
#   SKILLS_SRC    path to a local skills/ dir (skips any download)
#   PYTHON        interpreter for the settings.json merge (default: python3)
set -euo pipefail

usage() {
  sed -n '2,30p' "$0" 2>/dev/null | sed 's/^#\{1,\} \{0,1\}//' || true
}

scope="project"
link=0
hook=1
do_init=0
for arg in "$@"; do
  case "$arg" in
    --global) scope="global" ;;
    --project) scope="project" ;;
    --link) link=1 ;;
    --no-hook) hook=0 ;;
    --init) do_init=1 ;;
    -h|--help)
      cat <<'EOF'
install.sh — import this repo's skills into a Claude Code skills directory and
wire the roadmap auto-sync Stop hook (no manual copying or settings edits).

  ./install.sh            install into ./.claude/skills (this project) + hook
  --global                install into ~/.claude/skills (all projects)
  --link                  symlink instead of copy (development)
  --no-hook               do not touch settings.json
  --init                  also run `roadmap init` in the current directory

Remote (no clone):
  curl -fsSL .../install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --global

Env: SKILLS_REPO, SKILLS_REF, SKILLS_SRC, PYTHON
EOF
      exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

PYTHON="${PYTHON:-python3}"
SLUG="${SKILLS_REPO:-DrMxrcy/claude-skills}"
REF="${SKILLS_REF:-main}"

# Locate the source skills/ directory: alongside this script (local clone),
# an explicit SKILLS_SRC, or download the repo tarball (remote / curl | bash).
script_path="${BASH_SOURCE[0]:-}"
if [ -n "$script_path" ] && [ -d "$(cd "$(dirname "$script_path")" 2>/dev/null && pwd)/skills" ]; then
  SRC_DIR="$(cd "$(dirname "$script_path")" && pwd)/skills"
elif [ -n "${SKILLS_SRC:-}" ]; then
  SRC_DIR="$SKILLS_SRC"
else
  command -v tar >/dev/null 2>&1 || { echo "tar is required for remote install" >&2; exit 1; }
  tmpdl="$(mktemp -d)"
  trap 'rm -rf "$tmpdl"' EXIT
  url="https://github.com/$SLUG/archive/refs/heads/$REF.tar.gz"
  echo "Downloading $SLUG@$REF ..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" | tar -xz -C "$tmpdl"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$url" | tar -xz -C "$tmpdl"
  else
    echo "Need curl or wget for remote install" >&2; exit 1
  fi
  SRC_DIR="$tmpdl/${SLUG##*/}-${REF##*/}/skills"
fi

[ -d "$SRC_DIR" ] || { echo "Could not locate a skills/ directory at $SRC_DIR" >&2; exit 1; }

if [ "$scope" = "global" ]; then
  base="$HOME/.claude"
else
  base="$PWD/.claude"
fi
skills_dest="$base/skills"
settings="$base/settings.json"

mkdir -p "$skills_dest"

installed=0
for skill_dir in "$SRC_DIR"/*/; do
  [ -f "${skill_dir}SKILL.md" ] || continue
  name="$(basename "$skill_dir")"
  target="$skills_dest/$name"
  rm -rf "$target"
  if [ "$link" = "1" ]; then
    ln -s "${skill_dir%/}" "$target"
    echo "Linked skill:    $name -> $target"
  else
    cp -R "${skill_dir%/}" "$target"
    echo "Installed skill: $name -> $target"
  fi
  installed=$((installed + 1))
done

if [ "$installed" -eq 0 ]; then
  echo "No skills found in $SRC_DIR" >&2
  exit 1
fi

# Wire the roadmap auto-sync Stop hook (idempotent) unless --no-hook.
if [ "$hook" = "1" ]; then
  hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
  if [ -f "$hook_path" ]; then
    "$PYTHON" - "$settings" "bash \"$hook_path\"" <<'PY'
import json, os, sys
settings_path, cmd = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(settings_path):
    with open(settings_path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {settings_path} is not valid JSON; left unchanged.", file=sys.stderr)
            sys.exit(0)

stop = data.setdefault("hooks", {}).setdefault("Stop", [])
present = any(h.get("command") == cmd
             for entry in stop for h in entry.get("hooks", []))
if present:
    print(f"Stop hook already configured in {settings_path}")
else:
    stop.append({"hooks": [{"type": "command", "command": cmd}]})
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wired roadmap Stop hook into {settings_path}")
PY
  fi
fi

if [ "$do_init" = "1" ]; then
  echo "Running roadmap init in $PWD ..."
  "$PYTHON" "$skills_dest/roadmap/scripts/roadmap.py" init
fi

echo ""
echo "Done. Installed $installed skill(s) into $skills_dest."
echo "Start a new Claude Code session to pick up the skill(s)."
