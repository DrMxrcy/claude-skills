# Changelog (internal)

_Full work log — every item, including internal/dev work. The curated public changelog is CHANGELOG.md._

## v0.18.0 — 2026-08-28

### ✨ New
- The live dashboard now has tabs — browse your roadmap, the Idea Incubator, and the changelog without leaving the page.

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
