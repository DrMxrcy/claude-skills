# Changelog

## v0.21.0 — (in progress)

### ✨ New
- (pending) Move many items through review and merge in one command, and tick them off together once they reach main.
- (pending) Plans can reserve the next migration number, so two branches never pick the same one.
- (pending) Decisions and owner approvals get recorded on the plan and shown on its page.
- (pending) Steps can no longer be checked off on a plan that is still the empty template.
- (pending) See every worktree at a glance, which branch it holds, and which ones are safe to clean up.
- (pending) A board view on the dashboard shows every item in its column, from planned to done.
- (pending) Merge gates and test runs are recorded, so everyone can see what ran, what passed, and how far the trunk is ahead.

### ⚡ Improved
- (pending) The roadmap stops warning about file length once shipped versions fold away on their own.

## v0.20.0 — 2026-10-23

_Plus behind-the-scenes performance and reliability work._

## v0.19.0 — (in progress)

### ✨ New
- Built-but-unmerged work shows its real state instead of 0%.
- (pending) The live roadmap page opens on everything, and every plan and idea gets its own page.

## v0.18.0 — 2026-10-21

A roomier dashboard and a sharper crew. The live roadmap page now has tabs for your plan, your idea incubator, and your changelog. Antigravity joins the list of supported coders with native plugins. Behind the scenes, the review crew got cheaper and more careful: a different model now checks each change at full attention, and every helper gets exactly the tools its job needs. Happy shipping.

## v0.17.0 — 2026-08-21

Trust, but verify: finished steps can now carry proof of the tests that passed, release dates always match when work really wrapped, and your setup stays tidy across every AI coder you use.

## v0.16.0 — 2026-08-20

### ✨ New
- Items now show friendly typed IDs like FEAT-12 and BUG-7 in status and next — and you can reference them either way when marking work done.
- Plan templates now include an Acceptance section so reviews check work against explicit pass/fail criteria.
- Find things faster: filter status by type or version, and search titles, notes, and plans from the CLI.

## v0.15.0 — 2026-07-23

_Plus behind-the-scenes performance and reliability work._

## v0.14.2 — 2026-07-22

### 🐛 Fixed
- Codex starts cleanly without duplicate hook configuration warnings.

## v0.14.1 — 2026-07-22

### 🐛 Fixed
- Roadmap now opens correctly from Codex using its native skill picker.
