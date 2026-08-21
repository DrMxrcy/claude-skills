---
id: 16
title: "Completion-promise gate: parent greps an explicit done marker before allowing check"
type: feature
version: 0.17.0
status: done
created: 2026-08-21
---

# Plan 16: Completion-promise gate: parent greps an explicit done marker before allowing check
> Type: feature · Target: v0.17.0
> Spec: [notes](../notes/2026-08-20-completion-promise-gate-parent-greps-an-explicit-done-marker-before-allowing-check.md)

## 🎯 Target Scope & Boundaries
- **Core objective:** optional evidence gate on `check`: `check --plan N --step M --evidence "<text>"` records the completion evidence (verify command + result, or subagent DONE marker) into the plan file next to the step; a `settings.requireEvidence` (default false) makes `check` refuse without `--evidence`. Portable across Grok/Codex — plain CLI flag, no host-agent plumbing.
- **Out of scope:** no hook system, no <promise> tag parsing of agent transcripts, no auto-capture of command output.

## 🏗️ Architectural Blueprint
- **Files to create:** none
- **Files to modify:** roadmap.py (check argparse), rmlib/ops.py or wherever check flips boxes (append evidence as an indented sub-line under the step, format that parse.py's STEP_RE cannot mistake for a step), SKILL.md + quality-build.md (build loop passes evidence at check time), tests
- **Schema/interface changes:** `settings.requireEvidence` (bool, default false) — additive
- **Downstream impact:** merges plan 20's intent (execution metadata) — same mechanism

## ✅ Acceptance
- **Passes when:** `check --evidence "pytest -q: 287 passed"` writes the line under the step in the plan file; progress counting unchanged
- **Passes when:** with `requireEvidence: true`, bare `check` exits non-zero with a clear message; default behavior unchanged
- **Fails if:** evidence lines alter step counts, status derivation, or generated ROADMAP/changelog output

## 🚶 Step-by-Step Checklist
- [x] Step 1: --evidence flag + plan-file append + settings.requireEvidence gate + tests -> target: scripts + tests
  > evidence: uv run pytest tests/ -q: 312 passed; spec review mutation-tested 4 mutations killed (2026-08-21)
- [x] Step 2: document in SKILL.md command ref + build-loop docs (parent passes evidence when checking) -> target: docs
  > evidence: doc reviewer verified every claim against ops.py behavior; suite 312 passed (2026-08-21)
