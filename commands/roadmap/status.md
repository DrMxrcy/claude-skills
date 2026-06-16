---
description: Show the current roadmap status (versions, items, progress)
---

Show the current roadmap status. Run the roadmap CLI:

`python3 .claude/skills/roadmap/scripts/roadmap.py status`

(or the global path `~/.claude/skills/roadmap/scripts/roadmap.py status`).

Summarize the current version, each version's items grouped by type, and progress
percentages. If `.roadmap/` does not exist yet, tell the user to run `/roadmap:init` first.
