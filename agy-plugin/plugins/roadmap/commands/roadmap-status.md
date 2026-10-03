---
description: Show the current roadmap status (versions, items, progress)
---

Show the current roadmap status. Run the roadmap CLI:

`python3 <roadmap.py> status`

Summarize the current version, each version's items grouped by type, and progress
percentages. Also surface the latest `CHANGELOG.md` entry (the most recently released version)
if the file exists, so the user sees what shipped last. If `.roadmap/` does not exist yet,
tell the user to run `/roadmap:init` first.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
