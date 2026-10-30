# Antigravity (`agy`) Plugins

Native [Google Antigravity](https://antigravity.google) (`agy`) plugins packaging the **roadmap** planning/tracking skill and the cost-tiered **agent** fleet into deployable units.

## Plugins Included

1. **`roadmap`** (`plugins/roadmap`):
   - **Skill**: Versioned `ROADMAP.md` + `.roadmap/` tracking driven by deterministic Python CLI.
   - **Slash Commands**: `/roadmap-init`, `/roadmap-status`, `/roadmap-next`, `/roadmap-plan`, `/roadmap-build`, `/roadmap-done`, `/roadmap-release`, etc.
   - **Lifecycle Hooks**:
     - `Stop`: Runs `roadmap sync` + drift check and reports back cleanly.
     - `PreInvocation`: Injects ephemeral roadmap sprint orientation into the session on start.
   - **Rules**: Injects roadmap discipline rules (`rules/AGENTS.md`) into active sessions.

2. **`agent`** (`plugins/agent`):
   - **Skill**: Guidance and orchestration patterns for delegating labor to cheaper model tiers.
   - **Subagent Fleet**: `executor`, `verifier`, `scout`, `mech-executor`, and `security-executor` available via `agy --agent <name>`.
   - **Rules**: Injects subagent delegation policy (`rules/AGENTS.md`).

## Quick Install

### Via `agy plugin install` (Direct)

```bash
# 1. Assemble the bundles
scripts/build-agy-plugin.sh

# 2. Install into Antigravity
agy plugin install ./agy-plugin/plugins/roadmap
agy plugin install ./agy-plugin/plugins/agent
```

### Via `install.sh --agy`

```bash
# Project-level install (into ./.agents and ./AGENTS.md)
./install.sh --agy

# Global install (into ~/.gemini/config/plugins/ via agy plugin install)
./install.sh --agy --global
```

## Directory Structure

```text
agy-plugin/
├── .agents/plugins/
│   └── marketplace.json      # Discovered marketplace manifest
├── plugins/
│   ├── roadmap/
│   │   ├── plugin.json       # Manifest (version stamped from skills/roadmap/VERSION)
│   │   ├── hooks.json        # Stop + PreInvocation hooks
│   │   ├── rules/AGENTS.md   # Merged roadmap discipline rules
│   │   ├── commands/         # Flat slash commands (/roadmap-*)
│   │   └── skills/roadmap/   # Bundled skill (scripts, templates, references)
│   └── agent/
│       ├── plugin.json       # Manifest (version stamped from skills/agent/VERSION)
│       ├── rules/AGENTS.md   # Merged orchestration policy
│       ├── agents/           # Subagents (executor, verifier, scout, etc.)
│       └── skills/agent/     # Bundled agent skill
```

## Verifying Installation

Verify that the plugins are recognized:

```bash
agy plugin list
agy agents
agy plugin validate ./agy-plugin/plugins/roadmap
agy plugin validate ./agy-plugin/plugins/agent
```
