#!/usr/bin/env bash
# Opt-in SessionStart hook: make the orchestrator decide the caveman level up front.
#
# The caveman plugin's own hook writes its default level to ~/.claude/.caveman-active
# each session, so the model otherwise sees a level as "already set" and never makes
# the call the orchestration policy asks for. This hook injects the current level and
# the decision prompt as session context, so the choice happens at orientation —
# mechanically, not by hoping the policy paragraph gets read in time.
#
# Safe no-op (exit 0, no output) when the caveman plugin is not installed.
set -euo pipefail

flag="$HOME/.claude/.caveman-active"
plugin_dir="$HOME/.claude/plugins/cache/caveman"
[ -f "$flag" ] || [ -d "$plugin_dir" ] || exit 0

level="unset"
[ -f "$flag" ] && level="$(head -c 32 "$flag" | tr -d '[:space:]')"
[ -n "$level" ] || level="unset"

context="Caveman plugin active — current level: '${level}' (a session-start default \
unless the user chose it). Per the orchestration policy, decide the level NOW by \
session shape, before other work: /caveman ultra for orchestration-heavy sessions \
(multi-agent build chains, --auto runs, bulk sweeps), full for ordinary mixed work, \
lite when the user reads agent reports directly — then state the choice in one line. \
Compression applies to prose only; code, commands, paths, and errors stay verbatim."

python3 - "$context" 2>/dev/null <<'PY' || printf '%s\n' "$context"
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": sys.argv[1]}}))
PY
