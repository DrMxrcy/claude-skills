---
id: 2
title: Consolidate Codex hooks into config.toml
type: bug
version: 0.14.2
status: done
created: 2026-07-22
---

# 🐛 Plan 2: Consolidate Codex hooks into config.toml
> Type: bug · Target: v0.14.2

## 🔍 Symptom & Reproduction
- **Observed:** Codex warns when roadmap hooks are installed in `hooks.json` while another
  integration already defines hooks in `config.toml`.
- **Expected:** A Codex install uses one hook representation and preserves hooks owned by
  other integrations.
- **Repro steps:** Add any `[[hooks.Stop]]` entry to Codex `config.toml`, run the existing
  roadmap Codex installer, then start Codex.

## 🩺 Root Cause
- **Culprit:** The Codex installer reuses the Claude JSON hook writer and targets
  `.codex/hooks.json` unconditionally.
- **Why:** Current Codex supports hooks in `config.toml` and warns when both that file and
  `hooks.json` define the same configuration layer.

## 🛠️ Checklist
- [x] Step 1: Add coverage for consolidating existing JSON hooks into Codex TOML
- [x] Step 2: Install roadmap hooks into a managed `config.toml` block, migrate JSON hooks,
  and make bare `$roadmap` return a command menu
- [x] Step 3: Run installer, roadmap, plugin, and server test suites
