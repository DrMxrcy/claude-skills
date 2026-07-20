# `roadmap serve` — Local Live Progress Dashboard

**Date:** 2026-07-19
**Status:** Design approved — pending roadmap plan

## Problem

`ROADMAP.md` is the only way to see progress, and reading raw markdown is a poor
way to gauge where a version stands at a glance. The user wants a better view of
progress that runs alongside the Claude Code terminal session and reflects work
as it happens.

## Solution

Add a `serve` subcommand to the roadmap CLI that starts a local, read-only web
dashboard. It polls the existing `status --json` data and renders progress bars
grouped by version. It runs in the foreground for the life of the terminal
session and dies on Ctrl-C. No new dependencies, no build step, no hosting.

### Non-goals (v1)

- Per-step checklist drill-down (bars only in v1; deferred)
- SSE / push updates (polling is sufficient)
- Authentication (localhost-only bind)
- Remote / hosted / git-synced views
- Any write path — the dashboard never mutates `.roadmap/`

## Command

```
roadmap.py serve [--port 4700] [--root .] [--no-open]
```

- Starts a stdlib server, prints the URL, opens the default browser (unless
  `--no-open`), and blocks until interrupted.
- Fails cleanly with a message if the port is in use.
- Safe no-op with a clear message if `.roadmap/` is absent (mirrors `orient`).

## Architecture

One new section in `skills/roadmap/scripts/roadmap.py` (~80 lines). No new files
in the skill beyond tests; the frontend is an embedded string.

### Server

- `http.server.ThreadingHTTPServer` bound to `127.0.0.1` only (local, no auth
  needed; threading so a slow poll or page load does not block the other).
- Routes:
  - `GET /` → serve the embedded `index.html` string.
  - `GET /api/status` → `json.dumps(status(root))`. Reuses the existing
    `status()` function verbatim — no new data logic.
  - `GET /api/changelog` → reuses the changelog JSON builder (public progress
    view). Optional, cheap.
  - Everything else → 404.
- The handler captures `root` via a closure/partial so no global state is needed.

### Data contract (already exists)

`status(root)` returns:

```json
{
  "project": "...",
  "currentVersion": "0.9.0",
  "items": [
    {"id": 1, "title": "...", "type": "feature", "version": "0.9.0",
     "status": "active", "done": 2, "total": 5, "pct": 40,
     "dependsOn": [], "blockedBy": [], "note": "...", "audience": "public"}
  ]
}
```

The dashboard consumes this as-is. If the shape changes, the dashboard follows
for free.

### Frontend (embedded HTML string, vanilla JS/CSS)

- Polls `GET /api/status` every 2s; diffs against last render; updates the DOM.
- Groups items by `version`. `currentVersion` expanded at top; past versions
  collapsed by default.
- Per item: title, type badge, `pct` bar, `done/total`, status dot
  (done / active / blocked / todo). Blocked items show their `blockedBy` ids
  muted.
- Header: project name, current version, overall percent
  (`sum(done) / sum(total)` across items).
- "Last updated" ticker; the indicator goes stale-grey when a poll fails
  (e.g. the terminal/server was closed), signalling the data is no longer live.

## Boundaries & Isolation

- **Read-only.** All mutation stays in the CLI / skill commands. The server
  exposes no write route.
- **Self-contained.** One command, one server, one embedded page. Nothing
  persists; the process owns its whole lifecycle.
- **Zero deps.** Pure Python stdlib, matching the existing CLI.

## Testing

`tests/` gets `test_roadmap_serve` (mirrors existing CLI test style):

- Start the server on an ephemeral port (port 0) in a background thread.
- `GET /api/status` returns HTTP 200 and JSON deep-equal to `status(root)`.
- `GET /` returns HTTP 200 and `text/html`.
- An unknown path returns 404.
- Server binds `127.0.0.1` (not `0.0.0.0`).
- Graceful message (non-crash) when `.roadmap/` is absent.

## Rollout

Follows the project roadmap process: this spec → `/roadmap:plan` → tracked item
on an upcoming version → quality-first build. No off-roadmap code.
