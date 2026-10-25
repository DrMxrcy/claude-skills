#!/usr/bin/env bash
# Opt-in SessionStart hook: make the caveman level a decision, not an accident.
#
# Two modes:
#   1. Project preference (`.claude/caveman-level` containing lite|full|ultra|wenyan):
#      the hook SETS the level itself — writes the plugin's flag file and mode log —
#      and tells the session it's already active. Nobody types anything.
#   2. No preference: injects the decision prompt so the orchestrator chooses by
#      session shape, invokes the caveman skill, and persists the flag.
#
# The caveman plugin only records levels typed by the user (its UserPromptSubmit
# tracker), so without this hook a model-side decision never reaches the tracker,
# statusline, or later sessions.
#
# Safe no-op (exit 0, no output) when the caveman plugin is not installed.
set -euo pipefail

flag="$HOME/.claude/.caveman-active"
plugin_dir="$HOME/.claude/plugins/cache/caveman"
[ -f "$flag" ] || [ -d "$plugin_dir" ] || exit 0

level="unset"
[ -f "$flag" ] && level="$(head -c 32 "$flag" | tr -d '[:space:]')"
[ -n "$level" ] || level="unset"

proj="${CLAUDE_PROJECT_DIR:-$PWD}"
pref=""
if [ -f "$proj/.claude/caveman-level" ]; then
  pref="$(head -c 32 "$proj/.claude/caveman-level" | tr -d '[:space:]')"
  case "$pref" in lite|full|ultra|wenyan) ;; *) pref="" ;; esac
fi

if [ -n "$pref" ]; then
  if [ "$pref" != "$level" ]; then
    printf '%s' "$pref" > "$flag"
    python3 - "$pref" "$level" 2>/dev/null <<'PY' || true
import json, sys, time, os
log = os.path.expanduser("~/.claude/.caveman-mode-log.jsonl")
prev = None if sys.argv[2] == "unset" else sys.argv[2]
with open(log, "a") as f:
    f.write(json.dumps({"ts": int(time.time()*1000), "mode": sys.argv[1],
                        "prev": prev, "by": "agent-skill-project-preference"}) + "\n")
PY
  fi
  context="Caveman level '${pref}' set from project preference \
(.claude/caveman-level) — already active and persisted; no action needed. Subagent \
briefs: caveman-terse prose; code, commands, paths, and errors stay verbatim."
else
  context="Caveman plugin active — current level: '${level}' (a session-start default \
unless the user chose it). Per the orchestration policy, decide the level NOW by \
session shape, before other work: ultra for orchestration-heavy sessions \
(multi-agent build chains, --auto runs, bulk sweeps), full for ordinary mixed work, \
lite when the user reads agent reports directly. Announcing is NOT setting: invoke \
the caveman skill with the chosen level AND persist it \
(printf '<level>' > ~/.claude/.caveman-active), then state the choice in one line. \
Tip: pin a per-project default in .claude/caveman-level to skip this decision. \
Compression applies to prose only; code, commands, paths, and errors stay verbatim."
fi

python3 - "$context" 2>/dev/null <<'PY' || printf '%s\n' "$context"
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": sys.argv[1]}}))
PY
