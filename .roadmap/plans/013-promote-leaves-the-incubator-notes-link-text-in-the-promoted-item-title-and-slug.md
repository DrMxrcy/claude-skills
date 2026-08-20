---
id: 13
title: promote leaves the incubator notes-link text in the promoted item title and slug
type: bug
version: 0.16.0
status: planned
created: 2026-08-20
---

# Plan 13: promote leaves the incubator notes-link text in the promoted item title and slug
> Type: bug · Target: v0.16.0

## 🎯 Target Scope & Boundaries
- **Symptom:** Promoting a bullet that carries a linked notes file (created via `idea --body`) produces an item titled `<title> ([notes](.roadmap/notes/...))` — the markdown link lands in the title, slug, and plan filename (observed promoting plans 10–12 on 2026-08-20).
- **Root cause to confirm:** incubator promote path uses the raw bullet text as title instead of stripping the trailing notes link.
- **Core objective:** Strip the `([notes](...))` suffix from the title/slug and instead carry the notes link into the generated plan (Spec line), preserving the reference.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** skills/roadmap/scripts/incubator.py (promote), tests
- **Schema/interface changes:** none
- **Downstream impact:** matches how `idea` writes bullets; `--match` should still match bullets with or without the link text

## 🚶 Step-by-Step Checklist
- [ ] Step 1: strip notes-link suffix from promoted title/slug; inject the notes link as a Spec line in the new plan; regression test promoting a linked bullet -> target: incubator.py + tests
