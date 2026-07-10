---
description: Build the next unfinished (unblocked) item in the current version
---

Pick up the next piece of roadmap work using the **roadmap** skill.

1. Run `python3 <roadmap.py> next` (or `next --json`). This picks the lowest
   `order`/id unfinished item in the **current version** whose `dependsOn` targets
   are all 100% complete. Blocked items are skipped with a stderr note.
2. If it prints `No unfinished unblocked items.`:
   - If the version is truly done → suggest `/roadmap:review` / `/roadmap-review` then
     `/roadmap:release` / `/roadmap-release`.
   - If items remain but are blocked → show `status` and either finish blockers or
     `python3 <roadmap.py> next --force` only if the user explicitly wants to override.
   Stop.
3. Otherwise build that single item exactly like `/roadmap:build <id>` / `/roadmap-build <id>`:
   - Optional: `python3 <roadmap.py> deps-check --plan <id>` (warns on incomplete deps).
   - Read its plan file and any linked **Spec** / **Detailed plan** and follow them.
   - Execute the checklist step-by-step (prefer `subagent-driven-development`, else
     `executing-plans`, else direct TDD). Build/tests must pass before each `check`.
   - `python3 <roadmap.py> check --plan <id> --step <n>` after each step; commit code +
     roadmap together.
4. When the item is done, stop at a checkpoint and report — run `/roadmap:next` /
   `/roadmap-next` again for the following item.

This "build exactly one item, then stop" shape is the ideal iteration body for the
`ralph-loop` plugin if you want an unattended phase build — see the autonomous section of
`/roadmap:build` / `/roadmap-build`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.

**Agent slash names:** Claude Code → `/roadmap:next`; Grok → `/roadmap-next`.
