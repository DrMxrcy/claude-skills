#!/usr/bin/env bash
# Opt-in Stop hook: keep ROADMAP.md synced even if a sync was missed, and nudge
# when commits landed without a roadmap check-off (drift-check).
# Safe no-op if .roadmap/ is absent.
set -euo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/roadmap.py"

if [ -n "${ANTIGRAVITY_AGENT:-}" ] || [ -n "${ANTIGRAVITY_APP_DATA_DIR:-}" ]; then
  # AGY lifecycle hook: consumes stdin JSON (non-blocking), must emit valid JSON to stdout
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

workspace = None
if raw.strip():
    try:
        data = json.loads(raw)
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

if os.path.isdir(os.path.join(root, ".roadmap")):
    try:
        subprocess.run([sys.executable, script, "sync"], cwd=root, capture_output=True)
        subprocess.run([sys.executable, script, "drift-check"], cwd=root, capture_output=True)
    except Exception:
        pass

# Stop hook in AGY requires a valid JSON object on stdout (e.g. {})
print(json.dumps({}))
' "$script"
  exit 0
fi

# Claude / Grok / Codex lifecycle hook
root="$(pwd)"
while [ "$root" != "/" ] && [ ! -d "$root/.roadmap" ]; do root="$(dirname "$root")"; done
[ -d "$root/.roadmap" ] || exit 0
# Run from the project root so find_root / git see the right tree.
cd "$root"
python3 "$script" sync >/dev/null 2>&1 || true
# drift-check prints a one-line nudge (or nothing); surface it on Stop.
python3 "$script" drift-check 2>/dev/null || true
