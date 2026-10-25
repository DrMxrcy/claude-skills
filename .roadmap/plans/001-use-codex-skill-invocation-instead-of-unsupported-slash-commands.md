---
id: 1
title: Use Codex skill invocation instead of unsupported slash commands
type: bug
version: 0.14.1
status: done
created: 2026-07-22
---

# 🐛 Plan 1: Use Codex skill invocation instead of unsupported slash commands
> Type: bug · Target: v0.14.1

## 🔍 Symptom & Reproduction
- **Observed:** `install.sh --codex` copies command Markdown into `.codex/prompts` and
  tells users to run `/roadmap-*`, but current Codex does not discover those files as
  slash commands.
- **Expected:** Codex installs only the supported roadmap skill and tells users to invoke
  it with `$roadmap <action>` (or select it from Codex's skills UI).
- **Repro steps:** Run a project-scoped Codex install, start a fresh Codex session, and
  enter `/roadmap-status`; Codex treats it as an unknown slash command.

## 🩺 Root Cause
- **Culprit:** The Codex branch of `install.sh` assumes `.codex/prompts/*.md` creates
  dynamic slash commands.
- **Why:** Current Codex slash commands are a fixed built-in set. Installed skills are
  explicitly invoked with `$<skill-name>` instead.

## 🛠️ Checklist
- [x] Step 1: Add installer coverage proving Codex does not receive unsupported prompt files
- [x] Step 2: Update the installer and user-facing docs to use `$roadmap <action>` on Codex
- [x] Step 3: Run the installer and Codex plugin test suites
