---
description: Recompute progress and re-render ROADMAP.md from the plan files
---

Run `python3 <roadmap.py> sync` to
recompute progress from the plan files and re-render the managed region of `ROADMAP.md`.

Use this if the dashboard looks stale or after editing plan files by hand. It only rewrites
the region between the `roadmap:auto` markers — the Idea Incubator and other free-form
content are left untouched.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
