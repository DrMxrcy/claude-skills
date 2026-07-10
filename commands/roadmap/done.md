---
description: Mark a roadmap step or item as done and resync the dashboard
argument-hint: <plan id> [step number]
---

Mark progress on a roadmap item: $ARGUMENTS

Before marking a step done, make sure its tests/build pass. Then flip the checkbox via the
roadmap CLI (it auto-syncs the dashboard):

- One step: `python3 <roadmap.py> check --plan <id> --step <n>`
- Whole item: `python3 <roadmap.py> check --plan <id> --all-done`
- Undo: add `--undo`

When an item finishes (`--all-done`), set it up for the changelog while it's fresh: confirm
its audience (`python3 <roadmap.py> audience --plan <id> --to public|internal`) and, if it's
public, give it a plain-language user-facing note (`note --plan <id> --text "..."`). The CLI
warns if a public item ships without a note or with internal-sounding wording. Full curation
can wait for `/roadmap:changelog` / `/roadmap:release`, but a one-liner now saves rework.

After updating, commit the code and the roadmap changes together in one micro-commit.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
