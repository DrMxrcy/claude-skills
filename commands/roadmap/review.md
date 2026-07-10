---
description: Verify a completed version/phase against its specs and code-review before release
argument-hint: <version | empty for current>
---

Audit a roadmap version before releasing it, using the **roadmap** skill. Target: $ARGUMENTS
(default: the current version from `status`).

This is the **quality gate before ship** — same bar as the quality-first build protocol,
applied to the whole version.

1. Run `python3 <roadmap.py> status` and list the target version's items. Confirm each is
   100% on the dashboard (if not, send unfinished work back to `/roadmap:build` /
   `/roadmap-build` — do not release partial work).
2. **Spec conformance** — for each item, open its plan file and any linked **Spec** /
   **Detailed plan**. For every checklist step, verify it is *actually implemented in the
   codebase* (not merely checked off) and matches the spec's intent. Prefer a dedicated
   **spec-review subagent** (fresh context) per item or for the version.
   Flag anything missing, partial, or drifted from the spec.
3. **Code review** — review the version's changes for bugs and quality:
   - Prefer a dedicated **quality-review subagent**, superpowers `requesting-code-review`,
     or the repo's `/code-review` / `/review`.
   - Otherwise review the diff since the version began against the specs.
4. **Report** a per-item verdict: ✅ done & matches spec · ⚠️ partial · ❌ missing — plus any
   bugs or spec deviations found.
5. If gaps exist, propose fixes or `/roadmap:build` / `/roadmap-build` the unfinished steps.
   Only once the phase is clean, suggest `python3 <roadmap.py> release --version <next>`
   (and confirm public `note` / `audience` via `/roadmap:changelog` / `/roadmap-changelog`).

**Agent slash names:** Claude Code → `/roadmap:review`; Grok → `/roadmap-review`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.**

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
