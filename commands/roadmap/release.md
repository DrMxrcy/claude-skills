---
description: Cut a new version of the roadmap
argument-hint: <new version, e.g. 0.2.0>
---

Cut a new roadmap version: $ARGUMENTS

First confirm the current version's items are complete (run `status`). Then bump the
version with the roadmap CLI:

`python3 <roadmap.py> release --version <V>` (add `--tag` to also create a `git tag`).

Show the updated `ROADMAP.md` so the user can see the new current version and rollups.
