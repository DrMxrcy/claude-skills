---
id: 61
title: test_agy_cli_plugin_validate expects [ok] but agy 1.4.6 prints Validation passed
type: bug
version: 0.19.0
status: done
created: 2026-10-29
---

# 🐛 Plan 61: test_agy_cli_plugin_validate expects [ok] but agy 1.4.6 prints Validation passed
> Type: bug · Target: v0.19.0

## 🔍 Symptom & Reproduction
- **Observed:** agy plugin validate exits 0 and prints '✔ Validation passed with 6 warnings'; test asserts '[ok]' in stdout and fails
- **Expected:** both bundled agy plugins validate on agy 1.4.6, and the agent plugin's 6 subagents load.
- **Repro steps:** `bash scripts/build-agy-plugin.sh && agy plugin validate agy-plugin/plugins/agent` fails with "validation failed: 6 errors". Explore/scout/verifier have a comma-string `tools:` ("cannot unmarshal !!str into []string"); executor/mech-executor/security-executor have Claude model aliases ("Invalid model tier opus/haiku"). agy skips every agent, so the fleet never loads in agy. The roadmap plugin passes, but agy now prints "Validation passed" where the test expects "[ok]".

## 🩺 Root Cause
- **Culprit:** `scripts/build-agy-plugin.sh` copies the Claude-format fleet (`skills/agent/.claude/agents/*.md`) verbatim; `tests/test_agy_plugin.py` matches the old "[ok]" text.
- **Why:** agy's agent frontmatter needs `tools` as a YAML list and `model` as an agy tier (`pro`, `flash`, `flash_lite`, `inherit`; probed against agy 1.4.6). Fix: the build converts frontmatter on copy (opus/sonnet → pro, haiku → flash, other values → inherit; comma `tools:` → YAML list). The Claude source files don't change. The test accepts either success text.

## ✅ Acceptance
- **Passes when:** the repro steps above no longer reproduce the symptom
- **Passes when:** the regression test fails on the old code and passes on the fix
- **Fails if:** the Claude-side agents in `skills/agent/.claude/agents/` change, any other test in tests/test_agy_plugin.py breaks, or agy validation still reports errors. Warnings (unknown plugin.json fields, commands not loaded, SKILL.md size) are out of scope: see the parked idea.

## 🛠️ Checklist
- [x] Step 1: Write a reproduction test
  > evidence: new tests fail on old build (2 failed), pass on fix (7 passed); agy plugin validate agent: 0 errors, 6 agents; verifier (sonnet) CONFIRMED, rebuild deterministic (2026-10-29)
- [x] Step 2: Apply the fix
  > evidence: new tests fail on old build (2 failed), pass on fix (7 passed); agy plugin validate agent: 0 errors, 6 agents; verifier (sonnet) CONFIRMED, rebuild deterministic (2026-10-29)
- [x] Step 3: Verify suite is green
  > evidence: new tests fail on old build (2 failed), pass on fix (7 passed); agy plugin validate agent: 0 errors, 6 agents; verifier (sonnet) CONFIRMED, rebuild deterministic (2026-10-29)

## ⚖️ Rulings

- **Ruling (2026-10-29, owner):** agy has one strong tier for both executor and verifier (opus and sonnet both map to pro), so the mixed-model review split is lost inside agy. Accepted for now; revisit with the parked agy plugin restructure idea.
