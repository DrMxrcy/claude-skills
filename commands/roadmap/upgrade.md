---
description: Refresh this project's CLAUDE.md roadmap rules to the installed skill version
argument-hint: (no arguments)
---

Pull the latest roadmap rules into THIS project after the skill was updated globally
(`curl … | bash --global` does not touch project CLAUDE.md files).

1. Run `python3 <roadmap.py> upgrade`. It re-injects the current rules block between the
   `roadmap:rules` markers in `CLAUDE.md` (idempotent — your other content is preserved),
   records the skill version, and resyncs `ROADMAP.md`.
2. Report the old → new version line it prints.
3. Commit the CLAUDE.md change.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global).
