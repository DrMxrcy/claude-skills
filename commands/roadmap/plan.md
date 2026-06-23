---
description: Brainstorm an idea into a tracked, versioned roadmap plan
argument-hint: <idea or feature description>
---

Turn this idea into a tracked roadmap item using the **roadmap** skill:

$ARGUMENTS

Follow the skill's intake phase:
1. Classify the type: `feature` | `bug` | `refactor` | `chore`, and pick the **target
   version** by semver — bug → patch (x.y.Z), feature → minor (x.Y.0), breaking change or a
   whole new phase → major (X.0.0). Pass it with `--version` (omit for the current version).
2. Research as needed — use **context7** for library/API docs and any project **MCPs**
   (e.g. codegraph) for impact analysis. Degrade gracefully if unavailable.
3. If the superpowers `brainstorming`/`writing-plans` skills are installed, use them to
   design the approach before scaffolding.
4. Scaffold the plan file:
   `python3 <roadmap.py> new --type <T> --title "<title>" [--version <V>] --note "<one-liner>" [--audience public|internal]`
   - `--note` is a plain-language, user-benefit sentence (no jargon, no vendor/tool names,
     no file paths or issue refs) — it becomes the **public** `CHANGELOG.md` / App Store
     "What's New" line. The CLI warns if a public note reads internal.
   - `--audience` decides which changelog the item lands in: `public` (the curated
     `CHANGELOG.md`) or `internal` (`CHANGELOG.internal.md`, the full dev log). Omit it to
     accept the type default — `feature`/`bug` → public, `refactor`/`chore` → internal —
     then override when judgment differs (a user-invisible feature is `internal`; a
     user-felt fix from a refactor is `public`). Internal items still appear in the public
     changelog only as one rolled-up "behind-the-scenes" line.
5. Fill in the plan's **Target Scope**, **Architectural Blueprint**, and a checklist of
   tiny, testable steps.
6. If `brainstorming`/`writing-plans` produced a spec or detailed plan document, save it
   under `docs/superpowers/` and add `**Spec:**` / `**Detailed plan:**` links near the top
   of the plan file — `/roadmap:build` follows those links for the implementation detail.
7. The CLI auto-syncs `ROADMAP.md`. Show the new plan file and the updated dashboard.
