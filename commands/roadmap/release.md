---
description: Cut a new version of the roadmap
argument-hint: <new version, e.g. 0.2.0>
---

Cut a new roadmap version: $ARGUMENTS

Ideally run `/roadmap:review` first. Then bump the version with the roadmap CLI:

`python3 <roadmap.py> release --version <V>`

- Release is **guarded**: it refuses if the current version still has incomplete items.
  Finish them, or pass `--force` to override.
- It writes a `CHANGELOG.md` entry for the outgoing version (its completed items). Pass
  `--no-changelog` to skip.
- Add `--tag` to also create a `git tag` (e.g. `v0.2.0`).

Show the updated `ROADMAP.md` (new current version + rollups) and the `CHANGELOG.md` entry.
