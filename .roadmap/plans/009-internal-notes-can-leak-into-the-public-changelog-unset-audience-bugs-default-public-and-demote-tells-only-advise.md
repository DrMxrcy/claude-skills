---
id: 9
title: Internal notes can leak into the public changelog: unset-audience bugs default public and demote tells only advise
type: bug
version: 0.15.0
status: active
created: 2026-08-20
---

# 🐛 Plan 9: Internal notes can leak into the public changelog: unset-audience bugs default public and demote tells only advise

> Type: bug · Target: v0.15.0

## 🔍 Symptom & Reproduction

- **Observed:** In the Parkboxd repo, internal-flavored notes rendered into the public `CHANGELOG.md`:
  - #588 (feature, audience unset): "Article editor: brand byline now defaults on for staff…" — staff/admin-only surface.
  - #651 (bug, audience unset): "…emails can never be silently lost when the daily sending limit is reached" — internal ops ceiling.
  - #653 (bug, audience unset): "Turning off analytics is now enforced on our servers too…" — self-incriminating security disclosure.
  - #624 (bug, explicit public): "Ride ratings are harder to game." — abuse-hardening disclosure.
- **Expected:** No unclassified item ever emits text into the public changelog; demote-grade wording is refused on public items, not just warned about.
- **Repro steps:** `roadmap new --type bug --title "x" --note "<any of the four notes above>"` (no `--audience`) → note renders in `CHANGELOG.md`.

## 🩺 Root Cause

- **Culprit:** `rmlib/changelog.py` (`DEFAULT_AUDIENCE`, tell lists, `item_audience`) + `rmlib/ops.py` (`set_note`, `new_item`).
- **Why:** Three compounding gaps:
  1. `DEFAULT_AUDIENCE` maps bug/feature → public, so an item nobody classified publishes its note by default.
  2. Demote tells only *route/warn*; a note tripping them on a public item still saves (only structural status tells hard-block).
  3. Tell lists are word-only and miss whole classes: staff/operator surfaces, ops limits ("sending limit", "quota"), abuse/fraud hardening, and disclosure-shaped phrasing ("now enforced…", "harder to game", "cannot be fabricated") that admits a past hole.

## 🛠️ Fix design

1. **Fail-closed defaults:** `DEFAULT_AUDIENCE` → `internal` for every type. Public rendering requires an explicit `audience: public`. Legacy unclassified items collapse to the roll-up line (safe direction); `audit_public_notes` gains a message telling the user how to promote them.
2. **Explicit audience required to save a note:** `set_note` / `new --note` refuse when the item's `audience` is unset — the caller must pass `--audience` or run `roadmap audience` first (`--force` overrides). Forces the classification decision at the moment text is written.
3. **Demote tells hard-block on public notes:** saving a note on an *effective-public* item whose note/title trips a demote tell is refused (was: warning), `--force` overrides. Mirrors the existing `_refuse_public_demote_tells` on the audience side.
4. **Expanded tells:**
   - `DEMOTE_ADMIN` += staff, byline, operator, curation, cockpit, feature flag(s), internal tool(s)
   - `DEMOTE_DEVSURFACE` += sending limit, daily limit, quota, throttle, backoff, replay, idempotency, idempotent, dedupe, deduplication
   - `DEMOTE_SECURITY` += abuse, fraud, tamper, spoof, forge, bypass, escalation, step-up, re-auth, double-submit, brute force
   - New `DEMOTE_DISCLOSURE` regex tier (fix-that-admits-the-hole phrasing): `now (enforced|validated|verified|blocked|rejected)`, `no longer (accepts|allows|possible)`, `harder to (game|abuse|fake|forge)`, `can(not| no longer) be (fabricated|gamed|forged|spoofed|faked)`, `enforced on (our|the) server(s)`, `server-side`. Deliberately NOT bare "on our servers" — legit privacy-positive notes ("your data stays on our servers, never sold") must stay clean.
5. **Tests against the Parkboxd corpus:** the four leaked notes must trip; known-good public notes (privacy-positive analytics note, private-account note) must stay clean; default-audience, note-refusal, and demote-block behaviors covered.
6. **Docs:** SKILL.md + plan/promote command docs updated — audience is now explicit-only for noted items; type default is internal-everything.

## 🛠️ Checklist

- [x] Step 1: Reproduction tests — Parkboxd leak corpus trips demote/disclosure tells, false-positive corpus stays clean, unset-audience bug/feature renders internal (red first)
- [x] Step 2: Expand tell lists + add DEMOTE_DISCLOSURE regex tier to `demote_tells`/`lint_note`
- [x] Step 3: Flip `DEFAULT_AUDIENCE` to internal for all types; audit message for noted-but-unclassified items
- [x] Step 4: Note-time refusals — unset audience refuses `note`/`new --note`; demote tells refuse on effective-public notes (`--force` overrides both)
- [ ] Step 5: Update SKILL.md and command docs for the new audience contract
- [ ] Step 6: Full test suite green
