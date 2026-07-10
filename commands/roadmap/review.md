---
description: Verify a completed version/phase against its specs and code-review the work before release
argument-hint: <version | empty for current>
---

Audit a roadmap version before releasing it, using the **roadmap** skill. Target: $ARGUMENTS
(default: the current version from `status`).

1. Run `python3 <roadmap.py> status` and list the target version's items. Confirm each is
   100% on the dashboard.
2. **Spec conformance** — for each item, open its plan file and any linked **Spec** /
   **Detailed plan** (e.g. under `docs/`). For every checklist step, verify it is *actually
   implemented in the codebase* (not merely checked off) and matches the spec's intent.
   Flag anything missing, partial, or drifted from the spec.
3. **Code review** — review the version's changes for bugs and quality:
   - Prefer the superpowers `requesting-code-review` skill or the repo's `/code-review`.
   - Otherwise review the diff since the version began against the spec.
4. **Report** a per-item verdict: ✅ done & matches spec · ⚠️ partial · ❌ missing — plus any
   bugs or spec deviations found.
5. If gaps exist, propose fixes or `/roadmap:build` the unfinished steps. Only once the
   phase is clean, suggest `python3 <roadmap.py> release --version <next>`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
