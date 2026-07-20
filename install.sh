#!/usr/bin/env bash
# install.sh — import this repo's skills + /roadmap:* slash commands into a Claude
# Code directory, wire the roadmap auto-sync Stop hook, and add roadmap rules to
# CLAUDE.md, so there is nothing to copy or edit by hand.
#
# Run locally (cloned repo) OR straight from GitHub without cloning:
#   curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/DrMxrcy/claude-skills/main/install.sh | bash -s -- --global
#
# Usage:
#   ./install.sh                 # ./.claude: skills + /roadmap:* commands + hook + CLAUDE.md
#   ./install.sh --global        # ~/.claude (all projects); skips CLAUDE.md
#   ./install.sh --grok          # target Grok Build: ./.grok (or ~/.grok with --global)
#   ./install.sh --both          # install Claude + Grok (same skill version; keeps coders in sync)
#   ./install.sh --link          # symlink instead of copy (good for development)
#   ./install.sh --no-hook       # do not wire the auto-sync Stop hook (sync + drift-check)
#   ./install.sh --no-orient     # do not wire the SessionStart orient hook
#   ./install.sh --no-commands   # do not install the /roadmap:* (Claude) / /roadmap-* (Grok) slash commands
#   ./install.sh --no-claude-md  # do not add roadmap rules to CLAUDE.md / AGENTS.md
#   ./install.sh --no-agent      # do not install the cost-tiered agent orchestration fleet (Claude)
#   ./install.sh --no-model      # do not set a default main-session model in settings.json
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
agent="claude"
both=0
link=0
hook=1
orient=1
do_init=0
commands=1
claude_md=1
agent_fleet=1
model_wire=1
cli=-1          # -1 = auto (on for --global); 0/1 = forced by --no-cli/--cli
only=""
pass_args=()
for arg in "$@"; do
  case "$arg" in
    --global) scope="global"; pass_args+=("$arg") ;;
    --project) scope="project"; pass_args+=("$arg") ;;
    --grok) agent="grok"; pass_args+=("$arg") ;;
    --claude) agent="claude"; pass_args+=("$arg") ;;
    --both|--all-agents) both=1 ;;
    --link) link=1; pass_args+=("$arg") ;;
    --no-hook) hook=0; pass_args+=("$arg") ;;
    --no-orient) orient=0; pass_args+=("$arg") ;;
    --no-commands) commands=0; pass_args+=("$arg") ;;
    --no-claude-md) claude_md=0; pass_args+=("$arg") ;;
    --no-agent) agent_fleet=0; pass_args+=("$arg") ;;
    --no-model) model_wire=0; pass_args+=("$arg") ;;
    --cli) cli=1; pass_args+=("$arg") ;;
    --no-cli) cli=0; pass_args+=("$arg") ;;
    --only=*) only="${arg#--only=}"; pass_args+=("$arg") ;;
    --init) do_init=1; pass_args+=("$arg") ;;
    -h|--help)
      cat <<'EOF'
install.sh — import this repo's skills + slash commands into Claude Code or Grok
Build, wire Stop (sync+drift) and SessionStart (orient) hooks, and add roadmap
rules to CLAUDE.md + AGENTS.md (no manual copying or settings edits).

  ./install.sh            install into ./.claude (this project)
  --global                install into ~/.claude (all projects); skips project rules
  --grok                  target Grok Build: ./.grok (or ~/.grok with --global),
                          native hooks JSON, flat /roadmap-* slash commands
  --both                  install Claude + Grok at the same skill version (recommended
                          when you switch between AI coders)
  --link                  symlink instead of copy (development)
  --no-hook               do not wire the Stop hook (sync + drift-check)
  --no-orient             do not wire the SessionStart orient hook
  --no-commands           do not install slash commands
  --no-claude-md          do not add roadmap rules to CLAUDE.md / AGENTS.md
  --no-agent              do not install the cost-tiered agent orchestration fleet (Claude)
  --no-model              do not set a default main-session model in settings.json
  --cli                   install a 'claude-roadmap' command on PATH (default with
                          --global) so you can run 'claude-roadmap serve' anywhere
  --no-cli                do not install the 'claude-roadmap' PATH command
  --only=<skill[,skill]>  install only these skills (agent, roadmap) and skip the
                          excluded skills' wiring — e.g. --only=agent when roadmap
                          is already installed globally
  --init                  also run `roadmap init` in the current directory

Remote (no clone):
  curl -fsSL .../install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --global --both

Env: SKILLS_REPO, SKILLS_REF, SKILLS_SRC, PYTHON
EOF
      exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

# --only=<skill[,skill]> installs just those skills and skips the wiring that belongs
# to the excluded ones (roadmap: hooks/commands/rules/init; agent: fleet). Use it when
# a skill is already installed at another scope (e.g. roadmap installed globally).
_want() {
  [ -z "$only" ] && return 0
  case ",$only," in *,"$1",*) return 0 ;; *) return 1 ;; esac
}
agent_hook=$hook
if ! _want roadmap; then hook=0; orient=0; do_init=0; fi

# --both: install Claude then Grok with the same flags (keeps multi-coder skill in sync).
if [ "$both" = "1" ]; then
  # Drop agent selectors from the recursive pass; force each target.
  both_args=()
  for a in "${pass_args[@]+"${pass_args[@]}"}"; do
    case "$a" in
      --grok|--claude|--both|--all-agents) ;;
      *) both_args+=("$a") ;;
    esac
  done
  echo "=== Installing for Claude Code ==="
  bash "$0" "${both_args[@]+"${both_args[@]}"}" --claude
  echo ""
  echo "=== Installing for Grok Build ==="
  bash "$0" "${both_args[@]+"${both_args[@]}"}" --grok
  echo ""
  echo "Both agents installed at the same skill version. Switch coders with: roadmap.py handoff"
  exit 0
fi

# Roadmap rules are project-specific; never write a global CLAUDE.md.
[ "$scope" = "global" ] && claude_md=0

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
  base="$HOME/.$agent"
else
  base="$PWD/.$agent"
fi
skills_dest="$base/skills"
settings="$base/settings.json"

mkdir -p "$skills_dest"

installed=0
for skill_dir in "$SRC_DIR"/*/; do
  [ -f "${skill_dir}SKILL.md" ] || continue
  name="$(basename "$skill_dir")"
  _want "$name" || continue
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

# Wire lifecycle hooks (idempotent) unless opted out.
# Claude Code: merge into settings.json.
# Grok Build: native .grok/hooks/*.json (also reads .claude/settings.json, but
# native files survive without a Claude-compat shim).
#
#   Stop         → roadmap-sync.sh  (sync + drift-check nudge)
#   SessionStart → roadmap-orient.sh (inject current version + next item)
chmod +x "$skills_dest/roadmap/hooks/"*.sh 2>/dev/null || true

_wire_claude_hook() {
  # $1 = settings path, $2 = event name (Stop|SessionStart), $3 = command string
  "$PYTHON" - "$1" "$2" "$3" <<'PY'
import json, os, sys
settings_path, event, cmd = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(settings_path):
    with open(settings_path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {settings_path} is not valid JSON; left unchanged.", file=sys.stderr)
            sys.exit(0)

bucket = data.setdefault("hooks", {}).setdefault(event, [])
present = any(h.get("command") == cmd
             for entry in bucket for h in entry.get("hooks", []))
if present:
    print(f"{event} hook already configured in {settings_path}")
else:
    bucket.append({"hooks": [{"type": "command", "command": cmd}]})
    os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wired {event} hook into {settings_path}")
PY
}

# Idempotently merge a marker-delimited block from a source file into a target
# instruction file (CLAUDE.md / AGENTS.md). Updates the block in place if the markers
# already exist, otherwise appends it — never rewrites the rest of the file.
#   $1 target path  $2 source file (contains the block WITH markers)  $3 start  $4 end
_merge_block() {
  "$PYTHON" - "$1" "$2" "$3" "$4" <<'PY'
import os, sys
target, src, start, end = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
block = open(src, encoding="utf-8").read().strip()
existing = open(target, encoding="utf-8").read() if os.path.exists(target) else ""
if start in existing and end in existing:
    before = existing.split(start)[0]
    after = existing.split(end, 1)[1].lstrip("\n")
    new = before + block + ("\n\n" + after if after.strip() else "\n")
    action = "Updated"
elif existing.strip():
    new = existing.rstrip() + "\n\n" + block + "\n"
    action = "Added"
else:
    new = block + "\n"
    action = "Created"
os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
with open(target, "w", encoding="utf-8") as f:
    f.write(new)
print(f"{action} orchestration policy in {target}")
PY
}

# Pin a sensible main-session model + fallback chain — but ONLY when the user has not
# already chosen a model, so an explicit setting is never overridden.
_wire_model() {
  "$PYTHON" - "$1" <<'PY'
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Warning: {path} is not valid JSON; left model settings unchanged.", file=sys.stderr)
        sys.exit(0)
if "model" in data:
    print(f"Main-session model already set to {data['model']!r} in {path}; left unchanged.")
    sys.exit(0)
data["model"] = "fable"
data.setdefault("fallbackModel", ["opus"])
os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"Pinned main-session model 'fable' (fallback: opus) in {path}")
PY
}

if [ "$agent" = "grok" ]; then
  if [ "$hook" = "1" ] || [ "$orient" = "1" ]; then
    mkdir -p "$base/hooks"
  fi
  if [ "$hook" = "1" ]; then
    hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
    if [ -f "$hook_path" ]; then
      cat > "$base/hooks/roadmap-sync.json" <<EOF
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "bash \"$hook_path\"" } ] }
    ]
  }
}
EOF
      echo "Wired roadmap Stop hook into $base/hooks/roadmap-sync.json"
    fi
  fi
  if [ "$orient" = "1" ]; then
    orient_path="$skills_dest/roadmap/hooks/roadmap-orient.sh"
    if [ -f "$orient_path" ]; then
      cat > "$base/hooks/roadmap-orient.json" <<EOF
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "bash \"$orient_path\"" } ] }
    ]
  }
}
EOF
      echo "Wired roadmap SessionStart orient hook into $base/hooks/roadmap-orient.json"
    fi
  fi
else
  if [ "$hook" = "1" ]; then
    hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
    [ -f "$hook_path" ] && _wire_claude_hook "$settings" "Stop" "bash \"$hook_path\""
  fi
  if [ "$orient" = "1" ]; then
    orient_path="$skills_dest/roadmap/hooks/roadmap-orient.sh"
    [ -f "$orient_path" ] && _wire_claude_hook "$settings" "SessionStart" "bash \"$orient_path\""
  fi
fi

# Install slash commands unless --no-commands.
#
# Claude Code discovers nested commands/<ns>/<cmd>.md as /ns:cmd
#   e.g. commands/roadmap/next.md → /roadmap:next
# Grok Build only discovers *flat* commands/*.md (filename stem = command name);
# nested dirs are ignored, and ":" in names is not accepted (normalized away).
# So we also install flat aliases as <ns>-<cmd>.md → /ns-cmd
#   e.g. commands/roadmap/next.md → roadmap-next.md → /roadmap-next
#
# Claude installs get both layouts (Claude users keep /roadmap:*, Grok reading
# .claude/commands via compat gets /roadmap-*). Pure --grok installs get flat only.
if [ "$commands" = "1" ] && _want roadmap; then
  cmd_src="$(dirname "$SRC_DIR")/commands"
  if [ -d "$cmd_src" ]; then
    mkdir -p "$base/commands"
    flat_count=0
    for cdir in "$cmd_src"/*/; do
      [ -d "$cdir" ] || continue
      cname="$(basename "$cdir")"

      # Nested layout for Claude Code (/ns:cmd). Skip for pure Grok installs —
      # Grok never loads nested command dirs, so nested copies only waste space.
      if [ "$agent" != "grok" ]; then
        rm -rf "$base/commands/$cname"
        if [ "$link" = "1" ]; then
          ln -s "${cdir%/}" "$base/commands/$cname"
        else
          cp -R "${cdir%/}" "$base/commands/$cname"
        fi
      fi

      # Flat namespaced layout for Grok (/ns-cmd). Also useful on Claude Code as
      # hyphenated aliases that show up in autocomplete the same way.
      for f in "$cdir"*.md; do
        [ -f "$f" ] || continue
        stem="$(basename "$f" .md)"
        dest="$base/commands/${cname}-${stem}.md"
        if [ "$link" = "1" ]; then
          # Absolute target so the link survives even if CWD changes later.
          ln -sfn "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" "$dest"
        else
          cp "$f" "$dest"
        fi
        flat_count=$((flat_count + 1))
      done
    done
    if [ "$agent" = "grok" ]; then
      echo "Installed $flat_count Grok commands -> $base/commands (try /roadmap-init, /roadmap-next, /roadmap-build)"
    else
      echo "Installed commands -> $base/commands (Claude: /roadmap:init; Grok-compat: /roadmap-init, /roadmap-next)"
    fi
  fi
fi

# Add roadmap rules to CLAUDE.md (idempotent) so the discipline applies even when
# the skill is not explicitly invoked. Project scope only. Delegates to the installed
# CLI so the rules text has a single source of truth (RULES_BLOCK in roadmap.py).
if [ "$claude_md" = "1" ] && _want roadmap; then
  "$PYTHON" - "$skills_dest/roadmap/scripts/roadmap.py" <<'PY'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("roadmap", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
path = mod.ensure_claude_md_rules(pathlib.Path.cwd())
print(f"Ensured roadmap rules in {path}")
PY
fi

# Install the cost-tiered orchestration fleet (Claude only) unless --no-agent.
# Copies the project subagents into <base>/agents/, merges the orchestration policy
# into CLAUDE.md + AGENTS.md (idempotent; updates a marked block, never rewrites the
# file), and pins a default model when none is set. The named-tier agents use Claude's
# .claude/agents/ format, so this step is skipped for Grok installs.
fleet_installed=0
if [ "$agent_fleet" = "1" ] && _want agent && [ "$agent" = "claude" ] && [ -d "$skills_dest/agent/.claude/agents" ]; then
  agents_dest="$base/agents"
  mkdir -p "$agents_dest"
  copied=0
  for af in "$skills_dest/agent/.claude/agents/"*.md; do
    [ -f "$af" ] || continue
    if [ "$link" = "1" ]; then
      ln -sfn "$(cd "$(dirname "$af")" && pwd)/$(basename "$af")" "$agents_dest/$(basename "$af")"
    else
      cp "$af" "$agents_dest/$(basename "$af")"
    fi
    copied=$((copied + 1))
  done
  echo "Installed $copied orchestration agent(s) -> $agents_dest"
  fleet_installed=1

  # SessionStart hook: forces the caveman-level decision at orientation. The script
  # no-ops when the caveman plugin is absent, so wiring it is always safe. Honors
  # --no-hook.
  if [ "$agent_hook" = "1" ]; then
    chmod +x "$skills_dest/agent/hooks/"*.sh 2>/dev/null || true
    cl_hook="$skills_dest/agent/hooks/caveman-level.sh"
    [ -f "$cl_hook" ] && _wire_claude_hook "$settings" "SessionStart" "bash \"$cl_hook\""
  fi

  # Merge the orchestration policy into CLAUDE.md + AGENTS.md (project scope only —
  # like the roadmap rules, we never write a global CLAUDE.md). Honors --no-claude-md.
  if [ "$claude_md" = "1" ]; then
    policy_src="$skills_dest/agent/references/orchestration-policy.md"
    if [ -f "$policy_src" ]; then
      for target in CLAUDE.md AGENTS.md; do
        _merge_block "$PWD/$target" "$policy_src" \
          "<!-- agent:orchestration:start -->" "<!-- agent:orchestration:end -->"
      done
    fi
  fi

  # Pin a default main-session model (non-destructive) unless --no-model.
  [ "$model_wire" = "1" ] && _wire_model "$settings"
fi

# Optional 'claude-roadmap' PATH command. Default on for --global: the script
# resolves the project from your CWD (find_root), so one command serves every
# project — e.g. `claude-roadmap serve` or `claude-roadmap status` anywhere.
if [ "$cli" = "-1" ]; then
  if [ "$scope" = "global" ]; then cli=1; else cli=0; fi
fi
if [ "$cli" = "1" ] && [ "$agent" = "claude" ]; then
  rp_script="$skills_dest/roadmap/scripts/roadmap.py"
  if [ -f "$rp_script" ]; then
    bindir="$HOME/.local/bin"
    mkdir -p "$bindir"
    shim="$bindir/claude-roadmap"
    cat > "$shim" <<SHIM
#!/usr/bin/env bash
# Installed by claude-skills install.sh — runs the roadmap CLI against your CWD.
exec "${PYTHON:-python3}" "$rp_script" "\$@"
SHIM
    chmod +x "$shim"
    echo "Installed CLI:    claude-roadmap -> $shim"
    case ":$PATH:" in
      *":$bindir:"*) : ;;
      *)
        echo "  Note: $bindir is not on PATH. Add it (zsh):"
        echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
        ;;
    esac
  fi
fi

if [ "$do_init" = "1" ]; then
  echo "Running roadmap init in $PWD ..."
  "$PYTHON" "$skills_dest/roadmap/scripts/roadmap.py" init
fi

echo ""
echo "Done. Installed $installed skill(s) into $skills_dest."
if [ "$agent" = "grok" ]; then
  echo "Start a new Grok Build session to pick up the skill(s); run 'grok inspect' to verify discovery."
else
  echo "Start a new Claude Code session to pick up the skill(s)."
  if [ "$fleet_installed" = "1" ]; then
    echo "The orchestration fleet registers on the NEXT session. Until then, dispatch"
    echo "'general-purpose' with a model override (opus/sonnet/haiku) and the same brief."
  fi
fi
