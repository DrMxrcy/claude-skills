---
description: Remove a tracked roadmap item (archive its plan, demote it to the Idea Incubator)
argument-hint: <plan id>
---

Remove a tracked item with the **roadmap** skill — the clean alternative to hand-editing
`.roadmap/config.json`. Target: $ARGUMENTS

1. Run `python3 <roadmap.py> status` to confirm the id and title.
2. `python3 <roadmap.py> remove --plan <id>`. This:
   - archives `.roadmap/plans/<id>-*.md` to `.roadmap/archive/` (recoverable),
   - drops the item from the registry and clears any `dependsOn` that pointed at it,
   - leaves a breadcrumb under the **Idea Incubator** in `ROADMAP.md`
     (`- (was #<id>) <title> ([archived plan](.roadmap/archive/...))`) linking the kept plan,
   - re-syncs the dashboard + `CHANGELOG.md`.
3. Commit the roadmap change.

Use this for stray, duplicated, or abandoned items. To **consolidate** two items into one
instead of dropping work, use `merge` (see `/roadmap:reevaluate`).

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill at a
fixed path; resolve it once and reuse `$RM`:

```bash
RM=.claude/skills/roadmap/scripts/roadmap.py; [ -f "$RM" ] || RM="$HOME/.claude/skills/roadmap/scripts/roadmap.py"
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
