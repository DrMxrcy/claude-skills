---
description: Reconcile the roadmap with work already done outside the commands
argument-hint: <plan id | empty for current version>
---

Bring the roadmap in line with code that was written **without** `/roadmap:build` /
`/roadmap-build` (the dashboard only auto-updates when `check` runs, so ad-hoc work can
leave it behind). Also the recovery path when `drift-check` nudges after off-roadmap commits.

Target: $ARGUMENTS (default: every unfinished item in the current version).

1. Run `python3 <roadmap.py> status` to find the target item(s).
2. For each item, read its plan file (`.roadmap/plans/<id>-*.md`) and its checklist. Inspect
   the **codebase and recent git history** (`git log --oneline`, `git diff`) to determine
   which steps are *actually implemented*. **Run/confirm the relevant tests** before counting
   a step as done — don't check off on assumption (same quality bar as build).
3. Prefer a fresh **explore/review subagent** to verify "done vs plan" when the diff is large.
4. Check off each genuinely-completed step:
   `python3 <roadmap.py> check --plan <id> --step <n>` (or `--all-done` for a finished item).
   Parent owns the CLI. This auto-syncs `ROADMAP.md`.
5. Report the updated `status`, and commit the roadmap update. If anything is only partly
   done, leave it unchecked and say what remains — then continue with `/roadmap:next` /
   `/roadmap-next` or `/roadmap:build` / `/roadmap-build` under the quality-first protocol.

Going forward, use build/next so steps are checked off as you go — `catchup` is recovery,
not the normal loop.

**Agent slash names:** Claude Code → `/roadmap:catchup`; Grok → `/roadmap-catchup`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
