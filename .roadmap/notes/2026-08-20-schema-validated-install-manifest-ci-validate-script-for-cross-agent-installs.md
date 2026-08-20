# Schema-validated install manifest + CI validate script for cross-agent installs

From cursor/plugins research: every plugin ships .cursor-plugin/plugin.json validated against a checked-in JSON Schema (schemas/plugin.schema.json) plus scripts/validate-plugins.mjs CI gate. For roadmap/claude-skills: a small manifest schema (name, version, skills/hooks paths, per-agent minimums) + validate script in CI would machine-check install layout for Claude/Grok/Codex instead of ad-hoc directory conventions. See https://github.com/cursor/plugins schemas/.
