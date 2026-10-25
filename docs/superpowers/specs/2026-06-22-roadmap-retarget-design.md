# roadmap — `retarget` (re-stamp items onto another version)

**Status:** Approved (design)
**Date:** 2026-06-22
**Skill:** `skills/roadmap`
**Target version:** rides with the 0.6.0 branch

## Summary

Add a `retarget` verb that changes the `version` of existing items — the missing CRUD
operation (we can *set* a version at `new --version` but never *change* it). Primary use:
consolidate shipped work spread across versions (e.g. v1.0.0–v1.6.0) into a single version
(e.g. v1.0.0) on a release branch, without disturbing mainline.

## CLI

`roadmap.py retarget --to <version> (--from <versions> | --plan <ids>)`

- `--to` (required) — destination version, normalized via `_norm_version`.
- `--from` — comma list of source versions; selects **all items** in those versions.
- `--plan` — comma list of item ids; selects those items.
- Exactly one of `--from` / `--plan` is required (error if neither or both).

Behavior:
1. Resolve selected items. `--plan` with an unknown id → `ValueError`. A `--from` version
   with no items is skipped with a stderr warning (not fatal). If the selection is empty
   overall → `ValueError`.
2. For each selected item: set `item["version"] = to` in `config.json` **and** rewrite the
   plan file's `version:` frontmatter via `_set_frontmatter`.
3. `write_config`, then `sync`.

`currentVersion` is left untouched (it is only the default for new items; the v0.6.0
descope of derivation stands). The git branch is the user's workflow, documented in the
command file — the CLI only edits roadmap state.

## Knock-on: prune stale `versionDates` in `sync`

After a retarget, emptied versions should not linger. In `sync`, after stamping completion
dates, drop any `versionDates` key whose version no longer appears in `config["items"]`.
This keeps the changelog clean (it already renders only versions that have items) and the
config tidy. Stable for versions that still have items (no churn).

## Command file `/roadmap:retarget`

Documents the consolidation workflow:

```
git checkout -b release-1.0.0
python3 <roadmap.py> retarget --to 1.0.0 --from 1.0.0,1.3.0,1.6.0
git add -A && git commit -m "consolidate shipped work into v1.0.0"
```

Note that retarget moves items regardless of done-state, and that mainline keeps its
current versions.

## Docs

- New `commands/roadmap/retarget.md`.
- Add `retarget --to V (--from VERS | --plan IDS)` to SKILL.md + README.md command refs.
- `example/CLAUDE.md`: **no change** — its rules region is byte-identical to `RULES_BLOCK`,
  and "update only through the CLI / never hand-edit ROADMAP.md" already governs `retarget`.
  `RULES_BLOCK` stays lean (it lists principles, not every verb).

## Testing

- `--from` moves all items in the named versions; non-selected versions untouched.
- `--plan` moves the listed items.
- Plan-file `version:` frontmatter is rewritten to `--to`.
- Errors: neither selector, both selectors, unknown `--plan` id, empty selection.
- `--from` version with no items → warning, no crash.
- `versionDates` for an emptied version is pruned after `sync`; the changelog re-renders
  with the moved items under `--to`.

## Out of scope

- Creating/switching git branches from the CLI (user's git workflow).
- Auto-setting `currentVersion` to `--to`.
