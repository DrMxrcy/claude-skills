# Changelog (internal)

_Full work log — every item, including internal/dev work. The curated public changelog is CHANGELOG.md._

## v0.16.0 — (in progress)

### ✨ New
- (pending) Finished versions get cut automatically: when every item in the current version is done, the roadmap offers (or runs) the release for you before new work starts.

## v0.15.0 — (in progress)

### ✨ New
- The changelog now warns before developer-facing work (API keys, posting APIs, admin tooling) slips into the public notes.
- Worktree-aware serve/orient: detect git worktrees, warn when dashboard serves a stale branch's roadmap vs main checkout
- Combined all-worktrees view as the serve dashboard default
- Live worktree re-discovery in serve — added/deleted checkouts update the dashboard

### 🐛 Fixed
- (pending) Serve reprints unchanged status on every file touch — skip identical payloads

## v0.14.2 — 2026-07-22

### 🐛 Fixed
- Codex starts cleanly without duplicate hook configuration warnings.

## v0.14.1 — 2026-07-22

### 🐛 Fixed
- Roadmap now opens correctly from Codex using its native skill picker.
