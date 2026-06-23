# roadmap v0.6.0 — "removal, live changelog & dependency wiring"

**Status:** Approved (design)
**Date:** 2026-06-22
**Skill:** `skills/roadmap`
**Target version:** next minor (→ `0.6.0`)

## Summary

Four interlocking changes to the roadmap CLI + commands, all sharing the same
`config.json` / `sync()` plumbing:

- **A. `remove`** — the missing path to drop a tracked item without hand-editing
  state. Archives the plan, drops it from the registry, and demotes it to the Idea
  Incubator.
- **B. Live changelog** — changelog generation moves out of `release()` (which the
  user never runs) and into `sync()`, so `CHANGELOG.md` is a rendered artifact that
  fills in as items complete. Includes a `--backfill` path to reconstruct history.
- **C. `depends`** — implement the documented-but-missing dependency setter that
  `reevaluate.md` already invokes and `merge_items()` already retargets.
- **D. Surface** the CLI-only verbs (`remove`, `depends`, `reorder`, `merge`) in
  `SKILL.md` + `README.md`, and slim/demote `release`.

All changes are backward-compatible. New `config.json` fields are optional and read
tolerantly. No migration step required.

## Motivation

- **No removal path.** The CLI has `merge` (folds sources into a keeper) but no
  standalone removal. Dropping a stray tracked item means hand-editing
  `config.json` *and* deleting a plan file — the exact "touch state by hand" the
  skill exists to prevent. The Idea Incubator is hand-editable but has no bridge
  *back out of* the tracker.
- **Changelog never gets written.** `write_changelog()` is called **only** from
  `release()` (roadmap.py:446). The user does not run `/roadmap:release` — it is not
  part of their workflow — so reaching 100% on an item or a whole version produces no
  user-facing changelog. The feature exists but is gated behind an unused command.
- **`depends` is half-wired.** `reevaluate.md` step 4 tells the agent to run
  `roadmap.py depends --plan <id> --on <ids>`, and `merge_items()` reads & retargets a
  `dependsOn` field (roadmap.py:368-376) — but **no `depends` subcommand exists** and
  **nothing ever sets `dependsOn`**. Following the documented reevaluate flow errors.
- **Discoverability.** `reorder`/`merge` are surfaced only inside `/roadmap:reevaluate`;
  there are no command files and no SKILL/README mentions.

## Architecture shift: changelog becomes a rendered artifact

Today the changelog is *imperatively appended* once, at release. The fix is to treat
`CHANGELOG.md` like the ROADMAP.md auto-region: **regenerated from `config.json` on
every `sync()`**, which already runs after `check`/`done`/`build`/`merge`/`reorder`/
`remove`. Generation is therefore decoupled from `release` entirely.

### Current-version resolution (open point ① — decided: derive)

`release` was the only thing that bumped `currentVersion`. With it out of the critical
path, `currentVersion` is **derived during `sync()`**:

- `currentVersion` = the **lowest** version number that still has incomplete items;
- when **all** items across all versions are complete, it is the **highest** version present.
- `config.currentVersion` remains as the persisted seed/fallback (used when there are
  no items yet, e.g. fresh init), but `sync()` overwrites it with the derived value
  whenever items exist.

Versions advance naturally because new items target higher versions via
`new --version`. No manual bump and no `release` are required to move forward.

## A. `remove` command — archive + demote to Incubator

CLI: `roadmap.py remove --plan <id>`

1. Refuse an unknown id (`ValueError`, exit 1).
2. If other items list this id in `dependsOn`, **warn** (print to stderr) but proceed,
   retargeting per step 5.
3. Move `.roadmap/plans/NNN-slug.md` → `.roadmap/archive/NNN-slug.md` (create
   `archive/` if absent; atomic). If the plan file is already missing, skip the move
   and continue (still drop from config).
4. Drop the item from `config["items"]`.
5. Clear/retarget `dependsOn`: remove the dropped id from every other item's
   `dependsOn` list (reuse the list-cleaning logic from `merge_items`; drop the key if
   the list becomes empty).
6. Append a stub line under the Idea Incubator marker in ROADMAP.md so the idea isn't
   lost: `- (was #N) <title>`.
7. `sync()`.

**Idea Incubator stub insertion.** The Incubator is free-form and outside the
`roadmap:auto` markers, so `sync()` never touches it. `remove` locates a heading whose
text contains "Idea Incubator" (case-insensitive) and inserts the stub immediately
after it. If no such heading exists, the stub is appended at end of file under a
freshly created `## 💡 Idea Incubator` heading. The insertion is done on the raw file
text **before** calling `sync()` (sync only rewrites the auto-region, preserving the
edit).

New command file `commands/roadmap/remove.md`. `nextId` is **not** decremented (ids are
never reused — archived plans keep their number).

## B. Live changelog

### `render_changelog(root) -> str`

Pure function of `config.json` + per-plan progress. Replaces the append-only
`write_changelog`.

- Group **all** versions (sorted by `_version_key`, newest first for display).
- Within a version, group items by section using the existing `TYPE_SECTION` /
  `SECTION_ORDER` map (✨ New / 🐛 Fixed / ⚡ Improved). Each line is the item's `note`
  (fallback: title).
- **Completed items** render as plain shipped lines. In a version that is **not yet
  100%**, the header is suffixed `(in progress)` and not-yet-complete items render as
  `- (pending) <label>`. When a version reaches 100%, the header is dated:
  `## v<ver> — <YYYY-MM-DD>` and no `(pending)` lines remain.
- **Date persistence (determinism).** Re-rendering must not change a date each run.
  `config.json` gains `versionDates: { "<ver>": "<ISO date>" }`. During `sync()`, when
  a version is observed at 100% and has no recorded date, today's date is stored.
  Render reads the stored date; it never recomputes for an already-dated version. A
  version that drops back below 100% (e.g. a new item added to it) keeps its stored
  date but renders `(in progress)` again until complete — and once complete again,
  reuses the stored date (stable).

### Wiring into `sync()`

`sync()`, after rewriting the ROADMAP.md auto-region, writes `CHANGELOG.md` from
`render_changelog()` (full-file overwrite — it owns the file). The leading `# Changelog`
title is preserved/created. Because `render_changelog` covers every version, no
information is lost on overwrite.

### `release()` slimmed

`release()` loses its `write_changelog` call and the `--no-changelog` flag. It retains:
optional explicit version pin and optional `git tag`. It is no longer required for a
changelog. The slash command + `build`/`next`/`review` wording is updated to present
`release` as optional (formal-cut / tagging only).

### `--backfill`

New CLI verb `changelog` (there is currently **no** `changelog` subcommand — it is
slash-only):

- `roadmap.py changelog` → triggers `sync()` and prints `CHANGELOG.md` (show/refresh).
- `roadmap.py changelog --backfill` → for every version with **no** entry in
  `versionDates`, if a matching `git tag v<ver>` exists, record that tag's commit date
  (`git log -1 --format=%cs v<ver>`) as the version date; otherwise leave undated
  (renders `(in progress)` / `(unreleased)` as appropriate). Then `sync()` + print.
  Running this once on a repo populates `CHANGELOG.md` for all historical versions from
  config. Items missing a user-facing `note` still render by title; the
  `/roadmap:changelog` doc continues to guide reconstructing notes from `git log`.

## C. `depends` command

CLI: `roadmap.py depends --plan <id> --on <ids>` (`--on` is a comma list;
`--clear` removes all deps for the plan).

- Validate that `<id>` and every id in `--on` exist; reject self-dependency.
- Set `config[item].dependsOn = [ids]` (dedup, preserve order). `--clear` removes the
  key.
- This is the setter `merge_items()`/`remove` already retarget and `reevaluate.md`
  already invokes. No render change needed beyond what already consumes `dependsOn`
  (none today — ordering display is a separate concern handled by `reorder`/`order`;
  `dependsOn` is advisory metadata consumed by reevaluate and retargeted by
  merge/remove). `next`/`build` ordering is unchanged in this spec (still id/`order`).

## D. Surface CLI verbs + docs

- New `commands/roadmap/remove.md`.
- `SKILL.md` + `README.md`: add `remove`, `depends`, `reorder`, `merge` to the command
  reference; note that changelog is now automatic and `release` is optional.
- `reevaluate.md`: unchanged behaviorally — it already calls `depends`; now it works.
- Bump `skills/roadmap/VERSION` to `0.6.0`.

## Data model changes (config.json)

All optional, additive:

- `dependsOn: number[]` (per item) — already read; now also written by `depends`.
- `versionDates: { [version: string]: string }` (top-level) — completion dates for
  deterministic changelog rendering.

Existing configs without these keys render exactly as before (no deps; all dates
computed lazily on first 100%).

## Error handling

- `remove`/`depends`: unknown id → `ValueError` → "Error: …" on stderr, exit 1
  (matches existing CLI convention).
- `remove` on a missing plan file: proceed with config/Incubator update (warn).
- `changelog --backfill` in a non-git repo or with no matching tags: silently leaves
  versions undated (no crash).
- `render_changelog` with zero items: writes a `# Changelog` stub with no sections.

## Testing

- `remove`: archives file, drops from config, retargets dependents, inserts Incubator
  stub (existing heading + no-heading cases), missing-file case, unknown-id error.
- Live changelog: item at 100% appears after `sync`; in-progress version shows
  `(pending)`; date persists across re-renders; version dropping below 100% then
  re-completing keeps the same date.
- Derived currentVersion: lowest-incomplete selection; all-done → highest.
- `depends`: set, dedup, self-dep rejection, `--clear`; merge/remove retarget.
- `--backfill`: dates from git tag; undated when no tag.
- Regression: `release` no longer writes changelog and `--no-changelog` is gone;
  existing sync/check/status behavior intact.

## Out of scope

- Using `dependsOn` to *reorder* `next`/`build` automatically (still id/`order`).
- Un-archive / restore command (archive is recoverable by hand / git for now).
- Changing the ROADMAP.md auto-region format.
