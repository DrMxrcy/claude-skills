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
- **Quality-first build** (default for `/roadmap:build` **·** `/roadmap-build`, including `--auto`): per step, one `executor` implementer (opus) → **spec review** by `scout` (haiku, acceptance list) → **one** `verifier` quality review (opus; second pass only for high-risk steps) → parent runs the tests → `check`. Never spawn an unlabeled `general-purpose` child — it inherits the frontier model. The parent owns every `roadmap.py` call; `--auto` skips *user* pauses only, never reviews or tests.

### Invoking it
- **Resolve the CLI once:** probe `.claude|.grok|.agents` skills paths (project, then `$HOME`) for `skills/roadmap/scripts/roadmap.py`.
- **Slash names differ per agent:** Claude Code `/roadmap:build`, Grok Build **hyphen only** `/roadmap-build`, Codex `$roadmap build`. **Never quote colon-only names to a Grok user** — they do not appear in its menu; write `/roadmap:build` **·** `/roadmap-build` or the bare `/roadmap build`.
- **`--auto` is a `build` flag only.** **`next` has no `--auto`** — it does exactly one item and stops; chain items with `build --auto`.

### Long-form (load on demand, don't inline here)
- Build protocol, agent switching / rate-limit resume, incubator hygiene, release + changelog flow: the roadmap skill's `SKILL.md` and `references/quality-build.md`.
- Files, config settings, and invariants: the skill's `references/state-model.md`.
<!-- roadmap:rules:end -->
