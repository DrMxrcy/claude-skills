# Example Project

Your own project notes and conventions live here (build/test commands, code style,
architecture pointers, etc.). The roadmap skill never touches this area.

The block below is what the roadmap skill adds — via `install.sh` or the first
`roadmap init` / `/roadmap:init`. It is inserted idempotently between the
`roadmap:rules` markers, so your content above and below is always preserved.

<!-- roadmap:rules:start -->
## Roadmap tracking
This project tracks work in `ROADMAP.md` via the **roadmap** skill (`/roadmap:*` commands).
- Before writing functional code, ensure there is an active plan in `.roadmap/plans/`.
- Work one checklist item at a time; do not multitask across features/bugs.
- Update status only through the roadmap CLI / `/roadmap:done`; never hand-edit `ROADMAP.md`.
<!-- roadmap:rules:end -->
