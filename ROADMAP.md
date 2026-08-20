# 🗺️ Roadmap: claude-skills

## 💡 Idea Incubator
- Filtered listing and search: status --type/--version filters, plus search and stats subcommands ([notes](.roadmap/notes/2026-08-19-filtered-listing-and-search-status-type-version-filters-plus-search-and-stats-subcommands.md))
- Optional execution metadata on check — record verify command and result per step ([notes](.roadmap/notes/2026-08-19-optional-execution-metadata-on-check-record-verify-command-and-result-per-step.md))
- Acceptance criteria section as first-class part of plan templates ([notes](.roadmap/notes/2026-08-19-acceptance-criteria-section-as-first-class-part-of-plan-templates.md))
- Typed human-readable ID prefixes (TSK-42, BUG-7) as display layer over int ids ([notes](.roadmap/notes/2026-08-19-typed-human-readable-id-prefixes-tsk-42-bug-7-as-display-layer-over-int-ids.md))
<!-- Free-form; sync never rewrites this region. ONE bullet per idea (`roadmap.py idea`).
     Long write-ups (brainstorms, review findings) go to .roadmap/notes/ files and get linked. -->
<!-- roadmap:auto:start -->
**Current version: v0.15.0**

## 📊 Versions

### [x] v0.14.1 — 100% · 1 item · shipped 2026-07-22 ([history](CHANGELOG.internal.md))

### [x] v0.14.2 — 100% · 1 item · shipped 2026-07-22 ([history](CHANGELOG.internal.md))

### [ ] v0.15.0 — 89%
- [x] **#3 Audience leak guard: DEMOTE tier for developer/API-surface work + lint gate when explicitly setting audience public** `feature` — 100% ([plan](.roadmap/plans/003-audience-leak-guard-demote-tier-for-developer-api-surface-work-lint-gate-when-explicitly-setting-audience-public.md))
- [x] **#4 Worktree-aware serve/orient: detect git worktrees, warn when dashboard serves a stale branch's roadmap vs main checkout** `feature` — 100% ([plan](.roadmap/plans/004-worktree-aware-serve-orient-detect-git-worktrees-warn-when-dashboard-serves-a-stale-branch-s-roadmap-vs-main-checkout.md))
- [x] **#5 Combined all-worktrees view as the serve dashboard default** `feature` — 100% ([plan](.roadmap/plans/005-combined-all-worktrees-view-as-the-serve-dashboard-default.md))
- [x] **#6 Live worktree re-discovery in serve — added/deleted checkouts update the dashboard** `feature` — 100% ([plan](.roadmap/plans/006-live-worktree-re-discovery-in-serve-added-deleted-checkouts-update-the-dashboard.md))
- [ ] **#7 Serve reprints unchanged status on every file touch — skip identical payloads** `bug` — 33% ([plan](.roadmap/plans/007-serve-reprints-unchanged-status-on-every-file-touch-skip-identical-payloads.md))
- [x] **#9 Internal notes can leak into the public changelog: unset-audience bugs default public and demote tells only advise** `bug` — 100% ([plan](.roadmap/plans/009-internal-notes-can-leak-into-the-public-changelog-unset-audience-bugs-default-public-and-demote-tells-only-advise.md))

### [x] v0.16.0 — 100%
- [x] **#8 Auto-release nudge: when current version hits 100%, prompt or auto-run roadmap release before starting next version** `feature` — 100% ([plan](.roadmap/plans/008-auto-release-nudge-when-current-version-hits-100-prompt-or-auto-run-roadmap-release-before-starting-next-version.md))
<!-- roadmap:auto:end -->
