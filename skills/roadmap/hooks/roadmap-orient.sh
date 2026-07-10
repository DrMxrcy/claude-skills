#!/usr/bin/env bash
# Opt-in SessionStart hook: inject current roadmap orientation into the session.
# Safe no-op (exit 0, no output) when .roadmap/ is absent.
set -euo pipefail
root="$(pwd)"
while [ "$root" != "/" ] && [ ! -d "$root/.roadmap" ]; do root="$(dirname "$root")"; done
[ -d "$root/.roadmap" ] || exit 0
script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/roadmap.py"
cd "$root"
# --hook emits Claude SessionStart additionalContext JSON; plain text also works
# for agents that simply surface command stdout (Grok).
python3 "$script" orient --hook 2>/dev/null || python3 "$script" orient 2>/dev/null || true
