---
id: 22
title: Antigravity agy plugin packaging and CLI installer support
type: feature
version: 0.18.0
status: done
created: 2026-10-02
---

# Plan 22: Antigravity agy plugin packaging and CLI installer support
> Type: feature · Target: v0.18.0

## 🎯 Target Scope & Boundaries
- **Core objective:** Full Antigravity (`agy`) support across the repository: package `roadmap` and `agent` as native Antigravity plugins under `agy-plugin/` (skills, commands converted to skills, lifecycle hooks, rules, and subagent fleet), update hook scripts (`roadmap-sync.sh` and `roadmap-orient.sh`) to support AGY's JSON hook lifecycle and environment, add `scripts/build-agy-plugin.sh` and tests in `tests/test_agy_plugin.py`, and add `--agy`/`--antigravity` flag to `install.sh`.
- **Out of scope:** Modifying the agy binary itself; external cloud marketplace publishing (local install and repo marketplace supported).

## 🏗️ Architectural Blueprint
- **Files to create:**
  - `agy-plugin/README.md`
  - `agy-plugin/.agents/plugins/marketplace.json`
  - `agy-plugin/plugins/roadmap/plugin.json`
  - `agy-plugin/plugins/roadmap/hooks.json`
  - `agy-plugin/plugins/roadmap/rules/AGENTS.md`
  - `agy-plugin/plugins/agent/plugin.json`
  - `agy-plugin/plugins/agent/rules/AGENTS.md`
  - `scripts/build-agy-plugin.sh`
  - `tests/test_agy_plugin.py`
- **Files to modify:**
  - `skills/roadmap/hooks/roadmap-sync.sh`: support AGY Stop hook contract (stdin JSON with `workspacePaths`, stdout `{}`) while retaining Claude/Codex compatibility
  - `skills/roadmap/hooks/roadmap-orient.sh`: support AGY PreInvocation contract (`invocationNum: 1` ephemeral orientation) while retaining Claude/Codex compatibility
  - `install.sh`: add `--agy` / `--antigravity` flag supporting project (`./.agents`) and global (`agy plugin install` / `~/.gemini/config/`) installations
  - `README.md`: document AGY installation and usage alongside Claude, Grok, and Codex
- **Schema/interface changes:**
  - `install.sh` accepts `--agy` / `--antigravity`
  - `agy plugin validate` passes on `agy-plugin/plugins/roadmap` and `agy-plugin/plugins/agent`
- **Downstream impact:** Enables native Antigravity CLI and IDE users to install and run the roadmap tracking discipline and agent fleet seamlessly.

## ✅ Acceptance
- **Passes when:** `scripts/build-agy-plugin.sh` builds `agy-plugin/plugins/roadmap` and `agy-plugin/plugins/agent` with synchronized versions, bundled skills, rules, commands, and subagents.
- **Passes when:** `agy plugin validate agy-plugin/plugins/roadmap` and `agy plugin validate agy-plugin/plugins/agent` pass with exit code 0 and all components recognized.
- **Passes when:** `agy plugin install agy-plugin/plugins/roadmap` successfully installs into AGY, lifecycle hooks execute without errors, and commands/skills are discoverable.
- **Passes when:** `./install.sh --agy` runs and correctly wires skills, hooks, and rules for AGY projects and globally.
- **Passes when:** `pytest tests/test_agy_plugin.py` and the full pytest test suite (324+ tests) pass cleanly.
- **Fails if:** AGY hook execution throws protojson errors or fails to detect `.roadmap/` in workspace paths, or regressions are introduced for Claude/Codex/Grok.

## 🚶 Step-by-Step Checklist
- [x] Step 1: Update hook scripts for AGY lifecycle contracts (Stop JSON stdout, PreInvocation ephemeral orientation, workspacePaths detection) -> target: skills/roadmap/hooks/
  > evidence: Updated roadmap-sync.sh and roadmap-orient.sh to support AGY Stop and PreInvocation contracts (2026-10-03)
- [x] Step 2: Create agy-plugin package structure, build script (scripts/build-agy-plugin.sh), and assemble roadmap and agent plugins -> target: agy-plugin/, scripts/
  > evidence: Created agy-plugin structure, marketplace manifest, plugins for roadmap and agent, build-agy-plugin.sh, and successfully built and validated both plugins (2026-10-03)
- [x] Step 3: Add automated tests in tests/test_agy_plugin.py and verify agy plugin validation and hook execution -> target: tests/test_agy_plugin.py
  > evidence: Added test_agy_plugin.py covering build, manifest versions, AGY hooks format, runtime hook contracts, marketplace, and agy plugin validate CLI (2026-10-03)
- [x] Step 4: Add --agy/--antigravity support to install.sh and document in README.md -> target: install.sh, README.md, agy-plugin/README.md
  > evidence: Added --agy/--antigravity flag to install.sh supporting project and global installs, added unit tests, documented in README.md and agy-plugin/README.md (2026-10-03)

