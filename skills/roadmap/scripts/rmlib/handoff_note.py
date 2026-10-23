"""Pending-decision handoff notes for plan 27 step 2.

`handoff --pending "<text>"` records an open decision in .roadmap/notes/<id>-handoff.md.
A plain `handoff` refuses while that note holds an OPEN decision. `handoff --resolve`
closes it. The note is the only state written here; config.json and ROADMAP.md stay
untouched, so this layer never edits roadmap state."""
from __future__ import annotations
from pathlib import Path

from rmlib.core import roadmap_dir

OPEN_PREFIX = "OPEN: "
RESOLVED_PREFIX = "RESOLVED: "


def handoff_note_path(root: Path, plan_id: int) -> Path:
    return roadmap_dir(root) / "notes" / f"{plan_id}-handoff.md"


def open_decision(root: Path, plan_id: int) -> str | None:
    """Return the text of the open decision for this plan, or None if none is open."""
    path = handoff_note_path(root, plan_id)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(OPEN_PREFIX):
            return line[len(OPEN_PREFIX):].strip()
    return None


def write_pending(root: Path, plan_id: int, text: str) -> Path:
    """Write (or replace) the handoff note with one OPEN decision line."""
    text = text.strip()
    if not text:
        raise ValueError("--pending needs a non-empty decision")
    path = handoff_note_path(root, plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Handoff for plan {plan_id}\n\n"
        f"{OPEN_PREFIX}{text}\n",
        encoding="utf-8")
    return path


def resolve_pending(root: Path, plan_id: int) -> bool:
    """Close the open decision. Returns False when no note or no open decision exists."""
    path = handoff_note_path(root, plan_id)
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    for i, line in enumerate(lines):
        if line.startswith(OPEN_PREFIX):
            lines[i] = RESOLVED_PREFIX + line[len(OPEN_PREFIX):]
            changed = True
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed
