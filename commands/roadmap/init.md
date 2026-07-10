---
description: Initialize roadmap tracking in this project (auto-detects existing repo for adopt mode)
---

Set up roadmap tracking in this project using the **roadmap** skill.

If the project already has code (a `package.json`/`pyproject.toml`, source files, or git
history), use **adopt** mode so the starting version is seeded from the project and any
existing `TODO.md`/`README` roadmap is ingested non-destructively. Otherwise initialize
greenfield.

- Greenfield: `python3 "$RM" init --name "<project name>"`
- Existing repo: `python3 "$RM" init --adopt --name "<project name>"`

Then confirm `ROADMAP.md` and `.roadmap/` were created and show the result.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
