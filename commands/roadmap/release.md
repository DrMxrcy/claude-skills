---
description: Cut a new version of the roadmap
argument-hint: <new version, e.g. 0.2.0>
---

Cut a new roadmap version: $ARGUMENTS

Pick the next version by **semver**: bug fixes → patch (x.y.Z), backward-compatible features
→ minor (x.Y.0), breaking changes / a whole new phase → major (X.0.0).

Ideally run `/roadmap:review` first. Then make the changelog read for **end users**: for each
completed item, ensure it has a clear, plain-language note —
`python3 <roadmap.py> note --plan <id> --text "<user-facing summary>"` — fixing any that are
still developer-worded.

Then bump the version with the roadmap CLI:

`python3 <roadmap.py> release --version <V>`

- Release is **guarded**: it refuses if the current version still has incomplete items.
  Finish them, or pass `--force` to override.
- It writes a `CHANGELOG.md` entry for the outgoing version (its completed items). Pass
  `--no-changelog` to skip.
- Add `--tag` to also create a `git tag` (e.g. `v0.2.0`).

Show the updated `ROADMAP.md` (new current version + rollups) and the new `CHANGELOG.md`
entry — its latest section is ready to paste into the App Store "What's New" or a website
changelog.
