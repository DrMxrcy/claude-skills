#!/usr/bin/env bash
# Opt-in Stop hook: keep ROADMAP.md synced even if a sync was missed.
# Add to settings.json under hooks.Stop. Safe no-op if .roadmap/ is absent.
set -euo pipefail
root="$(pwd)"
while [ "$root" != "/" ] && [ ! -d "$root/.roadmap" ]; do root="$(dirname "$root")"; done
[ -d "$root/.roadmap" ] || exit 0
script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/roadmap.py"
python3 "$script" sync >/dev/null 2>&1 || true
