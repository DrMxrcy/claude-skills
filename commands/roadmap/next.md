---
description: Build the next unfinished (unblocked) item — quality-first multi-agent
---

Pick up the next piece of roadmap work using the **roadmap** skill.

This is **one item, high quality, then stop** — the ideal unit for focused work.
For a whole version with the same quality gates, use `/roadmap:build <ver> --auto` /
`/roadmap-build <ver> --auto` instead.

## Steps

1. Run `python3 <roadmap.py> next` (or `next --json`). Picks the lowest `order`/id
   unfinished item in the **current version** whose `dependsOn` targets are complete.
2. If `No unfinished unblocked items.`:
   - Version truly done → suggest `/roadmap:review` / `/roadmap-review` then release.
   - Items blocked → show `status`; finish blockers or `next --force` only if the user asks.
   Stop.
3. Build that **single item** with the **same quality-first multi-agent protocol as
   `/roadmap:build` / `/roadmap-build`** (full detail in the skill’s
   `references/quality-build.md`):

   | Phase | Who | What |
   |---|---|---|
   | Research | `explore` (optional, background OK) | Map files; read-only |
   | Implement | One `general-purpose` subagent | TDD for this step only |
   | Spec review | Fresh subagent | Diff vs plan/spec → fix until ✅ |
   | Quality review | Fresh subagent | Maintainability/tests → fix until ✅ |
   | Verify + check | **Parent only** | Real tests → `check --plan <id> --step <n>` → commit code+roadmap |

   Prefer superpowers `subagent-driven-development` when installed. **Parent only** runs
   `roadmap.py`. No parallel implementers on the same tree. Never hand-edit `ROADMAP.md`.

4. When the item is 100%, **stop** and report — run `/roadmap:next` / `/roadmap-next`
   again for the following item (or switch to `/roadmap-build <ver> --auto` to chain).

**Agent slash names (always cite both — Grok does not load colon forms):**
- Claude: `/roadmap:next` · Grok: **`/roadmap-next`** · Either: `/roadmap next`
- **No `--auto` on next.** One item then stop. To chain: `/roadmap-build <version> --auto`
  or `/roadmap:build <version> --auto`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
