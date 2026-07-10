---
description: Groom the Idea Incubator & free-form region — one linked bullet per idea, prose into notes files
argument-hint: (no args)
---

Groom the **free-form region** of `ROADMAP.md` — the Idea Incubator plus any phase
sketches, deferred/conditional sections, and stray prose outside the `roadmap:auto`
markers — back to skimmable, with the **roadmap** skill.

This is the ONE sanctioned direct edit of `ROADMAP.md`: scripts never rewrite the
free-form region, so the grooming judgment is yours. **Never touch anything between
`<!-- roadmap:auto:start -->` and `<!-- roadmap:auto:end -->`** — that region belongs to
`sync`.

1. Run `python3 <roadmap.py> tidy` (add `--json` for structured output) — a deterministic,
   report-only hygiene analysis: over-long bullets, nested sub-bullet blocks, bullets that
   duplicate tracked items, prose paragraphs outside any bullet, size warnings.
2. Read the free-form region, `.roadmap/notes/`, and `python3 <roadmap.py> status --json`,
   then draft a grooming plan:
   - **Prose-wall bullet or nested block** → write the FULL body to
     `.roadmap/notes/<date>-<slug>.md` and shrink the bullet to one line:
     `- <title> ([notes](.roadmap/notes/<file>.md))`.
   - **Multi-idea section** (phase sketches, "deferred / conditional" lists) → one linked
     bullet per idea, same treatment; a shared write-up may live in one notes file.
   - **Duplicate of a tracked item** → replace with `→ #<id>` or drop the bullet; if it is
     really untracked work, promote it instead (`roadmap.py promote` / `/roadmap:plan`).
   - **Shipped or stale residue** → flag it for the user; never silently delete.
3. **Lossless by default:** every line removed from `ROADMAP.md` must land verbatim in a
   notes file (or already exist in one) — tidy reorganizes, it does not destroy. Only the
   user may approve true deletions.
4. Interactive session: present the plan, apply on approval. Non-interactive (`--auto`,
   hooks, autonomous run): apply the lossless moves directly and leave
   flagged-for-deletion items in place with a note in your summary.
5. Re-run `python3 <roadmap.py> tidy` to confirm clean (or explain what remains), run
   `python3 <roadmap.py> sync`, and commit the roadmap + notes files together.

Rules of thumb (same as `/roadmap:idea` · `/roadmap-idea`):
- The incubator is a *parking lot*, not a document: one bullet per idea, always.
- Long-form content lives in `.roadmap/notes/` (or a spec under `docs/`) and gets linked.
- Run this whenever `status` warns the free-form region has outgrown its bounds.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
