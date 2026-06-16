---
description: Show the latest changelog entry, or backfill user-facing notes from git history
argument-hint: <version | empty for current>
---

Work with the user-facing changelog via the **roadmap** skill. Target: $ARGUMENTS
(default: current version).

**Show / copy:** If `CHANGELOG.md` already has an entry for the target version, print that
section verbatim — it's ready to paste into the App Store "What's New" or a website changelog.

**Backfill (when notes are missing or you adopted an existing repo):**
1. Run `python3 <roadmap.py> status` to list the version's items and which lack a user-facing
   `note`.
2. To reconstruct what shipped, read git history since the previous release:
   `git log v<previous>..HEAD --oneline` (or `git log --oneline` if there are no tags yet).
   Map commits to items by their plan/title.
3. For each item without a good note, write a plain-language, benefit-focused one-liner:
   `python3 <roadmap.py> note --plan <id> --text "<user-facing summary>"`.
4. Preview the grouped entry (✨ New / 🐛 Fixed / ⚡ Improved). The actual `CHANGELOG.md`
   section is written by `/roadmap:release`; this command just gets the notes ready and shows
   what it will look like.

The CLI lives at `.claude/skills/roadmap/scripts/roadmap.py` (project) or
`~/.claude/skills/roadmap/scripts/roadmap.py` (global).
