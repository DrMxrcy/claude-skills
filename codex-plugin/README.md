# Roadmap — Codex plugin

The roadmap skill packaged as an official [OpenAI Codex](https://developers.openai.com/codex)
plugin: a `plugin.json` manifest that bundles the roadmap **skill** and its lifecycle
**hooks** (Stop → sync + drift-check, SessionStart → orient) in one installable unit.

This is the packaged counterpart to `install.sh --codex` (which scatters the same
pieces into `~/.codex`). Use whichever you prefer; the plugin route shows up in the
Codex `/plugins` UI and installs via the marketplace flow.

## Layout

```
codex-plugin/
├── .agents/plugins/
│   └── marketplace.json        # discovered manifest; source ./plugins/roadmap (rel. to root)
└── plugins/roadmap/
    ├── plugin.json             # manifest (version stamped from skills/roadmap/VERSION)
    ├── hooks.json              # Stop + SessionStart, paths via ${CLAUDE_PLUGIN_ROOT}
    └── skills/roadmap/         # bundled at build time — NOT committed (gitignored)
```

> Codex discovers a marketplace at `<root>/.agents/plugins/marketplace.json`, so the
> manifest lives there (a root-level `marketplace.json` is not picked up).

## Build & install

```bash
# 1. Assemble the bundle (copies skills/roadmap in, stamps the version)
scripts/build-codex-plugin.sh

# 2. Register this local marketplace and install the plugin
codex plugin marketplace add ./codex-plugin
codex plugin add roadmap@claude-skills
```

Then start a Codex session — the roadmap skill is discoverable and the Stop /
SessionStart hooks fire. Roadmap discipline rules still live in `AGENTS.md`
(add them per-project with `install.sh --codex --project`, or globally with
`install.sh --codex --global`).

> The ChatGPT desktop app cannot load filesystem plugins — this is Codex CLI only.
