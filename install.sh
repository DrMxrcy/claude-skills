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
#   ./install.sh --codex         # target OpenAI Codex CLI: skill + hooks + AGENTS.md rules
#   ./install.sh --agy           # target Google Antigravity (agy): ./.agents + hooks + AGENTS.md
#   ./install.sh --both          # install Claude + Grok (same skill version; keeps coders in sync)
#   ./install.sh --link          # symlink instead of copy (good for development)
#   ./install.sh --no-hook       # do not wire the auto-sync Stop hook (sync + drift-check)
#   ./install.sh --no-orient     # do not wire the SessionStart orient hook
#   ./install.sh --no-commands   # do not install the /roadmap:* (Claude) / /roadmap-* (Grok) slash commands
#   ./install.sh --no-claude-md  # do not add roadmap rules to CLAUDE.md / AGENTS.md
#   ./install.sh --no-agent      # do not install the cost-tiered agent orchestration fleet (Claude)
#   ./install.sh --gitignore     # append a public-repo ignore block (.claude/ etc.) to ./.gitignore
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
gitignore=0
cli=-1          # -1 = auto (on for --global); 0/1 = forced by --no-cli/--cli
only=""
pass_args=()
for arg in "$@"; do
  case "$arg" in
    --global) scope="global"; pass_args+=("$arg") ;;
    --project) scope="project"; pass_args+=("$arg") ;;
    --grok) agent="grok"; pass_args+=("$arg") ;;
    --codex) agent="codex"; pass_args+=("$arg") ;;
    --agy|--antigravity) agent="agy"; pass_args+=("$arg") ;;
    --opencode) agent="opencode"; pass_args+=("$arg") ;;
    --claude) agent="claude"; pass_args+=("$arg") ;;
    --both|--all-agents) both=1 ;;
    --link) link=1; pass_args+=("$arg") ;;
    --no-hook) hook=0; pass_args+=("$arg") ;;
    --no-orient) orient=0; pass_args+=("$arg") ;;
    --no-commands) commands=0; pass_args+=("$arg") ;;
    --no-claude-md) claude_md=0; pass_args+=("$arg") ;;
    --no-agent) agent_fleet=0; pass_args+=("$arg") ;;
    --cli) cli=1; pass_args+=("$arg") ;;
    --no-cli) cli=0; pass_args+=("$arg") ;;
    --only=*) only="${arg#--only=}"; pass_args+=("$arg") ;;
    --gitignore) gitignore=1; pass_args+=("$arg") ;;
    --init) do_init=1; pass_args+=("$arg") ;;
    -h|--help)
      cat <<'EOF'
install.sh — import this repo's skills into Claude Code, Grok Build, OpenAI Codex, or
Google Antigravity (agy); install supported agent commands, wire Stop (sync+drift)
and SessionStart/PreInvocation (orient) hooks, and add roadmap rules to instruction files.

  ./install.sh            install into ./.claude (this project)
  --global                install into ~/.claude (all projects); skips project rules
  --grok                  target Grok Build: ./.grok (or ~/.grok with --global),
                          native hooks JSON, flat /roadmap-* slash commands
  --codex                 target OpenAI Codex CLI: ./.codex (or ~/.codex with --global),
                          roadmap skill in .agents/skills (global), rules in AGENTS.md,
                          and Stop/SessionStart hooks in config.toml. Invoke with $roadmap.
                          CLI only — not the ChatGPT app.
  --agy, --antigravity    target Google Antigravity (agy): ./.agents (or ~/.gemini/config
                          with --global), rules in AGENTS.md, flat slash commands,
                          subagent fleet, and Stop + PreInvocation hooks in hooks.json.
  --both                  install Claude + Grok at the same skill version (recommended
                          when you switch between AI coders)
  --link                  symlink instead of copy (development)
  --no-hook               do not wire the Stop hook (sync + drift-check)
  --no-orient             do not wire the SessionStart orient hook
  --no-commands           do not install slash commands
  --no-claude-md          do not add roadmap rules to CLAUDE.md / AGENTS.md
  --no-agent              do not install the cost-tiered agent orchestration fleet (Claude)
  --gitignore             append a public-repo ignore block to ./.gitignore
                          (.claude/ .grok/ .codex/ .agents/ CHANGELOG.internal.md);
                          roadmap data (ROADMAP.md, .roadmap/) stays tracked on purpose
  --cli                   install a 'claude-roadmap' command on PATH (default with
                          --global) so you can run 'claude-roadmap serve' anywhere
  --no-cli                do not install the 'claude-roadmap' PATH command
  --only=<skill[,skill]>  install only these skills (agent, roadmap,
                          adversarial-review) and skip the excluded skills'
                          wiring — e.g. --only=agent when roadmap is already
                          installed globally
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
# OpenCode has no roadmap hook wiring yet: install skills and commands only.
if [ "$agent" = "opencode" ]; then hook=0; orient=0; fi

# --both: install Claude then Grok with the same flags (keeps multi-coder skill in sync).
if [ "$both" = "1" ]; then
  # Drop agent selectors from the recursive pass; force each target.
  both_args=()
  for a in "${pass_args[@]+"${pass_args[@]}"}"; do
    case "$a" in
      --grok|--codex|--claude|--agy|--antigravity|--both|--all-agents) ;;
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

# Roadmap rules are project-specific; never write a global CLAUDE.md. Exception:
# a global Codex or AGY install writes rules to AGENTS.md in its own global directory,
# so the discipline applies there too.
[ "$scope" = "global" ] && [ "$agent" != "codex" ] && [ "$agent" != "agy" ] && claude_md=0
[ "$agent" = "opencode" ] && claude_md=0

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

if [ "$agent" = "agy" ]; then
  if [ "$scope" = "global" ]; then
    base="$HOME/.gemini/config"
  else
    base="$PWD/.agents"
  fi
  skills_dest="$base/skills"
  settings="$base/hooks.json"
elif [ "$agent" = "opencode" ]; then
  # OpenCode: skills and commands only. No hook wiring, no AGENTS.md rules (opt-in later).
  if [ "$scope" = "global" ]; then base="$HOME/.config/opencode"; else base="$PWD/.opencode"; fi
  skills_dest="$base/skills"
  settings="$base/opencode.json"
elif [ "$scope" = "global" ]; then
  base="$HOME/.$agent"
  skills_dest="$base/skills"
  settings="$base/settings.json"
else
  base="$PWD/.$agent"
  skills_dest="$base/skills"
  settings="$base/settings.json"
fi

# Codex loads user skills from ~/.agents/skills (its current root); ~/.codex/skills is
# only a deprecated fallback. For a global Codex install, put skills on the supported
# path while config.toml and other Codex state stay under ~/.codex ($base).
if [ "$agent" = "codex" ] && [ "$scope" = "global" ]; then
  skills_dest="$HOME/.agents/skills"
fi

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
    # evals/ (golden tasks + fixtures) is dev-only; never ship it to user installs.
    rm -rf "$target/evals"
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
if "roadmap-sync.sh" in cmd:
    script_name = "roadmap-sync.sh"
elif "roadmap-orient.sh" in cmd:
    script_name = "roadmap-orient.sh"
else:
    script_name = ""
roadmap_hook_marker = f"/skills/roadmap/hooks/{script_name}" if script_name else ""
present = False
changed = False
cleaned = []
for entry in bucket:
    kept = []
    for hook in entry.get("hooks", []):
        hook_cmd = hook.get("command", "")
        if hook_cmd == cmd:
            if present:
                changed = True
                continue
            present = True
        elif roadmap_hook_marker and roadmap_hook_marker in hook_cmd:
            # Drop an older install location for this same roadmap hook.
            changed = True
            continue
        kept.append(hook)
    if kept:
        entry["hooks"] = kept
        cleaned.append(entry)
    elif entry.get("hooks"):
        changed = True
bucket[:] = cleaned

if present and not changed:
    print(f"{event} hook already configured in {settings_path}")
else:
    if not present:
        bucket.append({"hooks": [{"type": "command", "command": cmd}]})
    os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    action = "Migrated" if changed else "Wired"
    print(f"{action} {event} hook in {settings_path}")
PY
}

_wire_codex_hooks() {
  # $1 config.toml, $2 legacy hooks.json, $3 Stop command (or empty),
  # $4 SessionStart command (or empty). Codex warns when both representations
  # exist, so migrate every JSON hook into TOML before removing hooks.json.
  "$PYTHON" - "$1" "$2" "$3" "$4" <<'PY'
import json, os, re, sys, tempfile

config_path, json_path, stop_cmd, start_cmd = sys.argv[1:5]
begin = "# roadmap:codex-hooks:start"
end = "# roadmap:codex-hooks:end"
migration_begin = "# roadmap:hooks-json-migration:start"
migration_end = "# roadmap:hooks-json-migration:end"


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported hook value: {value!r}")


def render_groups(groups):
    lines = []
    for event, group in groups:
        hooks = group.get("hooks", [])
        if not hooks:
            continue
        lines.append(f"[[hooks.{event}]]")
        for key, value in group.items():
            if key == "hooks" or value is None:
                continue
            lines.append(f"{key} = {toml_value(value)}")
        for hook in hooks:
            lines.extend(("", f"[[hooks.{event}.hooks]]"))
            for key, value in hook.items():
                if value is not None:
                    lines.append(f"{key} = {toml_value(value)}")
        lines.append("")
    return "\n".join(lines).rstrip()


os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
base = open(config_path, encoding="utf-8").read() if os.path.exists(config_path) else ""
managed_re = re.compile(
    rf"\n?{re.escape(begin)}.*?{re.escape(end)}\n?", re.DOTALL
)
base = managed_re.sub("\n", base).rstrip()

migrated = []
if os.path.exists(json_path):
    try:
        legacy = json.load(open(json_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: could not migrate {json_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    for event, groups in legacy.get("hooks", {}).items():
        for group in groups:
            kept = []
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                if "/skills/roadmap/hooks/roadmap-sync.sh" in command:
                    continue
                if "/skills/roadmap/hooks/roadmap-orient.sh" in command:
                    continue
                # Avoid duplicating a hook already represented in config.toml.
                if command and command in base:
                    continue
                kept.append(hook)
            if kept:
                copied = dict(group)
                copied["hooks"] = kept
                migrated.append((event, copied))

parts = [base] if base else []
rendered_migration = render_groups(migrated)
if rendered_migration:
    parts.append(f"{migration_begin}\n{rendered_migration}\n{migration_end}")

roadmap_groups = []
if stop_cmd:
    roadmap_groups.append(("Stop", {"hooks": [{"type": "command", "command": stop_cmd}]}))
if start_cmd:
    roadmap_groups.append(("SessionStart", {"hooks": [{"type": "command", "command": start_cmd}]}))
rendered_roadmap = render_groups(roadmap_groups)
if rendered_roadmap:
    parts.append(f"{begin}\n{rendered_roadmap}\n{end}")

updated = "\n\n".join(part for part in parts if part).rstrip() + "\n"
try:
    import tomllib
except ImportError:
    tomllib = None
if tomllib is not None:
    tomllib.loads(updated)

fd, tmp_path = tempfile.mkstemp(prefix="config.toml.", dir=os.path.dirname(config_path) or ".")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(updated)
    os.replace(tmp_path, config_path)
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

if os.path.exists(json_path):
    os.unlink(json_path)
    print(f"Migrated Codex hooks from {json_path} into {config_path}")
else:
    print(f"Wired roadmap hooks into {config_path}")
PY
}

_wire_agy_hooks() {
  # $1 hooks.json path, $2 Stop command (or empty), $3 PreInvocation command (or empty)
  "$PYTHON" - "$1" "$2" "$3" <<'PY'
import json, os, sys

hooks_path, stop_cmd, orient_cmd = sys.argv[1:4]
data = {}
if os.path.exists(hooks_path):
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

if not isinstance(data, dict):
    data = {}

if stop_cmd:
    data["roadmap-sync"] = {
        "Stop": [
            {
                "type": "command",
                "command": stop_cmd,
            }
        ]
    }

if orient_cmd:
    data["roadmap-orient"] = {
        "PreInvocation": [
            {
                "type": "command",
                "command": orient_cmd,
            }
        ]
    }

os.makedirs(os.path.dirname(os.path.abspath(hooks_path)), exist_ok=True)
with open(hooks_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"Wired AGY hooks into {hooks_path}")
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
elif [ "$agent" = "codex" ]; then
  stop_command=""; start_command=""
  if [ "$hook" = "1" ]; then
    hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
    [ -f "$hook_path" ] && stop_command="bash \"$hook_path\""
  fi
  if [ "$orient" = "1" ]; then
    orient_path="$skills_dest/roadmap/hooks/roadmap-orient.sh"
    [ -f "$orient_path" ] && start_command="bash \"$orient_path\""
  fi
  if [ -n "$stop_command" ] || [ -n "$start_command" ]; then
    _wire_codex_hooks "$base/config.toml" "$base/hooks.json" "$stop_command" "$start_command"
  fi
elif [ "$agent" = "agy" ]; then
  stop_command=""; start_command=""
  if [ "$hook" = "1" ]; then
    hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
    [ -f "$hook_path" ] && stop_command="bash \"$hook_path\""
  fi
  if [ "$orient" = "1" ]; then
    orient_path="$skills_dest/roadmap/hooks/roadmap-orient.sh"
    [ -f "$orient_path" ] && start_command="bash \"$orient_path\""
  fi
  if [ -n "$stop_command" ] || [ -n "$start_command" ]; then
    _wire_agy_hooks "$base/hooks.json" "$stop_command" "$start_command"
  fi
else
  # Claude Code reads .claude/settings.json using the JSON hooks envelope.
  hooks_target="$settings"
  if [ "$hook" = "1" ]; then
    hook_path="$skills_dest/roadmap/hooks/roadmap-sync.sh"
    [ -f "$hook_path" ] && _wire_claude_hook "$hooks_target" "Stop" "bash \"$hook_path\""
  fi
  if [ "$orient" = "1" ]; then
    orient_path="$skills_dest/roadmap/hooks/roadmap-orient.sh"
    [ -f "$orient_path" ] && _wire_claude_hook "$hooks_target" "SessionStart" "bash \"$orient_path\""
  fi
fi

# Install agent-supported command files unless --no-commands.
#
# Claude Code discovers nested commands/<ns>/<cmd>.md as /ns:cmd
#   e.g. commands/roadmap-next.md → /roadmap-next
# Grok Build only discovers *flat* commands/*.md (filename stem = command name);
# nested dirs are ignored, and ":" in names is not accepted (normalized away).
# So we also install flat aliases as <ns>-<cmd>.md → /ns-cmd
#   e.g. commands/roadmap-next.md → roadmap-next.md → /roadmap-next
#
# Claude installs get both layouts (Claude users keep /roadmap:*, Grok reading
# .claude/commands via compat gets /roadmap-*). Pure --grok installs get flat only.
# Codex has a fixed built-in slash-command list and invokes installed skills with
# $<skill-name>, so it must not receive legacy .codex/prompts files.
if [ "$agent" = "codex" ] && _want roadmap; then
  # Clean up files written by roadmap v0.14.0 without touching other custom prompts.
  for legacy_prompt in "$base/prompts"/roadmap-*.md; do
    [ -e "$legacy_prompt" ] || [ -L "$legacy_prompt" ] || continue
    rm -f "$legacy_prompt"
  done
  rmdir "$base/prompts" 2>/dev/null || true
fi

if [ "$commands" = "1" ] && _want roadmap && [ "$agent" != "codex" ]; then
  cmd_src="$(dirname "$SRC_DIR")/commands"
  if [ -d "$cmd_src" ]; then
    # Every agent gets the same flat roadmap-<cmd>.md layout (/roadmap-<cmd>).
    # Claude's nested /roadmap:<cmd> form is retired: one form everywhere.
    flat_dir="$base/commands"
    mkdir -p "$flat_dir"
    flat_count=0
    for f in "$cmd_src"/roadmap-*.md; do
      [ -f "$f" ] || continue
      dest="$flat_dir/$(basename "$f")"
      if [ "$link" = "1" ]; then
        # Absolute target so the link survives even if CWD changes later.
        ln -sfn "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" "$dest"
      else
        cp "$f" "$dest"
      fi
      flat_count=$((flat_count + 1))
    done
    echo "Installed $flat_count roadmap commands -> $flat_dir (try /roadmap-init, /roadmap-next, /roadmap-build)"
  fi
fi

# /adversarial-review and /single-adversarial-review: flat commands beside the skill
# (Codex invokes skills as $adversarial-review instead, so it gets no command file).
if [ "$commands" = "1" ] && _want adversarial-review && [ "$agent" != "codex" ] \
   && [ -d "$skills_dest/adversarial-review" ]; then
  for ar_name in adversarial-review single-adversarial-review; do
    ar_cmd="$(dirname "$SRC_DIR")/commands/$ar_name.md"
    [ -f "$ar_cmd" ] || continue
    mkdir -p "$base/commands"
    if [ "$link" = "1" ]; then
      ln -sfn "$(cd "$(dirname "$ar_cmd")" && pwd)/$(basename "$ar_cmd")" "$base/commands/$ar_name.md"
    else
      cp "$ar_cmd" "$base/commands/$ar_name.md"
    fi
    echo "Installed command: /$ar_name -> $base/commands/$ar_name.md"
  done
fi

# Add roadmap rules to the agent instruction files (idempotent) so the discipline
# applies even when the skill is not explicitly invoked. Delegates to the installed CLI
# so the rules text has a single source of truth (RULES_BLOCK in roadmap.py).
#   project (any agent): CWD/CLAUDE.md + CWD/AGENTS.md
#   global Codex/AGY:    ~/.<agent>/AGENTS.md only
if [ "$claude_md" = "1" ] && _want roadmap; then
  rules_root="$PWD"; rules_files="CLAUDE.md,AGENTS.md"
  if [ "$agent" = "codex" ] && [ "$scope" = "global" ]; then
    rules_root="$base"; rules_files="AGENTS.md"
  elif [ "$agent" = "agy" ]; then
    if [ "$scope" = "global" ]; then
      rules_root="$base"; rules_files="AGENTS.md"
    else
      rules_root="$PWD"; rules_files="AGENTS.md"
    fi
  fi
  "$PYTHON" - "$skills_dest/roadmap/scripts/roadmap.py" "$rules_root" "$rules_files" <<'PY'
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("roadmap", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
root = pathlib.Path(sys.argv[2])
files = tuple(sys.argv[3].split(","))
for path in mod.ensure_project_rules(root, files):
    print(f"Ensured roadmap rules in {path}")
PY
fi

# Install the cost-tiered orchestration fleet (Claude and AGY) unless --no-agent.
# Copies the project subagents into <base>/agents/, merges the orchestration policy
# into CLAUDE.md + AGENTS.md (idempotent; updates a marked block, never rewrites the
# file), and pins a default model when none is set. The named-tier agents use Claude's
# .claude/agents/ format, so this step is skipped for Grok installs.
fleet_installed=0
if [ "$agent_fleet" = "1" ] && _want agent && { [ "$agent" = "claude" ] || [ "$agent" = "agy" ]; } && [ -d "$skills_dest/agent/.claude/agents" ]; then
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
  # Explore was retired from the fleet (plan 56); drop our stale copy, never a user's own.
  if [ -f "$agents_dest/Explore.md" ] && grep -q "^description: Fast read-only codebase exploration" "$agents_dest/Explore.md"; then
    rm -f "$agents_dest/Explore.md"
  fi
  echo "Installed $copied orchestration agent(s) -> $agents_dest"
  fleet_installed=1

  # The skill ships its agent templates at skills/agent/.claude/agents/ so they're
  # copied above into agents_dest ($base/agents, the path Claude Code actually reads).
  # In copy mode that leaves a redundant nested .claude/agents/ inside the installed
  # skill dir too — strip it so only one copy exists. Skip in --link mode: there
  # skills_dest/agent IS the source repo dir, not a copy.
  if [ "$link" != "1" ]; then
    rm -rf "$skills_dest/agent/.claude"
  fi

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

fi

# Optional 'claude-roadmap' PATH command. Default on for --global: the script
# resolves the project from your CWD (find_root), so one command serves every
# project — e.g. `claude-roadmap serve` or `claude-roadmap status` anywhere.
# It prefers a project's own skill copy (walking up from CWD), then this install,
# then any ~/.claude|.grok|.agents copy; a bare `claude-roadmap` outside every
# roadmap project opens the all-projects dashboard (`serve --all`, plan 48).
if [ "$cli" = "-1" ]; then
  if [ "$scope" = "global" ]; then cli=1; else cli=0; fi
fi
if [ "$cli" = "1" ] && [ "$agent" = "claude" ]; then
  rp_script="$skills_dest/roadmap/scripts/roadmap.py"
  if [ -f "$rp_script" ]; then
    bindir="$HOME/.local/bin"
    mkdir -p "$bindir"
    shim="$bindir/claude-roadmap"
    {
      printf '#!/usr/bin/env bash\n'
      printf '# Installed by claude-skills install.sh — runs the roadmap CLI against your CWD.\n'
      printf 'py=%q\ninstalled=%q\n' "${PYTHON:-python3}" "$rp_script"
      cat <<'SHIM'
# Prefers the project's own copy (walking up from CWD), then the installed one,
# then any ~/.claude|.grok|.agents copy. Outside every roadmap project, a bare
# `claude-roadmap` opens the all-projects dashboard (`serve --all`).
rel=skills/roadmap/scripts/roadmap.py
script= inproj=
d=$PWD
while :; do
  [ -f "$d/.roadmap/config.json" ] && inproj=1
  if [ -z "$script" ]; then
    for a in .claude .grok .agents; do
      [ -f "$d/$a/$rel" ] && { script="$d/$a/$rel"; break; }
    done
  fi
  { [ -n "$script" ] && [ -n "$inproj" ]; } && break
  [ "$d" = / ] && break
  d=$(dirname "$d")
done
[ -z "$script" ] && [ -f "$installed" ] && script=$installed
if [ -z "$script" ]; then
  for a in .claude .grok .agents; do
    [ -f "$HOME/$a/$rel" ] && { script="$HOME/$a/$rel"; break; }
  done
fi
if [ -z "$script" ]; then
  echo "claude-roadmap: no roadmap skill found in this project or ~/.claude|.grok|.agents" >&2
  exit 1
fi
[ $# -eq 0 ] && [ -z "$inproj" ] && set -- serve --all
exec "$py" "$script" "$@"
SHIM
    } > "$shim"
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

# Optional .gitignore block for public repos: keep the reinstallable AI tooling and
# the internal dev log out of git. Roadmap data (ROADMAP.md, .roadmap/, CHANGELOG.md)
# stays tracked on purpose — it is the cross-agent sync state. Idempotent via the
# block's first comment line; project scope only (--global installs nothing here).
if [ "$gitignore" = "1" ] && [ "$scope" = "project" ]; then
  gi="$PWD/.gitignore"
  if grep -q "AI coding tooling" "$gi" 2>/dev/null; then
    echo "Gitignore block already present in $gi"
  else
    cat >> "$gi" <<'EOF'

# AI coding tooling — reinstallable via claude-skills install.sh
.claude/
.grok/
.codex/
.agents/

# Full internal dev log (public notes stay in CHANGELOG.md)
CHANGELOG.internal.md
EOF
    echo "Appended AI-tooling ignore block -> $gi"
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
elif [ "$agent" = "codex" ]; then
  echo "Start a new Codex CLI session to pick up the skill(s). Roadmap rules land in AGENTS.md;"
  echo "Stop/SessionStart hooks live in $base/config.toml. Invoke roadmap as: \$roadmap status"
  echo "Other examples: \$roadmap next  |  \$roadmap build 1.0.0 --auto"
  echo "Note: the ChatGPT desktop app has no filesystem/skill hook — CLI only."
elif [ "$agent" = "agy" ]; then
  echo "Start a new Antigravity (agy) session to pick up the skill(s). Roadmap rules land in AGENTS.md;"
  echo "Stop/PreInvocation hooks live in $base/hooks.json. Slash commands available: /roadmap-status"
  if [ "$fleet_installed" = "1" ]; then
    echo "The subagent fleet is installed into $base/agents/ (e.g. agy --agent executor)."
  fi
else
  echo "Start a new Claude Code session to pick up the skill(s)."
  if [ "$fleet_installed" = "1" ]; then
    echo "The orchestration fleet registers on the NEXT session. Until then, dispatch"
    echo "'general-purpose' with a model override (opus/sonnet/haiku) and the same brief."
  fi
fi
