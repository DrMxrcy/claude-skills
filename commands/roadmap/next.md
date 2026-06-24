---
description: Build the next unfinished item in the current version
---

Pick up the next piece of roadmap work using the **roadmap** skill.

1. Run `python3 <roadmap.py> status` and find the lowest-id item in the **current version**
   that is not yet 100%.
2. If every current-version item is done, say so and suggest `/roadmap:review` then
   `/roadmap:release <next version>`. Stop.
3. Otherwise build that single item exactly like `/roadmap:build <id>`:
   - Read its plan file and any linked **Spec** / **Detailed plan** and follow them.
   - Execute the checklist step-by-step (prefer `subagent-driven-development`, else
     `executing-plans`, else direct TDD). Build/tests must pass before each `check`.
   - `python3 <roadmap.py> check --plan <id> --step <n>` after each step; commit code +
     roadmap together.
4. When the item is done, stop at a checkpoint and report — run `/roadmap:next` again for
   the following item.

This "build exactly one item, then stop" shape is the ideal iteration body for the
`ralph-loop` plugin if you want an unattended phase build — see the autonomous section of
`/roadmap:build`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill at a
fixed path; resolve it once and reuse `$RM`:

```bash
RM=.claude/skills/roadmap/scripts/roadmap.py; [ -f "$RM" ] || RM="$HOME/.claude/skills/roadmap/scripts/roadmap.py"
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
