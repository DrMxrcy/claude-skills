#!/usr/bin/env bash
# Opt-in SessionStart hook: inject current roadmap orientation into the session.
# Safe no-op (exit 0, no output) when .roadmap/ is absent.
set -euo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/roadmap.py"

if [ -n "${ANTIGRAVITY_AGENT:-}" ] || [ -n "${ANTIGRAVITY_APP_DATA_DIR:-}" ]; then
  # AGY PreInvocation hook: consumes stdin JSON (non-blocking), injects ephemeral orientation on invocation 1
  python3 -c '
import json, os, select, subprocess, sys
script = sys.argv[1]
raw = ""
if not sys.stdin.isatty():
    try:
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if r:
            raw = sys.stdin.read()
    except Exception:
        pass

inv_num = 1
workspace = None
if raw.strip():
    try:
        data = json.loads(raw)
        inv_num = data.get("invocationNum", 1)
        paths = data.get("workspacePaths") or []
        if paths:
            workspace = paths[0]
    except Exception:
        pass

if not workspace:
    workspace = os.getcwd()

root = os.path.abspath(workspace)
while root != "/" and not os.path.isdir(os.path.join(root, ".roadmap")):
    root = os.path.dirname(root)

# Only inject orientation on the very first invocation in a session, when .roadmap exists
if inv_num == 1 and os.path.isdir(os.path.join(root, ".roadmap")):
    try:
        res = subprocess.run([sys.executable, script, "orient"], cwd=root, capture_output=True, text=True)
        out = (res.stdout or "").strip()
        if out:
            print(json.dumps({"injectSteps": [{"ephemeralMessage": out}]}))
            sys.exit(0)
    except Exception:
        pass

print(json.dumps({"injectSteps": []}))
' "$script"
  exit 0
fi

# Claude SessionStart / Grok orient
root="$(pwd)"
while [ "$root" != "/" ] && [ ! -d "$root/.roadmap" ]; do root="$(dirname "$root")"; done
[ -d "$root/.roadmap" ] || exit 0
cd "$root"
# --hook emits Claude SessionStart additionalContext JSON; plain text also works
# for agents that simply surface command stdout (Grok).
python3 "$script" orient --hook 2>/dev/null || python3 "$script" orient 2>/dev/null || true
