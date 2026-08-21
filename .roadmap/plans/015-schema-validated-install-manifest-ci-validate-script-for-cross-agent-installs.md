---
id: 15
title: Schema-validated install manifest + CI validate script for cross-agent installs
type: chore
version: 0.17.0
status: planned
created: 2026-08-21
---

# Plan 15: Schema-validated install manifest + CI validate script for cross-agent installs
> Type: chore · Target: v0.17.0
> Spec: [notes](../notes/2026-08-20-schema-validated-install-manifest-ci-validate-script-for-cross-agent-installs.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** machine-checkable contract for the repo's install layout (inspired by cursor/plugins): one JSON Schema describing what a valid skill package looks like (SKILL.md present with name/description frontmatter, scripts/, templates/, commands mapping, VERSION file matching a semver), plus a stdlib-only validate script runnable locally and in CI that checks skills/roadmap/ (and other skills dirs) against it.
- **Out of scope:** no runtime manifest consumed by agents; no marketplace features; no new dependencies (validator is hand-rolled Python, not jsonschema lib).

## 🏗️ Architectural Blueprint
- **Files to create:** schemas/skill.schema.json (documentation-grade), scripts/validate_skills.py (stdlib only), CI workflow step if .github/workflows exists (check first)
- **Files to modify:** README or CONTRIBUTING mention (one line)
- **Schema/interface changes:** none to roadmap CLI
- **Downstream impact:** catches install-layout drift (like the VERSION mismatch found at v0.16.0 review)

## ✅ Acceptance
- **Passes when:** `python3 scripts/validate_skills.py` exits 0 on the current repo and non-zero with a named violation when a required file is removed or VERSION is not semver
- **Passes when:** validator has tests in the main suite
- **Fails if:** validator needs a third-party package

## 🚶 Step-by-Step Checklist
- [ ] Step 1: schema + validate_skills.py + tests -> target: schemas/, scripts/, tests
- [ ] Step 2: wire into CI if workflows exist, else document local run; README line -> target: .github/ or README
