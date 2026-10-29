---
id: 60
title: adversarial-review: diff target caps context before redaction, so a secret cut at the cap can leak a prefix
type: bug
version: 0.19.0
status: done
created: 2026-10-29
---

# 🐛 Plan 60: adversarial-review: diff target caps context before redaction, so a secret cut at the cap can leak a prefix
> Type: bug · Target: v0.19.0
> Spec: [notes](../notes/2026-10-29-adversarial-review-diff-target-caps-context-before-redaction-so-a-secret-cut-at-the-cap-can-leak-a-prefix.md)

## 🔍 Symptom & Reproduction
- **Observed:** for every build_target kind (diff, branch, version, plan, repo), `_build_target` caps the context with `_cap` (run_review.py ~810/823/836/846/863) and only then does `build_target` run `redact_text`. If a token straddles MAX_CONTEXT_BYTES, the cut leaves a fragment that no longer matches the redaction pattern, so its prefix reaches every member prompt and the `--prompt-only` prompt.
- **Expected:** a secret is redacted in full, or doesn't appear at all, wherever the cap falls.
- **Repro steps:** dirty tree whose diff puts a bare `ghp_` + 36-char token across the 90000-byte cap; run `run_review.py diff --prompt-only`; the prompt contains most of the token.

## 🩺 Root Cause
- **Culprit:** `build_target` / `_build_target` in skills/adversarial-review/scripts/run_review.py.
- **Why:** cap then redact. Fix: `_build_target` returns uncapped context, and `build_target` redacts then caps. Prompt bytes don't change when no secret straddles the cap.

## ✅ Acceptance
- **Passes when:** the repro steps above no longer reproduce the symptom
- **Passes when:** the regression test fails on the old code and passes on the fix
- **Fails if:** any existing adversarial-review test breaks, the context can exceed MAX_CONTEXT_BYTES plus the cap's truncation marker, or the redaction counts change for inputs without a cap-straddling secret.

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
  > evidence: regression test fails on HEAD, passes on fix; pytest 115 passed; verifier (sonnet) CONFIRMED no other cap-then-redact path (2026-10-29)
- [x] Step 2: Apply the fix
  > evidence: regression test fails on HEAD, passes on fix; pytest 115 passed; verifier (sonnet) CONFIRMED no other cap-then-redact path (2026-10-29)
- [x] Step 3: Verify suite is green
  > evidence: regression test fails on HEAD, passes on fix; pytest 115 passed; verifier (sonnet) CONFIRMED no other cap-then-redact path (2026-10-29)

## ⚖️ Rulings

- **Ruling (2026-10-29, owner):** Accept redact-then-cap even though target.redacted can now count a secret that sits past the cap and never reaches the prompt. Overcounting in summary.md is the safe direction; exact counting would need offset mapping for no safety gain. This relaxes the Fails-if line on redaction counts for over-cap inputs only.
