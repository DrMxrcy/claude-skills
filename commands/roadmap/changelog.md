---
description: Curate the public changelog (and backfill user-facing notes from git history)
argument-hint: <version | empty for current>
---

Curate the changelog via the **roadmap** skill. Target: $ARGUMENTS (default: current version).

There are **two** changelogs, both rendered deterministically by the CLI:
- `CHANGELOG.md` — **public**. Only `audience: public` items, rendered from each item's
  user-facing `note` (never the raw title). Ready to paste into the App Store "What's New"
  or a website changelog. Versions that also shipped internal-only work get one rolled-up
  "behind-the-scenes" line instead of listing it.
- `CHANGELOG.internal.md` — **internal**. Every item, with the raw title as a fallback —
  the full dev-facing work log.

**Show / copy:** `python3 <roadmap.py> changelog` prints the public file; add `--internal`
for the full log. If the section is already curated, it's ready to paste.

**Auto-routing.** The CLI already does the high-confidence calls for you: an item with no
explicit `audience` whose note/title trips an admin, compliance, security-disclosure, or
SEO-plumbing tell is **auto-routed to the internal changelog** (and reported in the audit). An
explicit `audience --to public` always overrides this — but if you set public on something
that still matches those tells, the audit flags it loudly as "likely miscategorized." Softer
wording problems (vendor names, jargon, mechanism phrasing) only **warn** — those are usually
public features that just need rephrasing, not reclassifying.

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
1. `python3 <roadmap.py> changelog` → read the warnings: items auto-routed to internal
   (confirm or override `--to public`), items marked public but matching internal signals
   (almost always reclassify), public items with no note (dropped from `CHANGELOG.md`), and
   notes that read internal (rephrase).
2. Set audience where the auto-router didn't decide:
   `python3 <roadmap.py> audience --plan <id> --to public|internal`.
3. Write each public note: `python3 <roadmap.py> note --plan <id> --text "<benefit>"`.
4. Re-run until clean, then preview both files. `/roadmap:release` stamps the dated section;
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

**Finding the CLI (`<roadmap.py>`) — do not search for it.** It ships with the skill at a
fixed path; resolve it once and reuse `$RM`:

```bash
RM=.claude/skills/roadmap/scripts/roadmap.py; [ -f "$RM" ] || RM="$HOME/.claude/skills/roadmap/scripts/roadmap.py"
```

Run `python3 "$RM" …` — use `$RM` wherever `<roadmap.py>` appears.
