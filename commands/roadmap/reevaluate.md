---
description: Audit the codebase against the roadmap — merge dupes, drop stale, resequence
argument-hint: <version | empty for the whole roadmap>
---

Reconcile the roadmap's STRUCTURE and COMPLETENESS against reality. This is broader than
the other two reconcilers:
- `/roadmap:sync` only re-renders `ROADMAP.md` from existing checkboxes (never reads code).
- `/roadmap:catchup` only checks off steps of items that already exist.
- `/roadmap:reevaluate` (this) audits the whole roadmap vs the codebase and reorganizes it.

Target: $ARGUMENTS (default: the whole roadmap).

1. Run `python3 <roadmap.py> status --json` to load items, versions, progress,
   dependencies, and order.
2. Scan the **codebase and git history** (use a code-intelligence MCP such as codegraph if
   one is available, but do not require it). Compare against the roadmap to find:
   - **Missed / untracked work** — features, modules, endpoints in code with no item.
   - **Done-but-untracked** — whole features finished with no plan.
   - **Duplicates / overlap** — multiple items covering the same work that should be one.
   - **Stale / obsolete items** — planned things the code shows were superseded or dropped.
   - **Gaps** — plans missing obvious steps the code implies (tests, error handling).
   - **Sequencing** — items whose prerequisites are scheduled later.
3. Present an **advisory report** grouped by the categories above. Do NOT mutate yet.
4. After the user approves, apply the accepted changes via the CLI only:
   - add missed items: `roadmap.py new …`
   - record finished work: `roadmap.py check --plan <id> --all-done`
   - **merge duplicates/overlap into one:** `roadmap.py merge --into <keepId> --from <ids>`
     (appends the others' checklist steps to the keeper, deletes their plans, retargets
     dependencies — then add any missing steps to the keeper)
   - express ordering: `roadmap.py depends --plan <id> --on <ids>` and/or
     `roadmap.py reorder --version <v> --order <ids>`
   - never delete a user's plan automatically — flag stale items and let the user decide.
5. Show the updated `status` and commit the roadmap changes.

Run this periodically as the backlog grows; `catchup` is the progress reconcile, this is
the structural one.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
