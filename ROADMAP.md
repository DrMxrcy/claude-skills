# 🗺️ Roadmap: claude-skills

## 💡 Idea Incubator
- Upgrade must not write into a gitignored scripts dir without git add -f or a refusal
<!-- Free-form; sync never rewrites this region. ONE bullet per idea (`roadmap.py idea`).
     Long write-ups (brainstorms, review findings) go to .roadmap/notes/ files and get linked. -->
<!-- roadmap:auto:start -->
**Current version: v0.19.0**

## 📊 Versions

### [x] v0.14.1 — 100% · 1 item · shipped 2026-07-22 ([history](CHANGELOG.internal.md))

### [x] v0.14.2 — 100% · 1 item · shipped 2026-07-22 ([history](CHANGELOG.internal.md))

### [x] v0.15.0 — 100% · 6 items · shipped 2026-07-23 ([history](CHANGELOG.internal.md))

### [x] v0.16.0 — 100% · 5 items · shipped 2026-08-20 ([history](CHANGELOG.internal.md))

### [x] v0.17.0 — 100% · 6 items · shipped 2026-08-21 ([history](CHANGELOG.internal.md))

### [x] v0.18.0 — 100% · 6 items · shipped 2026-10-21 ([history](CHANGELOG.internal.md))

### [ ] v0.19.0 — 81%
- [ ] **#28 Council review: plan review and merge gate by multiple agent CLIs** `feature` — 0% ([plan](.roadmap/plans/028-council-review-plan-review-and-merge-gate-by-multiple-agent-clis.md))
- [x] **#29 Adversarial review skill: multi-CLI review with triage from Claude Code** `feature` — 100% ([plan](.roadmap/plans/029-adversarial-review-skill-multi-cli-review-with-triage-from-claude-code.md))
- [x] **#30 Honest in-flight tracking: claim branch/stage/verdict per item, branch progress and stage filters in status and dashboard** `feature` — 100% ([plan](.roadmap/plans/030-honest-in-flight-tracking-claim-branch-stage-verdict-per-item-branch-progress-and-stage-filters-in-status-and-dashboard.md))
- [x] **#31 Dashboard: trunk plus branches always the default view, URL in every refresh log line, and full pages for each plan and idea** `feature` — 100% ([plan](.roadmap/plans/031-dashboard-trunk-plus-branches-always-the-default-view-url-in-every-refresh-log-line-and-full-pages-for-each-plan-and-idea.md))

### [x] v0.20.0 — 100%
- [x] **#27 Parallel-safe roadmap builds: per-item worktrees, fresh-session orchestration, pending-decision handoff and per-item token spend** `feature` — 100% ([plan](.roadmap/plans/027-parallel-safe-roadmap-builds-per-item-worktrees-fresh-session-orchestration-pending-decision-handoff-and-per-item-token-spend.md))

### [ ] v0.21.0 — 38%
- [x] **#32 Batch claims, a landed stage, and bulk check-off from claims** `feature` — 100% ([plan](.roadmap/plans/032-batch-claims-a-landed-stage-and-bulk-check-off-from-claims.md))
- [x] **#33 Numbered slot reservations: reserve the next migration (or any numbered sequence) per plan, with clash detection** `feature` — 100% ([plan](.roadmap/plans/033-numbered-slot-reservations-reserve-the-next-migration-or-any-numbered-sequence-per-plan-with-clash-detection.md))
- [x] **#34 Rulings: record dated decisions on a plan from the CLI and show them on the dashboard** `feature` — 100% ([plan](.roadmap/plans/034-rulings-record-dated-decisions-on-a-plan-from-the-cli-and-show-them-on-the-dashboard.md))
- [x] **#35 check refuses steps on bug plans whose Observed/Root cause are still the template** `feature` — 100% ([plan](.roadmap/plans/035-check-refuses-steps-on-bug-plans-whose-observed-root-cause-are-still-the-template.md))
- [x] **#36 Worktree map: status --worktrees and a dashboard worktree panel with safe-to-remove marks** `feature` — 100% ([plan](.roadmap/plans/036-worktree-map-status-worktrees-and-a-dashboard-worktree-panel-with-safe-to-remove-marks.md))
- [ ] **#37 Dashboard lane board: columns per lane with cards for branch, sha, verdict and last note, plus verdict and branch filter chips** `feature` — 0% ([plan](.roadmap/plans/037-dashboard-lane-board-columns-per-lane-with-cards-for-branch-sha-verdict-and-last-note-plus-verdict-and-branch-filter-chips.md))
- [x] **#38 Run log: record merge-gate and trunk suite runs from the CLI, shown as a gate timeline and trunk health tile** `feature` — 100% ([plan](.roadmap/plans/038-run-log-record-merge-gate-and-trunk-suite-runs-from-the-cli-shown-as-a-gate-timeline-and-trunk-health-tile.md))
- [x] **#39 Auto-collapse shipped versions in ROADMAP.md instead of a length warning on every call** `chore` — 100% ([plan](.roadmap/plans/039-auto-collapse-shipped-versions-in-roadmap-md-instead-of-a-length-warning-on-every-call.md))
- [ ] **#40 Claim owners and a work-in-progress limit** `feature` — 0% ([plan](.roadmap/plans/040-claim-owners-and-a-work-in-progress-limit.md))
- [ ] **#41 Branch conflict risk: show which open branches change the same files** `feature` — 0% ([plan](.roadmap/plans/041-branch-conflict-risk-show-which-open-branches-change-the-same-files.md))
- [ ] **#42 Scope drift per branch: flag changes outside the files a plan lists** `feature` — 0% ([plan](.roadmap/plans/042-scope-drift-per-branch-flag-changes-outside-the-files-a-plan-lists.md))
- [ ] **#43 Acceptance ledger: mark each acceptance bullet passed with evidence, and require it for done** `feature` — 0% ([plan](.roadmap/plans/043-acceptance-ledger-mark-each-acceptance-bullet-passed-with-evidence-and-require-it-for-done.md))
- [ ] **#44 Version forecast: estimate each open version's finish date from recent pace** `feature` — 0% ([plan](.roadmap/plans/044-version-forecast-estimate-each-open-version-s-finish-date-from-recent-pace.md))
- [ ] **#45 Digest: what landed, moved, stalled and got blocked since a given time** `feature` — 0% ([plan](.roadmap/plans/045-digest-what-landed-moved-stalled-and-got-blocked-since-a-given-time.md))
- [ ] **#46 Waiting steps and split retarget: time-gated checks no longer hold up a release or drag the whole feature to the next version** `feature` — 0% ([plan](.roadmap/plans/046-waiting-steps-and-split-retarget-time-gated-checks-no-longer-hold-up-a-release-or-drag-the-whole-feature-to-the-next-version.md))
- [ ] **#47 Bug routing: a bug command that fixes in-flight plans in place or files a linked bug item, and an incubator that refuses bugs** `feature` — 0% ([plan](.roadmap/plans/047-bug-routing-a-bug-command-that-fixes-in-flight-plans-in-place-or-files-a-linked-bug-item-and-an-incubator-that-refuses-bugs.md))
- [ ] **#48 All-projects dashboard home: every roadmap project on one page, registered automatically** `feature` — 0% ([plan](.roadmap/plans/048-all-projects-dashboard-home-every-roadmap-project-on-one-page-registered-automatically.md))
- [ ] **#49 Dashboard navigation: version pages, dependency graph, full-text search, keyboard shortcuts and copy-command buttons** `feature` — 0% ([plan](.roadmap/plans/049-dashboard-navigation-version-pages-dependency-graph-full-text-search-keyboard-shortcuts-and-copy-command-buttons.md))
- [ ] **#50 Dashboard resilience and polish: reconnect banner, tab-title alerts, light theme, fast first paint** `feature` — 0% ([plan](.roadmap/plans/050-dashboard-resilience-and-polish-reconnect-banner-tab-title-alerts-light-theme-fast-first-paint.md))
<!-- roadmap:auto:end -->
