---
description: Brainstorm an idea into a tracked, versioned roadmap plan
argument-hint: <idea or feature description>
---

Turn this idea into a tracked roadmap item using the **roadmap** skill:

$ARGUMENTS

Follow the skill's intake phase:
1. Classify the type: `feature` | `bug` | `refactor` | `chore`.
2. Research as needed — use **context7** for library/API docs and any project **MCPs**
   (e.g. codegraph) for impact analysis. Degrade gracefully if unavailable.
3. If the superpowers `brainstorming`/`writing-plans` skills are installed, use them to
   design the approach before scaffolding.
4. Scaffold the plan file:
   `python3 <roadmap.py> new --type <T> --title "<title>" [--version <V>]`
   (target a future version for work not slated for the current one).
5. Fill in the plan's **Target Scope**, **Architectural Blueprint**, and a checklist of
   tiny, testable steps.
6. If `brainstorming`/`writing-plans` produced a spec or detailed plan document, save it
   under `docs/superpowers/` and add `**Spec:**` / `**Detailed plan:**` links near the top
   of the plan file — `/roadmap:build` follows those links for the implementation detail.
7. The CLI auto-syncs `ROADMAP.md`. Show the new plan file and the updated dashboard.
