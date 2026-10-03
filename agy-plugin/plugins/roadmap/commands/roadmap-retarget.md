---
description: Re-stamp roadmap items onto another version (e.g. consolidate shipped work into one release)
argument-hint: --to <version> (--from <versions> | --plan <ids>)
---

Move existing items to a different version with the **roadmap** skill. Target: $ARGUMENTS

Typical use: fold work spread across versions (v1.0.0–v1.6.0) into a single consolidated
release **on a branch**, leaving mainline untouched.

1. Branch first (the CLI only edits roadmap state — git is yours):
   ```
   git checkout -b release-1.0.0
   ```
2. Retarget. Pick **one** selector:
   - by source versions: `python3 <roadmap.py> retarget --to 1.0.0 --from 1.0.0,1.3.0,1.6.0`
   - by item ids: `python3 <roadmap.py> retarget --to 1.0.0 --plan 3,8`

   This rewrites each item's `version` (config + plan frontmatter), re-renders `ROADMAP.md`
   and **both changelogs** — `CHANGELOG.md` (public) and `CHANGELOG.internal.md` — with
   everything now grouped under `--to`, and prunes dates for emptied versions. Each item
   keeps its `note` and `audience`, so the consolidated version's changelog reads exactly as
   the originals did, just merged under one heading (public notes stay public, internal-only
   work stays in the roll-up line). It moves items **regardless of done-state** and does
   **not** change `currentVersion`.
3. After consolidating, give the merged section a final read with `/roadmap:changelog` — once
   many versions collapse into one, you may want to tighten or reorder the public notes.
4. Commit the consolidated roadmap:
   ```
   git add -A && git commit -m "consolidate shipped work into v1.0.0"
   ```

To drop or combine items instead of re-versioning them, use `/roadmap:remove` or `merge`.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
