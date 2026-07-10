---
description: Multi-coder handoff brief — sync state when switching Claude ↔ Grok (or any agent)
---

Prepare a clean handoff so the next AI coder continues from the **same** roadmap state.
No arguments required.

1. Run `python3 <roadmap.py> handoff` (or `handoff --json`).
2. Act on any warnings it prints:
   - **Uncommitted changes** → commit code + roadmap together (or stash). Do not switch agents with a dirty tree if the other agent needs those edits.
   - **Drift** (commits since last check-off) → `/roadmap:catchup` / `/roadmap-catchup` after verifying tests, then commit.
   - **Stale skill rules** (project `skillVersion` ≠ installed) → `python3 <roadmap.py> upgrade`.
3. If collaborating or switching machines: `git push` so the other session can `git pull`.
4. On the **next** agent (Claude Code, Grok Build, etc.):
   - `git pull`
   - `python3 <roadmap.py> handoff` (or rely on SessionStart `orient`)
   - Continue with `/roadmap:next` / `/roadmap-next` or `/roadmap:build` / `/roadmap-build`
     under the quality-first multi-agent protocol.

**Shared source of truth (always in git):**

| Path | Role |
|---|---|
| `ROADMAP.md` | Dashboard (CLI-owned auto region) |
| `.roadmap/config.json` | Registry, versions, dependsOn, last_seen_sha |
| `.roadmap/plans/*` | Checklists / progress |
| `CHANGELOG.md` / `CHANGELOG.internal.md` | Rendered on sync |
| `CLAUDE.md` + `AGENTS.md` rules block | Same discipline for every agent |

Never keep a private parallel plan in chat memory only — if it matters, it's a plan item,
incubator idea, or notes file under `.roadmap/`.

**Agent slash names:** Claude Code → `/roadmap:handoff`; Grok → `/roadmap-handoff`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
