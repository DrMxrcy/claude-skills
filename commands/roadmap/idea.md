---
description: Park an idea in the Idea Incubator (one bullet; long write-ups become linked note files)
argument-hint: <idea title or description>
---

Park a stray idea with the **roadmap** skill — without bloating `ROADMAP.md`. Idea: $ARGUMENTS

1. Distill the idea to a **one-line title** (plain language, no prose walls).
2. If there is meaningful long-form content — a brainstorm write-up, deferred review
   findings, an option analysis, a phase sketch — save it as the idea's **body** so it
   lands in a linked `.roadmap/notes/<date>-<slug>.md` file instead of inline:
   - `python3 <roadmap.py> idea --title "<one-liner>" --body-file <path>` (or `--body "<text>"`)
   - Title only (no long content): `python3 <roadmap.py> idea --title "<one-liner>"`
3. This appends ONE bullet under the **Idea Incubator** heading in `ROADMAP.md`,
   linking the notes file when one was written.
4. Commit the roadmap change.

Rules of thumb:
- The incubator is a *parking lot*, not a document: one bullet per idea, always.
- Never paste brainstorm output, review findings, or multi-paragraph analyses into
  `ROADMAP.md` — give them a notes file (or a spec under `docs/`) and link it.
- When an idea is prioritized, promote it with `/roadmap:plan` and delete its bullet.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill at a
fixed path; resolve it once and reuse `$RM`:

```bash
RM=.claude/skills/roadmap/scripts/roadmap.py; [ -f "$RM" ] || RM="$HOME/.claude/skills/roadmap/scripts/roadmap.py"
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
