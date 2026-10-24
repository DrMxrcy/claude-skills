"""roadmap reporting — session orientation, handoff brief, drift check, and the
git helpers they rely on. Layer: rmcore + rmsync (read-only, no mutations)."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from rmlib.core import (
    display_id, get_version, read_config, roadmap_dir, write_config)
from rmlib.sync import (
    format_due, next_item, roadmap_health, status)
from rmlib.incubator import (
    incubator_file, list_incubator_bullets)
from rmlib import owners as rmowners
from rmlib import digest as rmdigest


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
            f"run /roadmap-catchup or /roadmap-catchup?")


def _git_dirty(root: Path) -> bool:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                             capture_output=True, text=True)
        return out.returncode == 0 and bool(out.stdout.strip())
    except FileNotFoundError:
        return False


def _git_out(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=str(root),
                             capture_output=True, text=True)
        return out.stdout if out.returncode == 0 else None
    except FileNotFoundError:
        return None


def _git_state(root: Path) -> dict:
    """Branch, dirty file list and last 5 commits. Empty values when not a git repo."""
    # symbolic-ref works on an unborn branch (a fresh repo with no commits yet)
    branch = (_git_out(root, "symbolic-ref", "--short", "HEAD") or "").strip() or None
    dirty = [l[3:] for l in (_git_out(root, "status", "--porcelain") or "").splitlines()
             if l.strip()]
    log = [l for l in (_git_out(root, "log", "--oneline", "-5") or "").splitlines() if l]
    return {"branch": branch, "dirtyFiles": dirty, "recentCommits": log}


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
    owner = rmowners.default_owner(root)
    nxt = next_item(root, version=ver, quiet=True, owner=owner)
    installed = get_version()
    recorded = cfg.get("skillVersion") or "unknown"
    payload = {
        "project": st["project"],
        "currentVersion": ver,
        "stepsDone": steps_done,
        "stepsTotal": steps_total,
        "itemsDone": items_done,
        "itemsTotal": len(in_ver),
        "next": ({"id": nxt["id"], "displayId": nxt["displayId"],
                  "title": nxt["title"], "type": nxt["type"],
                  "pct": nxt["pct"], "blockedBy": nxt.get("blockedBy") or [],
                  "file": nxt.get("file")}
                 if nxt else None),
        "versionComplete": bool(st.get("versionComplete")),
        # Plan 46: waiting steps due today/overdue (listed first), and whether
        # the current version's only open work is waiting steps.
        "waitingDue": st.get("waitingDue") or [],
        "waitingOnly": any(i["lane"] == "waiting" for i in in_ver) and all(
            i["lane"] in ("done", "waiting") for i in in_ver),
        "drift": drift_check(root),
        "skillVersionInstalled": installed,
        "skillVersionProject": recorded,
        "skillVersionStale": recorded not in ("unknown", installed),
        "gitDirty": _git_dirty(root),
    }
    payload.update(_git_state(root))
    # Claim owners (plan 40): who this session is and what it holds.
    payload["owner"] = owner
    payload["held"] = _own_holds(st["items"], owner,
                                 rmowners.claim_ttl_hours(cfg))
    if st.get("wip"):                       # settings.wipLimit set
        payload["wip"] = st["wip"]
    # ROADMAP.md size (plan 39): orient is the once-per-session place to say it.
    payload["health"] = roadmap_health(root)
    # settings.buildRoles: free-form per-role model/agent names, surfaced only when set
    # (absent key keeps orient/handoff output identical to a project without it).
    roles = (cfg.get("settings") or {}).get("buildRoles")
    if isinstance(roles, dict) and roles:
        payload["buildRoles"] = roles
    return payload


def _own_holds(items: list[dict], owner: str | None, ttl: float) -> list[dict]:
    """Unfinished items whose claim `owner` currently holds (plan 40)."""
    out = []
    for it in items:
        claim = it.get("claim")
        if it.get("lane") == "done" or not rmowners.same_owner(
                rmowners.holder(claim, ttl), owner):
            continue
        out.append({"id": it["id"], "displayId": it["displayId"],
                    "title": it["title"], "lane": it.get("lane"),
                    "age": rmowners.age(claim)})
    return out


def format_orient(payload: dict, handoff: bool = False) -> str:
    lines = [
        f"Roadmap: {payload['project']} — v{payload['currentVersion']}",
        f"Progress: {payload['itemsDone']}/{payload['itemsTotal']} items · "
        f"{payload['stepsDone']}/{payload['stepsTotal']} steps",
    ]
    lines.extend(format_due(payload.get("waitingDue") or []))
    nxt = payload.get("next")
    if nxt:
        nid = nxt["id"]
        lines.append(f"Next: {display_id(nxt)} {nxt['title']} "
                     f"[{nxt['type']}] — {nxt['pct']}%")
        if handoff and nxt.get("file"):
            lines.append(f"Plan: .roadmap/{nxt['file']}")
        # One hyphen form (the single command name every agent uses) plus the bare form.
        lines.append(
            f"Continue: /roadmap-next · /roadmap next"
            f"  OR  /roadmap-build {nid} · /roadmap build {nid}"
        )
        lines.append(
            f"Chain version (pauses off): /roadmap-build {payload['currentVersion']} --auto"
            f"  (not next --auto — next is always one item)"
        )
    elif payload.get("versionComplete"):
        lines.append(
            f"🎉 v{payload['currentVersion']} is 100% complete but uncut — cut it: "
            f"/roadmap-release · /roadmap-release · roadmap.py release --version <next> "
            f'(or set settings.autoRelease to "auto")')
    elif payload.get("waitingOnly"):
        lines.append(
            f"Next: (none — v{payload['currentVersion']} has only waiting steps left; "
            f"ship it now with: roadmap.py release --version <next> --with-waiting)")
    else:
        lines.append("Next: (none — current version complete or all remaining items blocked)")
    held = payload.get("held") or []
    if held:
        lines.append(f"Held by you ({payload.get('owner')}): " + " · ".join(
            f"{h['displayId']} {h['title']} ({h['lane']})" for h in held))
    over = rmowners.wip_warning(payload.get("wip"))
    if over:
        lines.append(f"⚠ {over}")
    lines.extend(rmdigest.orient_lines(payload.get("digest")))   # plan 45
    if payload.get("drift"):
        lines.append(payload["drift"])
    if payload.get("branch"):
        lines.append(f"Branch: {payload['branch']}")
    if payload.get("gitDirty"):
        lines.append("⚠ Working tree has uncommitted changes — commit code+roadmap (or "
                     "inspect) before building more so nothing is agent-private.")
        for f in payload.get("dirtyFiles", [])[:10]:
            lines.append(f"  - {f}")
        if len(payload.get("dirtyFiles", [])) > 10:
            lines.append(f"  … {len(payload['dirtyFiles']) - 10} more")
    if handoff and payload.get("recentCommits"):
        lines.append("Recent commits:")
        lines.extend(f"  {c}" for c in payload["recentCommits"])
    if not handoff:
        lines.extend(f"⚠ {w}" for w in payload.get("health") or [])
    roles = payload.get("buildRoles")
    if roles:
        lines.append("Roles: " + " · ".join(f"{k}={v}" for k, v in roles.items())
                     + "  (settings.buildRoles — use when spawning build subagents)")
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
            "(/roadmap-next) — formal handoff is optional; git is the sync.")
    if handoff:
        lines.extend([
            "",
            "Multi-coder / rate-limit checklist:",
            "  1. Prefer micro-commits after every checked step (limits loss on rate-limit)",
            "  2. If you could not handoff: just open the other agent — run orient/handoff there",
            "  3. Commit any dirty tree (code + roadmap) the previous agent left",
            "  4. git pull/push if machines differ",
            "  5. Drift → /roadmap-catchup after tests; then next unfinished step",
            "  6. Continue quality-first build (do not re-plan from chat memory)",
            "Shared source of truth: ROADMAP.md + .roadmap/ + CHANGELOG*.md in git.",
        ])
    return "\n".join(lines)


def search(root: Path, text: str) -> list[dict]:
    """Case-insensitive substring search over item titles/notes, plan file bodies and
    Idea Incubator bullets. Every hit carries a locatable `ref`: a typed item id
    (FEAT-12) or file:line. No fuzzy matching, no regex — plain substring."""
    needle = text.lower()
    hits: list[dict] = []
    try:
        cfg = read_config(root)
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}
    for item in cfg.get("items", []):
        for field in ("title", "note"):
            value = item.get(field) or ""
            if needle in value.lower():
                hits.append({"kind": "item", "ref": display_id(item),
                             "id": item["id"], "field": field,
                             "text": " ".join(value.split())})
    for path in sorted((roadmap_dir(root) / "plans").glob("*.md")):
        for n, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if needle in line.lower():
                hits.append({"kind": "plan", "ref": f".roadmap/plans/{path.name}:{n}",
                             "file": f".roadmap/plans/{path.name}", "line": n,
                             "text": line.strip()})
    inc = incubator_file(root)
    try:
        rel = str(inc.relative_to(root))
    except ValueError:
        rel = str(inc)
    for b in list_incubator_bullets(root):
        if needle in b["body"].lower():
            hits.append({"kind": "idea", "ref": f"{rel}:{b['lineNo']}", "file": rel,
                         "line": b["lineNo"], "text": b["body"]})
    return hits


def format_search(hits: list[dict], query: str) -> str:
    if not hits:
        return f"No matches for {query!r}."
    lines = [f"{len(hits)} match(es) for {query!r}:"]
    for h in hits:
        suffix = f"  ({h['field']})" if h["kind"] == "item" else ""
        lines.append(f"  {h['kind']:<4} {h['ref']}  {h['text']}{suffix}")
    return "\n".join(lines)


def handoff(root: Path) -> dict | None:
    """Brief for switching between AI coders (Claude ↔ Grok ↔ …). Same data as orient
    with an explicit handoff checklist."""
    return orient(root)
