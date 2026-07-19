---
description: Curate the public changelog (and backfill user-facing notes from git history)
argument-hint: <version | empty for current>
---

Curate the changelog via the **roadmap** skill. Target: $ARGUMENTS (default: current version).

There are **two** changelogs, both rendered deterministically by the CLI:
- `CHANGELOG.md` — **public**. Each version renders its curated **release-notes summary**
  (`summary --version <v> --text "..."`) when one exists — a short, warm "What's New" blurb,
  exactly what ships to the App Store. Only when a version has no summary does it fall back
  to per-item bullets (`audience: public` items, from their `note`, never the raw title),
  with a "behind-the-scenes" roll-up line when nothing public shipped.
- `CHANGELOG.internal.md` — **internal**. Every item, with the raw title as a fallback —
  the full dev-facing work log. **This is where the detail lives.** The public file does
  NOT need every change; the internal one records all of them.

**Show / copy:** `python3 <roadmap.py> changelog` prints the public file; add `--internal`
for the full log. If the section is already curated, it's ready to paste.

**In-app consumption:** `python3 <roadmap.py> changelog --json` emits the public changelog
as structured data — `[{version, date, released, notes, sections: {New/Fixed/Improved:
[{text, pending}]}, rollup}]` — for build pipelines feeding an in-app changelog screen or
"What's New" popup. When `notes` (the curated blurb) is set it supersedes `sections` —
display it verbatim. Popups should filter to `released: true` and typically show only the
newest version's entries.

**The summary IS the release notes — keep it stupid simple.** End users don't want an
itemized list of everything on the roadmap; they want two friendly sentences. Write one
blurb per released version (`summary --version <v> --text "..."`), calibrated to the size
of the release:

- **Patch release** → two or three warm sentences, generic is fine. *"This update smooths
  out the ride. We've fixed display issues on some devices and squashed a few minor bugs
  behind the scenes for a more polished experience. Thanks for rolling with us!"* That's
  the whole entry.
- **Minor/major release** → a warm one-or-two-sentence intro, then 3–5 named highlights —
  a feature name plus one or two benefit sentences each — closing with something friendly
  and generic (*"Plus bug fixes and behind-the-scenes improvements. Keep the feedback
  coming!"*). A mid-size release can also be one flowing paragraph that walks through the
  highlights conversationally. Never enumerate every item — the highlight reel, not the
  inventory.
- Err on the side of a fuller, friendlier paragraph over a terse line — the blurb should
  feel like the team talking to fans, not a form field.
- Don't repeat the version number in the text (the CLI renders the version header), and
  keep the app's voice — friendly, a little playful, never a ticket.

The per-item `note`/`audience` work below still matters: it keeps the internal log honest
and gives you clean raw material to write the blurb from. But the blurb is what users see.

**Draft with a subagent.** For more than a version or two, delegate the writing: spawn a
subagent (Claude Task / Codex / whatever the host offers) with (a) the per-version item
list — titles + notes + audience — and (b) the sizing + voice rules above, including the
hard constraints (no dates, step numbers, version refs, paths, issue refs, or ALL-CAPS
status words — the CLI rejects them). Have it return one blurb per version as JSON, review
the drafts yourself, then save each via `summary --version <v> --text "..."` — the gate
still checks every save.

**Auto-routing.** The CLI already does the high-confidence calls for you: an item with no
explicit `audience` whose note/title trips an admin, compliance, security-disclosure, or
SEO-plumbing tell is **auto-routed to the internal changelog** (and reported in the audit). An
explicit `audience --to public` always overrides this — but if you set public on something
that still matches those tells, the audit flags it loudly as "likely miscategorized." Softer
wording problems (vendor names, jargon, mechanism phrasing) only **warn** — those are usually
public features that just need rephrasing, not reclassifying. One thing does hard-block:
`note` **refuses** a public note that is structurally a status/progress dump (ISO dates,
"Step N", version refs, file/spec paths, issue refs, ALL-CAPS status words like
DONE/DESCOPED/ACCEPTED). Rewrite it as a benefit sentence, mark the item internal, or pass
`--force` only when the text genuinely belongs in front of end users.

**The north star: `CHANGELOG.md` *is* your App Store "What's New".** Write and curate it as if
it will be pasted, unedited, straight into the App Store / Play Store release notes — because it
should be. That means: written for a **prospective or current end user**, in their language;
short and punchy; led by the headline features; friendly but not hypey; and containing nothing
they couldn't see, wouldn't care about, or shouldn't know. If a line wouldn't earn its place in
those few release-notes bullets, it belongs in `CHANGELOG.internal.md`. The internal changelog's
reader is your future team; write that one for them.

When you're unsure which file an item belongs in, the one question that settles it:

> *"Would this line make that end user a little more glad they use the app — and can they
> understand it without knowing how the app is built?"*

No on either half → `internal`. **The keyword lint only catches phrasing we anticipated; it
will miss novel internal wording. You are the classifier — apply the principle below even when
nothing is flagged. The lint is a seatbelt, not the rule.**

**For each item, decide in this order:**
1. **Who actually experiences it?** End users → maybe public. Only admins/operators/staff,
   only a regulator, or nobody visible → `internal`. Judge by who *uses* the feature, not how
   the note reads: "a markdown editor on the web" sounds public, but if it lives in the admin
   panel it's internal.
2. **Net-new value, or table-stakes?** A new ability or an improvement they'll feel → maybe
   public. The app merely *existing* (sign-up, @usernames, a dark theme, core navigation) or a
   cosmetic/housekeeping tweak → `internal`. Don't announce that the product is a product.
3. **Safe to say out loud?** Announcing a security fix advertises the hole you had; a
   compliance gate (age check, EULA, GDPR) is a legal obligation, not a feature. Anything
   self-incriminating or legally mandated → `internal`. Never describe a past weakness.
4. **Still public? Write the benefit, not the build.** One sentence, in the user's words,
   leading with what they can now *do* — never the system, vendor, file, ticket, or mechanism
   behind it. Describe the *result* ("crowd levels are more accurate"), not the method
   ("truncated headliner index").

**Operational loop:**
1. `python3 <roadmap.py> changelog` → read the warnings: versions missing a release-notes
   summary, items auto-routed to internal (confirm or override `--to public`), items marked
   public but matching internal signals (almost always reclassify), public items with no
   note, and notes that read internal (rephrase).
2. Set audience where the auto-router didn't decide:
   `python3 <roadmap.py> audience --plan <id> --to public|internal`.
3. Write each public note: `python3 <roadmap.py> note --plan <id> --text "<benefit>"`.
4. **Write the version blurb** from those notes:
   `python3 <roadmap.py> summary --version <v> --text "<What's New blurb>"` — generic
   one-liner for patches, intro + 3–4 highlights for big releases (sizing guide above).
5. Re-run until clean, then preview both files. `/roadmap:release` stamps the dated section;
   this command just gets it clean.

**The exclusions, and the principle behind each** (each sends an item to `internal` even when
real work shipped — recognize the *category*, not just the example words):

- **Admin / operator-only** — panels, dashboards, user management, moderation, the CMS. Staff
  aren't the audience. Expose only the user-operated half: "block other users" is public; the
  moderation console behind it is not.
- **Security fixes that reveal a past hole** — "now uses expiring links instead of public
  URLs", "closed a privilege gap". Telling users you fixed it tells them (and attackers) they
  were exposed. Never name the prior weakness.
- **Compliance / legal gates** — age gate, EULA/terms acceptance, GDPR/COPPA, policy-required
  account deletion. Mandated, not chosen by anyone.
- **Foundational / launch / table-stakes** — sign-up, @usernames, a theme, core nav. Baseline,
  not *new*. Even at v1.0.0, lead with the headline experience, not every brick.
- **Trivial / cosmetic / minor nav** — a settings-screen reskin, moving a button. Fold into the
  roll-up.

Litmus test: *"Would I proudly put this in the App Store 'What's New', and be glad a competitor
read it?"* If it's plumbing, admin-only, a fixed embarrassment, a legal checkbox, cosmetic
housekeeping, or just "the app works" — it's `internal`.

**Collapse a campaign into one line.** When many items are the same initiative, the public
changelog gets **one headline**, not every variant — mark the rest `internal`. A version that
shipped six SEO items ("static-page builder", "per-park web pages", "news web pages",
"sitemap.xml", "structured data", "search-optimized homepage") gets *one* public line —
"Parks, rides, and news now show up when you search Google" — and the plumbing stays internal.
Same for five "responsive web layout" items → "Parkboxd now has a proper desktop web layout."
The public changelog is the highlight reel; the internal log keeps the full list.

**Voice — write App Store release notes.** Public notes: one sentence, lead with the user's
gain, concrete and specific, warm and plain (the way the App Store "What's New" reads), results
over mechanisms, zero vendor/tool names, file paths, issue refs, or dev jargon. Read the whole
public section back as if it were the release notes a user sees before updating — if any line
feels like a ticket, an internal brag, or filler, fix or drop it. A version's public section
should feel like a tight highlight reel of a few marquee items, not an exhaustive list.
Internal notes (or no note → the title fallback) can be as technical as you like.

**Translate, don't copy.** Examples:

| Item (internal/title)                              | ❌ leaks internal                          | ✅ public note                                            |
|----------------------------------------------------|--------------------------------------------|-----------------------------------------------------------|
| Wire up Sentry + Aptabase analytics                | "Added Sentry crash reporting + Aptabase"  | *(internal — user sees nothing; mark `internal`)*         |
| Stop dev backend polling 24/7 (Convex cost)        | "Cut Convex polling to save cost"          | *(internal — infra; `internal`)*                          |
| Signed URLs for non-public images (convex/lib/r2)  | "Switch r2.ts reads to signed URLs (#42)"  | "Your private photos are now protected by secure, expiring links." |
| Park-closed gate fix in waitTimes.ts               | "Fixed hours gate in waitTimes.ts"         | "Closed parks no longer show phantom wait times."         |
| Pre-launch security & abuse hardening              | "Hardened security: closed privilege-misuse and spam/abuse gaps" | *(internal — plumbing; expose only user-operated controls like "block users")* |
| SEO: reusable static-page builder + sitemap/robots | "Lays the groundwork with a reusable static-page builder + robots rules" | "Parks and rides now show up when you search Google."     |
| Crowd index: truncated headliner index             | "Use a truncated headliner index over anchor rides" | "Crowd levels are more accurate — busy parks now read busy." |
| Apple Watch logging feature                        | —                                          | "Log the ride you just rode straight from your Apple Watch — no phone needed." |

**Backfill (adopted repo / missing notes):** reconstruct what shipped from git history —
`git log v<previous>..HEAD --oneline` (or `git log --oneline` with no tags) — map commits to
items by plan/title, then set each item's audience + note as above.

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill under
the agent's skills dir; probe the fixed candidates once and reuse `$RM`:

```bash
for d in .claude .grok .agents "$HOME/.claude" "$HOME/.grok" "$HOME/.agents"; do RM="$d/skills/roadmap/scripts/roadmap.py"; [ -f "$RM" ] && break; done
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
