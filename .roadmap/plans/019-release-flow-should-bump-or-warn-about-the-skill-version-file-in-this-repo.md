---
id: 19
title: Release flow should bump or warn about the skill VERSION file in this repo
type: chore
version: 0.17.0
status: planned
created: 2026-08-21
---

# Plan 19: Release flow should bump or warn about the skill VERSION file in this repo
> Type: chore · Target: v0.17.0
> Spec: [notes](../notes/2026-08-20-release-flow-should-bump-or-warn-about-the-skill-version-file-in-this-repo.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** stop VERSION drift (found at 0.14.2 while cutting 0.16.0). In THIS repo, `release` should keep skills/roadmap/VERSION in step: when the CLI detects it is running from its own source repo (VERSION file sibling to the running script), `release --version X` updates VERSION to the version being cut and prints what it did; elsewhere no change.
- **Out of scope:** no generic packaging/publish pipeline; installed skills untouched.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** rmlib/ops.py release() (self-repo detection + VERSION write), tests
- **Schema/interface changes:** none
- **Downstream impact:** validate_skills.py from plan 15 can also assert VERSION == last cut version (only if trivial)

## ✅ Acceptance
- **Passes when:** running release in a scratch repo that mimics the source layout bumps VERSION to the cut version; running in a normal project leaves everything alone
- **Passes when:** regression test covers both cases
- **Fails if:** release behavior changes for installed-skill users

## 🚶 Step-by-Step Checklist
- [ ] Step 1: self-repo detection + VERSION write on release + tests -> target: ops.py + tests
