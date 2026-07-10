---
description: Reconcile the roadmap with work already done outside the commands
argument-hint: <plan id | empty for current version>
---

Bring the roadmap in line with code that was written **without** `/roadmap:build` (the
dashboard only auto-updates when `check` runs, so ad-hoc work can leave it behind).

Target: $ARGUMENTS (default: every unfinished item in the current version).

1. Run `python3 <roadmap.py> status` to find the target item(s).
2. For each item, read its plan file (`.roadmap/plans/<id>-*.md`) and its checklist. Inspect
   the **codebase and recent git history** (`git log --oneline`, `git diff`) to determine
   which steps are *actually implemented*. Run/confirm the relevant tests before counting a
   step as done — don't check off on assumption.
3. Check off each genuinely-completed step:
   `python3 <roadmap.py> check --plan <id> --step <n>` (or `--all-done` for a finished item).
   This auto-syncs `ROADMAP.md`.
4. Report the updated `status`, and commit the roadmap update. If anything is only partly
   done, leave it unchecked and say what remains.

Going forward, use `/roadmap:build` / `/roadmap:next` so steps are checked off as you go —
`catchup` is the recovery path, not the normal loop.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
