"""roadmap reporting — session orientation, handoff brief, drift check, and the
git helpers they rely on. Layer: rmcore + rmsync (read-only, no mutations)."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from rmcore import (
    get_version, read_config, roadmap_dir, write_config)
from rmsync import (
    next_item, status)


def _git_head(root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root),
                             capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def _record_last_seen_sha(root: Path) -> None:
    """Stamp config with current HEAD after a successful check-off (clears drift nudge)."""
    head = _git_head(root)
    if not head:
        return
    try:
        cfg = read_config(root)
    except (FileNotFoundError, json.JSONDecodeError):
        return
    if cfg.get("last_seen_sha") == head:
        return
    cfg["last_seen_sha"] = head
    write_config(root, cfg)


def drift_check(root: Path) -> str | None:
    """If the repo has commits since last check-off and the current version still has
    unfinished work, return a nudge message; otherwise None. Never raises; safe no-op
    without .roadmap/ or git."""
    try:
        cfg = read_config(root)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None
    head = _git_head(root)
    if not head:
        return None
    last = cfg.get("last_seen_sha")
    if not last or last == head:
        return None
    # Count commits between last seen and HEAD (best-effort)
    n = 0
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", f"{last}..HEAD"],
            cwd=str(root), capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip().isdigit():
            n = int(out.stdout.strip())
    except FileNotFoundError:
        return None
    if n <= 0:
        return None
    st = status(root)
    ver = st["currentVersion"]
    unfinished = [i for i in st["items"] if i["version"] == ver and i["pct"] < 100]
    if not unfinished:
        return None
    return (f"⚠ {n} commit(s) since last roadmap check-off — "
            f"run /roadmap:catchup or /roadmap-catchup?")


def _git_dirty(root: Path) -> bool:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                             capture_output=True, text=True)
        return out.returncode == 0 and bool(out.stdout.strip())
    except FileNotFoundError:
        return False


def orient(root: Path) -> dict | None:
    """Session orientation: project, progress, next item, drift, skill versions.
    Returns None when .roadmap/ is absent — safe for hooks."""
    if not (roadmap_dir(root) / "config.json").exists():
        return None
    cfg = read_config(root)
    st = status(root)
    ver = st["currentVersion"]
    in_ver = [i for i in st["items"] if i["version"] == ver]
    steps_done = sum(i["done"] for i in in_ver)
    steps_total = sum(i["total"] for i in in_ver)
    items_done = sum(1 for i in in_ver if i["pct"] == 100)
    nxt = next_item(root, version=ver, quiet=True)
    installed = get_version()
    recorded = cfg.get("skillVersion") or "unknown"
    return {
        "project": st["project"],
        "currentVersion": ver,
        "stepsDone": steps_done,
        "stepsTotal": steps_total,
        "itemsDone": items_done,
        "itemsTotal": len(in_ver),
        "next": ({"id": nxt["id"], "title": nxt["title"], "type": nxt["type"],
                  "pct": nxt["pct"], "blockedBy": nxt.get("blockedBy") or [],
                  "file": nxt.get("file")}
                 if nxt else None),
        "drift": drift_check(root),
        "skillVersionInstalled": installed,
        "skillVersionProject": recorded,
        "skillVersionStale": recorded not in ("unknown", installed),
        "gitDirty": _git_dirty(root),
    }


def format_orient(payload: dict, handoff: bool = False) -> str:
    lines = [
        f"Roadmap: {payload['project']} — v{payload['currentVersion']}",
        f"Progress: {payload['itemsDone']}/{payload['itemsTotal']} items · "
        f"{payload['stepsDone']}/{payload['stepsTotal']} steps",
    ]
    nxt = payload.get("next")
    if nxt:
        nid = nxt["id"]
        lines.append(f"Next: #{nid} {nxt['title']} [{nxt['type']}] — {nxt['pct']}%")
        if handoff and nxt.get("file"):
            lines.append(f"Plan: .roadmap/{nxt['file']}")
        # Dual slash forms so Grok never gets colon-only recommendations
        lines.append(
            f"Continue: /roadmap:next · /roadmap-next · /roadmap next"
            f"  OR  /roadmap:build {nid} · /roadmap-build {nid} · /roadmap build {nid}"
        )
        lines.append(
            f"Chain version (pauses off): /roadmap:build {payload['currentVersion']} --auto"
            f" · /roadmap-build {payload['currentVersion']} --auto"
            f"  (not next --auto — next is always one item)"
        )
    else:
        lines.append("Next: (none — current version complete or all remaining items blocked)")
    if payload.get("drift"):
        lines.append(payload["drift"])
    if payload.get("gitDirty"):
        lines.append("⚠ Working tree has uncommitted changes — commit code+roadmap (or "
                     "inspect) before building more so nothing is agent-private.")
    inst = payload.get("skillVersionInstalled", "?")
    proj = payload.get("skillVersionProject", "?")
    if payload.get("skillVersionStale"):
        lines.append(f"⚠ Project rules at skill v{proj} but installed skill is v{inst} — "
                     f"run: roadmap.py upgrade")
    elif handoff:
        lines.append(f"Skill: v{inst} (project rules recorded: v{proj})")
    # Always useful after rate-limit / crash / agent switch (handoff adds the full list).
    if payload.get("gitDirty") or payload.get("drift") or handoff:
        lines.append(
            "Resume: commit or catchup if needed, then continue the plan checklist "
            "(/roadmap:next · /roadmap-next) — formal handoff is optional; git is the sync.")
    if handoff:
        lines.extend([
            "",
            "Multi-coder / rate-limit checklist:",
            "  1. Prefer micro-commits after every checked step (limits loss on rate-limit)",
            "  2. If you could not handoff: just open the other agent — run orient/handoff there",
            "  3. Commit any dirty tree (code + roadmap) the previous agent left",
            "  4. git pull/push if machines differ",
            "  5. Drift → /roadmap:catchup after tests; then next unfinished step",
            "  6. Continue quality-first build (do not re-plan from chat memory)",
            "Shared source of truth: ROADMAP.md + .roadmap/ + CHANGELOG*.md in git.",
        ])
    return "\n".join(lines)


def handoff(root: Path) -> dict | None:
    """Brief for switching between AI coders (Claude ↔ Grok ↔ …). Same data as orient
    with an explicit handoff checklist."""
    return orient(root)
