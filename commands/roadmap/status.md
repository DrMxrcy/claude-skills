---
description: Show the current roadmap status (versions, items, progress)
---

Show the current roadmap status. Run the roadmap CLI:

`python3 <roadmap.py> status`

Summarize the current version, each version's items grouped by type, and progress
percentages. Also surface the latest `CHANGELOG.md` entry (the most recently released version)
if the file exists, so the user sees what shipped last. If `.roadmap/` does not exist yet,
tell the user to run `/roadmap:init` first.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill at a
fixed path; resolve it once and reuse `$RM`:

```bash
RM=.claude/skills/roadmap/scripts/roadmap.py; [ -f "$RM" ] || RM="$HOME/.claude/skills/roadmap/scripts/roadmap.py"
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
