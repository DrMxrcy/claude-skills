---
description: Multi-coder resume brief — after switch, rate-limit, or crash (handoff optional)
---

Print a resume brief so any AI coder continues from the **same** roadmap state.
No arguments required. **You do not need a clean prior handoff** — this is also the
recovery path after rate limits, crashes, or killed sessions.

1. Run `python3 <roadmap.py> handoff` (or `orient` — lighter; SessionStart often runs orient).
2. Act on warnings:
   - **Uncommitted changes** → inspect `git status` / `git diff`. Commit code + roadmap
     together if the previous agent finished a step; otherwise finish or stash carefully.
   - **Drift** (commits since last check-off) → `/roadmap:catchup` / `/roadmap-catchup`
     after verifying tests, then commit.
   - **Stale skill rules** → `python3 <roadmap.py> upgrade`.
3. Continue from the **plan checklist** (next unfinished step), not from chat memory:
   `/roadmap:next` / `/roadmap-next` or `/roadmap:build` / `/roadmap-build`.

## Rate limit / no formal handoff

If Claude or Grok died mid-turn:

| What you still have | What to do |
|---|---|
| Committed steps | Already safe — `orient` shows **Next** |
| Uncommitted code on disk | Commit or finish the step on the new agent |
| Code done, checklist not checked | `/roadmap-catchup` after tests |
| Nothing on disk (pure chat ideas) | Lost — re-park with `/roadmap-idea` if still needed |

**Prevention:** after every successful `check`, micro-commit immediately. That way a
rate-limit loses at most the in-flight step, never a whole item.

## Shared source of truth (always in git)

| Path | Role |
|---|---|
| `ROADMAP.md` | Dashboard (CLI-owned auto region) |
| `.roadmap/config.json` | Registry, versions, dependsOn, last_seen_sha |
| `.roadmap/plans/*` | Checklists / progress |
| `CHANGELOG.md` / `CHANGELOG.internal.md` | Rendered on sync |
| `CLAUDE.md` + `AGENTS.md` rules block | Same discipline for every agent |

**Agent slash names:** Claude Code → `/roadmap:handoff`; Grok → `/roadmap-handoff`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
