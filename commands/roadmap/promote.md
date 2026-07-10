---
description: Promote an Idea Incubator bullet into a tracked, versioned roadmap plan
argument-hint: <match text | empty to list> [--type feature|bug|refactor|chore]
---

Lift a parked Idea Incubator idea into a tracked plan using the **roadmap** skill.
Target: $ARGUMENTS

1. Run `python3 <roadmap.py> status` to confirm the project is initialized.
2. List incubator bullets if the user did not pick one:
   - Read the **Idea Incubator** section of `ROADMAP.md`, or
   - Try `python3 <roadmap.py> promote` with no selector — it lists bullets when several exist.
3. Classify **type** (feature | bug | refactor | chore) and target **version** (semver:
   bug → patch, feature → minor, breaking → major). Draft a public `--note` when the
   item is user-facing.
4. Promote (exactly one selector when multiple bullets exist):
   - by substring: `python3 <roadmap.py> promote --match "<text>" --type <T> [--version V] [--note "..."] [--audience public|internal]`
   - by 1-based index: `python3 <roadmap.py> promote --index N --type <T> ...`
   - sole bullet: `python3 <roadmap.py> promote --type <T> ...`
5. Open the new plan file the CLI printed, fill scope / blueprint / checklist (or link a
   Spec / Detailed plan), then continue with `/roadmap:build` / `/roadmap-build` or
   `/roadmap:next` / `/roadmap-next`.
6. Commit the roadmap change.

The CLI removes only the promoted bullet from the incubator and registers a real plan
under `.roadmap/plans/`. Long-form notes files linked from the bullet are left in place
(link them from the plan if useful).

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.

**Agent slash names:** Claude Code → `/roadmap:promote`; Grok → `/roadmap-promote`.
Arguments after the command replace `$ARGUMENTS` (Claude) or are passed as the user message (Grok).
