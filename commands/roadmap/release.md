---
description: Cut a new version of the roadmap
argument-hint: <new version, e.g. 0.2.0>
---

Cut a new roadmap version: $ARGUMENTS

Pick the next version by **semver**: bug fixes → patch (x.y.Z), backward-compatible features
→ minor (x.Y.0), breaking changes / a whole new phase → major (X.0.0).

Ideally run `/roadmap:review` first. Then make the **public** changelog read for end users.
The quickest path is `/roadmap:changelog`, which audits the outgoing version and warns about
public items missing a note or worded internally. For each completed item:
- Confirm its **audience** — user-visible work is `public`, backend/infra/tooling/CI is
  `internal` (`python3 <roadmap.py> audience --plan <id> --to public|internal`). Internal
  items never list in `CHANGELOG.md`; they collapse into one "behind-the-scenes" line.
- Give every **public** item a clear, plain-language note (no vendor names, file paths, or
  issue refs): `python3 <roadmap.py> note --plan <id> --text "<user-facing summary>"`.

If notes are missing (e.g. you adopted an existing repo), backfill from git history
(`git log v<previous>..HEAD --oneline`) — or run `/roadmap:changelog`.

Then bump the version with the roadmap CLI:

`python3 <roadmap.py> release --version <V>`

- Release is **guarded**: it refuses if the current version still has incomplete items.
  Finish them, or pass `--force` to override.
- It re-renders both `CHANGELOG.md` (public) and `CHANGELOG.internal.md` and stamps the
  outgoing version's date.
- Add `--tag` to also create a `git tag` (e.g. `v0.2.0`).

Show the updated `ROADMAP.md` (new current version + rollups) and the new public
`CHANGELOG.md` entry — its latest section is ready to paste into the App Store "What's New"
or a website changelog.
