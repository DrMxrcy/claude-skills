# Example Project

Your own project notes and conventions live here (build/test commands, code style,
architecture pointers, etc.). The roadmap skill never touches this area.

The block below is what the roadmap skill adds — via `install.sh` or the first
`roadmap init` / `/roadmap:init` / `/roadmap-init` / `$roadmap init`. It is inserted idempotently between the
`roadmap:rules` markers, so your content above and below is always preserved. The same
block is also written to `AGENTS.md` for agent-neutral readers (Grok, Codex, Cursor, …).

<!-- roadmap:rules:start -->
## Roadmap tracking
This project uses the **roadmap** skill to stay on-task and ship **high-quality** code. Truth lives in **git** — `ROADMAP.md` + `.roadmap/` (plans, config) + `CHANGELOG*.md` — written by the `roadmap.py` CLI only. This block is the compact core; load the long-form files below when you need the detail.

### Core rules
- **Orient first:** run `roadmap.py orient` (or roadmap status, or read `ROADMAP.md`) before writing code. A SessionStart hook may do it for you.
- **Nothing off-roadmap:** features/bugs get a plan first (`/roadmap:plan` **·** `/roadmap-plan`); park stray ideas (`/roadmap:idea` **·** `/roadmap-idea`) instead of building them.
- **One item at a time**, with an active plan file in `.roadmap/plans/` — no functional code without one, no multitasking across features/bugs. The plan's Spec / ✅ Acceptance is the definition of done; the checklist is only the tracker.
- **Test before you check:** run the real build/tests for a step, then `roadmap.py check`.
- **Micro-commit** code + roadmap together right after every checked step, so an interrupted session loses at most the in-flight step.
- **Never hand-edit `ROADMAP.md`** or `.roadmap/` state — CLI only (`/roadmap:done` **·** `/roadmap-done`); never keep a private plan outside `.roadmap/`.
- **Quality-first build** (default for `/roadmap:build` **·** `/roadmap-build`, including `--auto`): per step, one `executor` implementer (opus) → **spec review** by `scout` (haiku, acceptance list) → **one** `verifier` quality review (opus; second pass only for high-risk steps) → parent runs the tests → `check`. Never spawn an unlabeled `general-purpose` child — it inherits the frontier model. **No native subagents** (Codex, Gemini, Kimi, Copilot, restricted sessions): the parent implements as sole writer and runs spec + quality review as two separate passes itself (or via permitted read-only reviewers); record real reviewers and independence limits in the evidence, never fabricate independent review; same test gates and micro-commits; stay in the host's native tools. The parent owns every `roadmap.py` call; `--auto` skips *user* pauses only, never reviews or tests.

### Invoking it
- **Resolve the CLI once:** probe `.claude|.grok|.agents` skills paths (project, then `$HOME`) for `skills/roadmap/scripts/roadmap.py`.
- **Slash names differ per agent:** Claude Code `/roadmap:build`, Grok Build **hyphen only** `/roadmap-build`, Codex `$roadmap build`. **Never quote colon-only names to a Grok user** — they do not appear in its menu; write `/roadmap:build` **·** `/roadmap-build` or the bare `/roadmap build`.
- **`--auto` is a `build` flag only.** **`next` has no `--auto`** — it does exactly one item and stops; chain items with `build --auto`.

### Long-form (load on demand, don't inline here)
- Build protocol, agent switching / rate-limit resume, incubator hygiene, release + changelog flow: the roadmap skill's `SKILL.md` and `references/quality-build.md`.
- Files, config settings, and invariants: the skill's `references/state-model.md`.
<!-- roadmap:rules:end -->
