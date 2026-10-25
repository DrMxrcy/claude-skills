# Changelog (internal)

_Full work log — every item, including internal/dev work. The curated public changelog is CHANGELOG.md._

## v0.21.0 — 2026-10-25

### ✨ New
- Move many items through review and merge in one command, and tick them off together once they reach main.
- Plans can reserve the next migration number, so two branches never pick the same one.
- Decisions and owner approvals get recorded on the plan and shown on its page.
- Steps can no longer be checked off on a plan that is still the empty template.
- See every worktree at a glance, which branch it holds, and which ones are safe to clean up.
- A board view on the dashboard shows every item in its column, from planned to done.
- Merge gates and test runs are recorded, so everyone can see what ran, what passed, and how far the trunk is ahead.
- Each claimed item shows who is working on it, and the roadmap warns when too much is in flight at once.
- See which in-flight branches touch the same files, so merge order can be planned before the gate.
- Branches that wander outside their plan get flagged before review.
- Every acceptance line gets its own pass mark and evidence, so done means every line was checked.
- Each open version shows a forecast finish date based on how fast work has been moving.
- A short digest tells you what changed on the roadmap since you last looked.
- Steps that need time to pass, like a week of monitoring, can wait without holding up a release.
- Bugs always land in the right place: fixed inside the plan still being built, or tracked as their own item, never lost among ideas.
- One dashboard page lists every project you use the roadmap in, with no setup.
- Find anything fast: pages per version, a dependency map, search across every plan, and keyboard shortcuts.
- The dashboard reconnects on its own, flags problems in the browser tab, follows your light or dark setting, and opens faster.
- Steps can wait a few hours, or wait on a person such as a tester, with daily reminders until they are done.

### ⚡ Improved
- The roadmap stops warning about file length once shipped versions fold away on their own.
- A calmer dashboard: each fact appears once, pages lead with what matters now, and color only marks real problems.

## v0.20.0 — 2026-10-23

### ✨ New
- Respawn budget set to 4 respawns per step (5 attempts total). After that the step is BLOCKED and written to the handoff note.

## v0.19.0 — (in progress)

### ✨ New
- (pending) Adds a council of installed agent CLIs that reviews each plan before build and each diff before merge.
- Adversarial review skill: multi-CLI review with triage from Claude Code
- Built-but-unmerged work shows its real state instead of 0%.
- The live roadmap page opens on everything, and every plan and idea gets its own page.
- Chunked whole-repo review with model.md baseline, openusage budgeting, and resumable coverage
- (pending) OpenCode install target: roadmap and adversarial-review in ~/.config/opencode

### 🐛 Fixed
- bug --found-in writes the Fix step before refusing a claim held by another owner
- Leftovers: note error suggests a missing --audience flag; board copy commands lack the project under serve --all; board filters shared across projects
- Dashboard: header too tall, panels not collapsible, trunk health shows every past run as a red chip

### ⚡ Improved
- (pending) Agent fleet slimmed per fold-subagents guidance, gated on golden-task evals

## v0.18.0 — 2026-10-21

### ✨ New
- The live dashboard now has tabs — browse your roadmap, the Idea Incubator, and the changelog without leaving the page.
- Antigravity users can now install the roadmap and agent tools as native plugins, with the same commands and hooks as everywhere else.

### ⚡ Improved
- Haiku-first cost tiers: re-tier the agent fleet and slim the quality build loop
- Sole-writer fallback for AI coders without native subagents
- Mixed-model review: verifier on sonnet, opus or cross-provider second pass for high-risk steps
- Review-effort and cache-stable briefs: verifier sonnet/high, read-only tool scopes, inline plan bodies, diff-scoped re-verification

## v0.17.0 — 2026-08-21

### ✨ New
- Completion-promise gate: parent greps an explicit done marker before allowing check
- Per-role model mapping setting for the quality-first build loop

### 🐛 Fixed
- Version date stamped once and never re-stamped when the version reopens

### ⚡ Improved
- Schema-validated install manifest + CI validate script for cross-agent installs
- Split roadmap discipline rules into individually loadable principle skills
- Release flow should bump or warn about the skill VERSION file in this repo

## v0.16.0 — 2026-08-20

### ✨ New
- Finished versions get cut automatically: when every item in the current version is done, the roadmap offers (or runs) the release for you before new work starts.
- Items now show friendly typed IDs like FEAT-12 and BUG-7 in status and next — and you can reference them either way when marking work done.
- Plan templates now include an Acceptance section so reviews check work against explicit pass/fail criteria.
- Find things faster: filter status by type or version, and search titles, notes, and plans from the CLI.

### 🐛 Fixed
- promote leaves the incubator notes-link text in the promoted item title and slug

## v0.15.0 — 2026-07-23

### ✨ New
- The changelog now warns before developer-facing work (API keys, posting APIs, admin tooling) slips into the public notes.
- Worktree-aware serve/orient: detect git worktrees, warn when dashboard serves a stale branch's roadmap vs main checkout
- Combined all-worktrees view as the serve dashboard default
- Live worktree re-discovery in serve — added/deleted checkouts update the dashboard

### 🐛 Fixed
- Serve reprints unchanged status on every file touch — skip identical payloads
- The public changelog is now protected: unclassified work stays in the internal log, saving a public note requires an explicit audience, and internal-sounding wording is refused at save time.

## v0.14.2 — 2026-07-22

### 🐛 Fixed
- Codex starts cleanly without duplicate hook configuration warnings.

## v0.14.1 — 2026-07-22

### 🐛 Fixed
- Roadmap now opens correctly from Codex using its native skill picker.
