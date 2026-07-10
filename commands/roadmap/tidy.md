---
description: Groom the Idea Incubator & free-form region — notes files, curation vs the roadmap, optional externalize
argument-hint: [--externalize]
---

Groom the **free-form region** of `ROADMAP.md` — the Idea Incubator plus any phase
sketches, deferred/conditional sections, and stray prose outside the `roadmap:auto`
markers — back to skimmable, with the **roadmap** skill.

This is the ONE sanctioned direct edit of the free-form region: scripts never rewrite it,
so the grooming judgment is yours. **Never touch anything between
`<!-- roadmap:auto:start -->` and `<!-- roadmap:auto:end -->`** — that region belongs to
`sync`. If `settings.incubatorFile` is set, the incubator lives in that external file
(e.g. `.roadmap/IDEAS.md`) — groom there too.

1. Run `python3 <roadmap.py> tidy` (add `--json` for structured output) — a deterministic,
   report-only hygiene analysis: over-long bullets, nested sub-bullet blocks, bullets that
   duplicate tracked items, prose paragraphs outside any bullet, size warnings. Covers the
   external incubator file when one is configured.
2. **Format pass (lossless — apply freely):**
   - **Prose-wall bullet or nested block** → write the FULL body to
     `.roadmap/notes/<date>-<slug>.md` and shrink the bullet to one line:
     `- <title> ([notes](.roadmap/notes/<file>.md))`.
   - **Multi-idea section** (phase sketches, "deferred / conditional" lists) → one linked
     bullet per idea; a shared write-up may live in one notes file.
   - Every line removed must land verbatim in a notes file (or already exist in one) —
     this pass reorganizes, it never destroys.
3. **Curation pass (reevaluate ideas against the current roadmap — lossy, needs
   approval):** read `python3 <roadmap.py> status --json` plus recent git history, then
   for each idea bullet propose one of:
   - **Shipped / superseded** by a tracked item or commit → drop the bullet (cite the
     item id or commit).
   - **Duplicate / overlapping ideas** → merge into ONE bullet (union of their notes
     files, cross-linked).
   - **Ripe** (unblocked, fits the current version's theme) → promote it:
     `python3 <roadmap.py> promote --match "<title>" [--type T --version V]`.
   - **Still valid, still parked** → leave alone.
   Interactive session: present the proposals and apply on approval. Non-interactive
   (`--auto`, hooks, autonomous run): apply only merges whose bullets are verbatim-level
   duplicates; report the rest — never drop an idea without the user.
4. **Dashboard still too busy? Externalize the incubator:**
   `python3 <roadmap.py> tidy --externalize [PATH]` mechanically moves the whole
   incubator into `PATH` (default `.roadmap/IDEAS.md`), leaves one linked bullet in
   `ROADMAP.md`, and records `settings.incubatorFile` so `idea` / `promote` / `remove`
   target the new home automatically. Lossless and instant — offer it when the user
   wants ROADMAP.md to be a pure dashboard, or when the idea list stays long even after
   grooming.
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
