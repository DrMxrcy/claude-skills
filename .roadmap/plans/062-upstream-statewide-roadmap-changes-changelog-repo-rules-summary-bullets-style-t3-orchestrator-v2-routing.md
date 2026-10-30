---
id: 62
title: Upstream statewide roadmap changes: changelog repo rules, summary+bullets style, T3 Orchestrator V2 routing
type: feature
version: 0.19.0
status: planned
created: 2026-10-30
---

# Plan 62: Upstream statewide roadmap changes: changelog repo rules, summary+bullets style, T3 Orchestrator V2 routing
> Type: feature · Target: v0.19.0

## 🎯 Target Scope & Boundaries
- **Core objective:** port the generic roadmap-skill changes made directly in statewide-app (/Users/jp/Desktop/Dev/statewide/statewide-app) back into this source repo, so the next install doesn't erase them. Source commits there: `b5a5cb34d` (changelog repo rules: settings internalTerms / internalPatterns / publicTerms, new disclosure and version tells), `db54b59db` (settings.changelogStyle `summary+bullets`), `1c6a015ee` (build loop: "Orchestrator V2 routing" for T3 Code in SKILL.md and references/quality-build.md).
- **Out of scope:** statewide's own `.roadmap/config.json` values (project data, not skill code); statewide's plan/changelog content; the adversarial-review model pins (already upstream in b1b38ef); installing anywhere (separate follow-up).

## 🏗️ Architectural Blueprint
- **Files to modify:** skills/roadmap/scripts/rmlib/changelog.py, skills/roadmap/scripts/rmlib/ops.py, skills/roadmap/scripts/roadmap.py, skills/roadmap/references/state-model.md, skills/roadmap/SKILL.md, skills/roadmap/references/quality-build.md, commands/roadmap-changelog.md, plus any mirrored copies the repo keeps (agy-plugin via scripts/build-agy-plugin.sh), plus tests under tests/.
- **Schema/interface changes:** new optional settings keys in .roadmap/config.json (internalTerms, internalPatterns, publicTerms, changelogStyle); documented in state-model.md with defaults that keep current behaviour.
- **Downstream impact:** apply statewide's diffs as patches (`git -C <statewide> show <sha> -- <paths>`), mapping `.claude/skills/roadmap` → `skills/roadmap` and `.agents/skills/roadmap` → `skills/roadmap`. Where this repo has moved on since statewide's copy (e.g. .opencode paths), keep both sides. Don't revert repo-newer code to statewide's older text.

## ✅ Acceptance
- **Passes when:** with no new settings keys, `roadmap.py changelog` output for this repo is byte-identical to before the port.
- **Passes when:** each new settings key has a test showing its effect (internalTerms/internalPatterns move a line internal, publicTerms keep one public, changelogStyle summary+bullets renders the summary and the public bullets).
- **Passes when:** `diff` of statewide's changed hunks against this repo shows every generic hunk present; SKILL.md and quality-build.md carry the "Orchestrator V2 routing" section.
- **Passes when:** `python3.11 -m pytest -q tests/` is green except the known agy plugin warnings test if any.
- **Fails if:** any newer repo-side change (OpenCode paths, plan 57-61 work) is lost, or the roadmap SKILL.md grows past what it already was by more than the routing paragraph.

## 🚶 Step-by-Step Checklist
- [ ] Step 1: Port changelog repo rules and changelogStyle (changelog.py, ops.py, roadmap.py, state-model.md, roadmap-changelog command) with tests -> target: skills/roadmap/scripts, commands/roadmap-changelog.md, tests/
- [ ] Step 2: Port Orchestrator V2 routing docs (SKILL.md, quality-build.md), rebuild agy plugin mirror -> target: skills/roadmap/SKILL.md, skills/roadmap/references/quality-build.md, agy-plugin/
