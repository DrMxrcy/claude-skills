#!/usr/bin/env bash
# Opt-in Stop hook: keep ROADMAP.md synced even if a sync was missed, and nudge
# when commits landed without a roadmap check-off (drift-check).
# Safe no-op if .roadmap/ is absent.
set -euo pipefail
root="$(pwd)"
while [ "$root" != "/" ] && [ ! -d "$root/.roadmap" ]; do root="$(dirname "$root")"; done
[ -d "$root/.roadmap" ] || exit 0
script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/roadmap.py"
# Run from the project root so find_root / git see the right tree.
cd "$root"
python3 "$script" sync >/dev/null 2>&1 || true
# drift-check prints a one-line nudge (or nothing); surface it on Stop.
python3 "$script" drift-check 2>/dev/null || true
