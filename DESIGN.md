# Design

This repo has no product UI except the roadmap dashboard, `skills/roadmap/scripts/rmlib/dashboard.html`. It is a read-only status view served locally. This file records its visual system so new UI matches it.

## Principles
- **Terminal-native.** Monospace throughout, dark background, dense rows. It reads like the CLI output it mirrors.
- **Status by colour, always with text.** Every colour-coded dot or bar also has a label or fraction.
- **Read-only.** The dashboard shows state; it never edits plans or config.
- **No build step, no framework.** One HTML file with inline CSS and vanilla JS.

## Colour tokens
Defined once in `:root` in `dashboard.html`. Reuse these names rather than new hex values.

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0e1116` | page and header background |
| `--fg` | `#e6edf3` | primary text |
| `--muted` | `#8b98a5` | secondary text, counts, file paths |
| `--line` | `#232a34` | borders and dividers |
| `--bar` | `#242c38` | progress track, tabs, inputs |
| `--done` | `#3fb950` | done status, progress fill |
| `--active` | `#d29922` | in-progress status, incubator bullets |
| `--blocked` | `#f85149` | blocked status |
| `--todo` | `#4b5563` | not-started status |
| `--accent` | `#58a6ff` | current version label |

## Typography
- Font stack: `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`, 14px / 1.5.
- Headings are 16px (page title) and 13px (version groups), weight 600.
- Secondary metadata is 11–12px in `--muted`.

## Layout and components
- Max content width 960px, with 24px side padding.
- Sticky header holds the title, a progress bar, count chips and tabs (Roadmap, Ideas, Changelog).
- Version groups are collapsible. The current version is open by default. User toggles persist in `localStorage`.
- Items are a three-column grid: status dot, title with badges, and a progress bar with an `n/m` fraction.
- Badges are 10px text in a thin `--line` border.
- Clicking an item expands its checklist, loaded on demand from `/api/item`.

## Interaction rules
- Live updates arrive over Server-Sent Events on `/events`. A stale indicator turns grey when the connection drops.
- Filters match item ids and titles. While filtering, every matching group is forced open.
- Text is inserted with `textContent` only. Never use `innerHTML` with project data.

## Accessibility
- Keep text contrast readable on `--bg`. Do not use `--todo` for body text.
- Keep status conveyed in words or counts, not colour alone.
- Respect `[hidden]` with `display:none !important`, as the existing CSS does.

## Changing the dashboard
Edit `dashboard.html` directly, add tokens to `:root` only when a new state needs one, and verify through the pytest suite (`tests/test_roadmap_serve.py`) and the rendered DOM. Visual review is the user's call.
