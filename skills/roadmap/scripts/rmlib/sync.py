"""roadmap sync & status — recompute progress, render ROADMAP.md, derive status,
auto-advance the current version, health checks, and dependency/next-item logic.
Layer: rmcore + rmparse + rmchangelog + rmbranches (read-only git discovery)."""
from __future__ import annotations
import datetime
import math
import sys
from collections import Counter
from pathlib import Path
from rmlib.core import (
    AUTO_END, AUTO_START, _norm_version, _set_frontmatter, _version_key,
    atomic_write, derive_status, display_id, read_config, roadmap_dir,
    write_config)
from rmlib.parse import (
    CLAIM_STAGES, count_progress, meta_ids, needs_approval, off_plan, parse_plan,
    read_claim, scope_allow, waiting_steps)
from rmlib.parse import acceptance_summary  # plan 43
from rmlib import branches as rmbranches
from rmlib import slots as rmslots
from rmlib import forecast as rmforecast
from rmlib import runs as rmruns
from rmlib import owners as rmowners
from rmlib import conflicts as rmconflicts
from rmlib.changelog import (
    render_internal_changelog, render_public_changelog)


def render_region(cfg: dict, progress: dict, waiting: dict | None = None) -> str:
    """`waiting` ({id: n waiting steps}, plan 46) adds ` (+n waiting)` to an item's
    line; waiting steps are already counted as open in `progress`."""
    waiting = waiting or {}
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    collapse = cfg.get("settings", {}).get("collapseShipped", True)
    dates = cfg.get("versionDates", {})
    current = _norm_version(cfg["currentVersion"])
    lines = ["## 📊 Versions", ""]
    for version in sorted(by_version, key=_version_key):
        items = sorted(by_version[version],
                       key=lambda i: (i.get("order", i["id"]), i["id"]))
        done_total = [progress.get(i["id"], (0, 0)) for i in items]
        d = sum(x for x, _ in done_total)
        t = sum(y for _, y in done_total)
        pct = round(100 * d / t) if t else 0
        marker = "x" if t and d == t else " "
        # Collapse shipped history: fully-done versions strictly below the current
        # one render as a single summary line (details live in CHANGELOG.internal.md
        # and .roadmap/plans/). The current/future versions always render in full.
        if collapse and marker == "x" and _version_key(version) < _version_key(current):
            n = len(items)
            shipped = f" · shipped {dates[version]}" if version in dates else ""
            lines.append(f"### [x] v{version} — 100% · {n} item{'s' if n != 1 else ''}"
                         f"{shipped} ([history](CHANGELOG.internal.md))")
            lines.append("")
            continue
        lines.append(f"### [{marker}] v{version} — {pct}%")
        for item in items:
            done, total = progress.get(item["id"], (0, 0))
            ipct = round(100 * done / total) if total else 0
            box = "x" if total and done == total else " "
            nw = waiting.get(item["id"]) or 0
            wtag = f" (+{nw} waiting)" if nw else ""
            lines.append(f"- [{box}] **#{item['id']} {item['title']}** "
                         f"`{item['type']}` — {ipct}%{wtag} "
                         f"([plan](.roadmap/{item['file']}))")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _version_complete(vitems: list, progress: dict) -> bool:
    """A version is complete when it has items and every one is 100% done."""
    if not vitems:
        return False
    for i in vitems:
        done, total = progress.get(i["id"], (0, 0))
        if not (total > 0 and done == total):
            return False
    return True


def uncut_complete_version(root: Path, cfg: dict | None = None) -> str | None:
    """The current version when every item in it is 100% done (and it has items) —
    finished work that has not been cut with `release` yet. None otherwise."""
    cfg = cfg or read_config(root)
    cur = cfg["currentVersion"]
    vitems = [i for i in cfg["items"] if i["version"] == cur]
    return cur if _version_complete(vitems, _progress_map(root, cfg)) else None


def _next_current_version(cfg: dict, by_version: dict, progress: dict):
    """If the current version is fully shipped, the version current should point
    at next: the lowest later version that is not yet complete, or (if every
    later version is also complete) the newest one. None = leave current as-is.

    Only advances a *completed* current version, so a freshly `release`-d empty
    future version (no items yet) is never skipped."""
    cur = cfg["currentVersion"]
    if not _version_complete(by_version.get(cur, []), progress):
        return None
    above = sorted((v for v in by_version if _version_key(v) > _version_key(cur)),
                   key=_version_key)
    # Only follow the work forward once a *shipped* (100%) version sits above the
    # current one — i.e. current has fallen behind a completed release. A freshly
    # added, still-incomplete next version alone is left to release()/build flow,
    # so an explicit release isn't pre-empted.
    if not any(_version_complete(by_version[v], progress) for v in above):
        return None
    for v in above:
        if not _version_complete(by_version[v], progress):
            return v            # land on the lowest still-open version above
    return above[-1]            # everything above is shipped too → newest


def sync(root: Path, quiet: bool = False) -> None:
    cfg = read_config(root)
    # Self-heal: enforce the canonical (no-'v') version form on stored data so a
    # project written before normalization (e.g. a `--version v1.0.0` that produced
    # `vv1.0.0`) repairs itself on the next sync.
    changed = False
    if _norm_version(cfg["currentVersion"]) != cfg["currentVersion"]:
        cfg["currentVersion"] = _norm_version(cfg["currentVersion"])
        changed = True
    for item in cfg["items"]:
        nv = _norm_version(item["version"])
        if nv != item["version"]:
            item["version"] = nv
            changed = True
            path = roadmap_dir(root) / item["file"]
            if path.exists():
                _set_frontmatter(path, "version", nv)
    if changed:
        write_config(root, cfg)
    progress, waiting = {}, {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            done, total = count_progress(path)
            progress[item["id"]] = (done, total)
            waiting[item["id"]] = len(parse_plan(path).get("waiting") or {})
            _set_frontmatter(path, "status", derive_status(done, total))
    # stamp a completion date when a version reaches 100% (deterministic changelog).
    # A version that is not yet cut (>= currentVersion) and regains incomplete work
    # loses its stamp, so the date always reflects the latest 100% transition;
    # shipped versions below currentVersion keep their historical dates.
    version_dates = cfg.setdefault("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    cur_key = _version_key(_norm_version(cfg["currentVersion"]))
    for version, vitems in by_version.items():
        if _version_complete(vitems, progress):
            if version not in version_dates:
                version_dates[version] = datetime.date.today().isoformat()
                changed = True
        elif version in version_dates and _version_key(version) >= cur_key:
            del version_dates[version]
            changed = True
    # drop dates for versions that no longer have any items (e.g. after a retarget)
    for stale in [v for v in version_dates if v not in by_version]:
        del version_dates[stale]
        changed = True
    # Auto-advance currentVersion: once the current version ships 100%, current
    # should follow the work to the next unfinished version — no hand-editing,
    # no stale pointer. Opt out with settings.autoAdvanceVersion = false.
    if cfg.get("settings", {}).get("autoAdvanceVersion", True):
        nxt = _next_current_version(cfg, by_version, progress)
        if nxt and nxt != cfg["currentVersion"]:
            cfg["currentVersion"] = nxt
            changed = True
    if changed:
        write_config(root, cfg)
    body = render_region(cfg, progress, waiting) if cfg["items"] else \
        "_No items yet. Use the roadmap skill to add one._\n"
    region = f"**Current version: v{cfg['currentVersion']}**\n\n{body}"
    rm_path = root / "ROADMAP.md"
    if not rm_path.exists():
        raise ValueError(f"ROADMAP.md not found at {rm_path}; run init first")
    text = rm_path.read_text(encoding="utf-8")
    if (text.count(AUTO_START) != 1 or text.count(AUTO_END) != 1
            or text.index(AUTO_START) > text.index(AUTO_END)):
        raise ValueError(
            "ROADMAP.md has missing or malformed roadmap:auto markers; restore "
            "exactly one '<!-- roadmap:auto:start -->' before "
            "'<!-- roadmap:auto:end -->'")
    before = text.split(AUTO_START)[0]
    after = text.split(AUTO_END)[1]
    atomic_write(rm_path, f"{before}{AUTO_START}\n{region}{AUTO_END}{after}")
    public_text, warnings = render_public_changelog(root)
    atomic_write(root / "CHANGELOG.md", public_text)
    atomic_write(root / "CHANGELOG.internal.md", render_internal_changelog(root))
    if not quiet:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)


MAX_ROADMAP_LINES = 150


MAX_FREEFORM_LINES = 40


MAX_FREEFORM_CHARS = 4000


def roadmap_health(root: Path) -> list[str]:
    """Size warnings for ROADMAP.md: the dashboard should stay skimmable. Only the
    free-form region is measured — the auto block is sync's job (shipped versions
    collapse via settings.collapseShipped), so its length never warns on its own.
    The free-form region only stays short if prose lives in .roadmap/notes/ files
    instead of inline; it is checked by both line count and character volume (prose
    dumps often sit on few, very long lines), and the warning names the largest
    section to trim. Surfaced by `orient` and `tidy` only, never on every command."""
    rm = root / "ROADMAP.md"
    if not rm.exists():
        return []
    lines = rm.read_text(encoding="utf-8").splitlines()
    warnings = []
    in_auto = False
    freeform = chars = auto = 0
    section, per_section = "top of file", Counter()
    for line in lines:
        if AUTO_START in line:
            in_auto = True
        elif AUTO_END in line:
            in_auto = False
        elif in_auto:
            auto += 1
        elif line.strip():
            freeform += 1
            chars += len(line)
            if line.startswith("## "):
                section = line[3:].strip()
            elif not line.startswith("# "):
                per_section[section] += 1
    if freeform > MAX_FREEFORM_LINES or chars > MAX_FREEFORM_CHARS:
        size = (f"{freeform} lines (> {MAX_FREEFORM_LINES})"
                if freeform > MAX_FREEFORM_LINES
                else f"{chars} characters (> {MAX_FREEFORM_CHARS})")
        where = ""
        if per_section:
            name, n = per_section.most_common(1)[0]
            where = f" — trim “{name}” ({n} lines)"
        warnings.append(
            f"ROADMAP.md free-form region (outside the auto block) is {size}{where}. "
            "Move long-form notes into linked files via `roadmap.py idea --title ... "
            "--body-file ...` (or `tidy --externalize`) and keep one bullet per idea.")
    # The auto block is sync's job — but only while collapse is on. With it off, a
    # long block is the one thing a setting fixes, so suggest it (orient/tidy only).
    if auto > MAX_ROADMAP_LINES:
        try:
            collapse = (read_config(root).get("settings") or {}).get("collapseShipped", True)
        except (ValueError, FileNotFoundError):
            collapse = True
        if collapse is False:
            warnings.append(
                f"ROADMAP.md auto block is {auto} lines (> {MAX_ROADMAP_LINES}) with "
                "settings.collapseShipped off — set it to true so shipped versions "
                "collapse to one line each on sync.")
    return warnings


# Lanes (plan 30) are display-only: they never feed done/active/planned, which
# stay derived from trunk checkboxes alone. Precedence, first match wins:
#   done (every trunk step ticked) > claim stage (what git cannot know) >
#   landed (branch contained in settings.integrationBranch, not trunk; plan 32) >
#   stale / building (a branch carrying unmerged work) > planned / active.
def _branch_has_work(branch: dict | None) -> bool:
    """A branch is in-flight work only when it holds commits trunk lacks. A
    fresh branch cut at the trunk tip (merged, nothing ahead, nothing tagged)
    is not building anything yet."""
    if not branch or branch.get("merged"):
        return False
    return (branch.get("ahead") or 0) > 0 or (branch.get("taggedCommits") or 0) > 0


def derive_lane(status: str, claim: dict | None, branch: dict | None,
                waiting: bool = False) -> str:
    """`waiting` (plan 46): every step is ticked except waiting ones — the work
    is built and only time-gated verification is left, so it outranks claims
    and branches (and keeps `check --landed` from ever ticking the wait)."""
    if status == "done":
        return "done"
    if waiting:
        return "waiting"
    stage = (claim or {}).get("stage")
    if stage in CLAIM_STAGES:          # a hand-edited unknown stage is ignored
        return stage
    if _branch_has_work(branch) and branch.get("landed"):
        return "landed"                 # merged into integration, not yet trunk
    if _branch_has_work(branch):
        # Stale is "idle in-flight work": only a branch that would otherwise
        # read as building can go stale, so an old empty branch stays quiet.
        return "stale" if branch.get("stale") else "building"
    return status


def is_in_flight(item: dict) -> bool:
    """Not done, and git (a branch) or the build loop (a claim) says work is
    under way. The one predicate behind `status --in-flight` and the counts.
    A `waiting` item (plan 46) is parked on time, not in flight."""
    return item.get("lane") not in ("done", "waiting") \
        and bool(item.get("branch") or item.get("claim"))


def lane_counts(items: list[dict]) -> dict[str, int]:
    """done / inFlight / active / planned / waiting — every item lands in
    exactly one. `active` holds trunk-active items with no branch and no claim;
    `waiting` (plan 46) items whose only open steps wait on a date."""
    out = {"done": 0, "inFlight": 0, "active": 0, "planned": 0, "waiting": 0}
    for i in items:
        if i.get("lane") == "done":
            out["done"] += 1
        elif i.get("lane") == "waiting":
            out["waiting"] += 1
        elif is_in_flight(i):
            out["inFlight"] += 1
        elif i.get("status") == "active":
            out["active"] += 1
        else:
            out["planned"] += 1
    return out


def lane_label(item: dict) -> str:
    """`building · roadmap/7 · +4` / `gate-ready · roadmap/7 · CONFIRMED · +4` /
    `landed · roadmap/7 · @1a2b3c4 · +4` (the commit it landed in)."""
    lane = item.get("lane") or item.get("status") or "?"
    parts = [lane]
    if lane == "waiting":                  # plan 46: `waiting · step 3 · 4d left`
        for w in item.get("waitingSteps") or []:
            parts.append(f"step {w['step']}")
            if w.get("on") and not w.get("until"):     # plan 53: open-ended
                parts.append(awaiting_label(w))
                continue
            parts.append(countdown(w.get("daysLeft"), w.get("hoursLeft")))
            if w.get("on"):
                parts.append(f"awaiting {w['on']}")
        return " · ".join(parts)
    branch, claim = item.get("branch"), item.get("claim") or {}
    if branch:
        parts.append(branch["name"])
    if lane == "landed":
        sha = claim.get("landed_sha") or (branch or {}).get("landedSha")
        if sha:
            parts.append(f"@{sha[:7]}")
    if claim.get("verdict"):
        parts.append(claim["verdict"])
    if branch and branch.get("ahead"):
        parts.append(f"+{branch['ahead']}")
    return " · ".join(parts)


def countdown(days_left: int | None, hours_left: int | None = None) -> str:
    """`4d left` / `due` / `2d overdue` for a waiting step (plan 46). A wait due
    at a time of day (plan 53, `hours_left` set) reads in hours while it is
    under 2 days away or overdue: `5h left` / `due` / `3h overdue`."""
    if hours_left is not None and abs(hours_left) < 48:
        if hours_left > 0:
            return f"{hours_left}h left"
        return "due" if hours_left == 0 else f"{-hours_left}h overdue"
    if days_left is None:
        return "no date"
    if days_left > 0:
        return f"{days_left}d left"
    return "due" if days_left == 0 else f"{-days_left}d overdue"


def wait_left(until: str | None, today: datetime.date,
              now: datetime.datetime | None = None) -> tuple[int | None, int | None]:
    """(daysLeft, hoursLeft) for a wait's `until`. A date (plan 46): whole days
    from `today`, hoursLeft None. A UTC time `YYYY-MM-DDTHH:MMZ` (plan 53):
    hoursLeft rounds up while time remains (`1h left`, never `0h left`) and is 0
    for the first hour past due; daysLeft follows it — >= 1 until the time is
    reached, 0 for the first day past it — so every `daysLeft <= 0` due check
    holds for both kinds. (None, None) when there is no readable date."""
    if not until:
        return None, None
    if "T" in until:
        try:
            due = datetime.datetime.strptime(until, "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            return None, None
        now = now or datetime.datetime.now(datetime.timezone.utc)
        secs = (due - now).total_seconds()
        hours = math.ceil(secs / 3600) if secs > 0 else int(secs / 3600)
        days = max(1, hours // 24) if hours > 0 else -((-hours) // 24)
        return days, hours
    try:
        return (datetime.date.fromisoformat(until) - today).days, None
    except ValueError:
        return None, None


DEFAULT_WAIT_NUDGE_DAYS = 7


def wait_nudge_days(cfg: dict) -> int:
    """settings.waitNudgeDays (plan 53, default 7): an open-ended wait on
    someone this many days old or older needs attention."""
    try:
        return int((cfg.get("settings") or {}).get("waitNudgeDays",
                                                   DEFAULT_WAIT_NUDGE_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_WAIT_NUDGE_DAYS


def awaiting_label(w: dict) -> str:
    """`awaiting dispatch team · 3d` — an open-ended wait's badge (plan 53)."""
    days = w.get("waitingDays")
    return f"awaiting {w.get('on')}" + (f" · {days}d" if isinstance(days, int) else "")


def _days(n: int) -> str:
    return f"{n} day{'' if n == 1 else 's'}"


def _waiting_rows(path: Path, today: datetime.date,
                  now: datetime.datetime | None = None) -> list[dict]:
    """waiting_steps() plus `daysLeft` (None when the step has no date) and, for
    a wait due at a time of day (plan 53), `hoursLeft`."""
    out = []
    for w in waiting_steps(path):
        days, hours = wait_left(w.get("until"), today, now)
        row = {**w, "daysLeft": days}
        if hours is not None:
            row["hoursLeft"] = hours
        if w.get("on"):                     # plan 53: days since the wait began
            try:
                row["waitingDays"] = (today - datetime.date.fromisoformat(
                    w.get("since") or "")).days
            except ValueError:
                row["waitingDays"] = None
        out.append(row)
    return out


def due_waiting(items: list[dict]) -> list[dict]:
    """Every waiting step due today or overdue across `items` (status rows),
    most overdue first: {id, displayId, title, version, step, text, until,
    reason, daysLeft}."""
    due = [{"id": i["id"], "displayId": i.get("displayId"), "title": i["title"],
            "version": i["version"], **w}
           for i in items for w in i.get("waitingSteps") or []
           if w.get("daysLeft") is not None and w["daysLeft"] <= 0]
    return sorted(due, key=lambda d: (d["daysLeft"], d.get("hoursLeft", 0),
                                      d["id"], d["step"]))


def format_due(due: list[dict]) -> list[str]:
    """One reminder line per due waiting step, with the command that ticks it."""
    return [f"⏰ {d['displayId'] or '#' + str(d['id'])} step {d['step']} "
            f"({countdown(d['daysLeft'], d.get('hoursLeft'))}"
            + (f", awaiting {d['on']}" if d.get("on") else "")
            + (f": {d['reason']}" if d.get("reason") else "") + f") — {d['text']} "
            f"→ verify, then: roadmap.py check --plan {d['id']} --step {d['step']}"
            for d in due]


def awaiting_waits(items: list[dict]) -> list[dict]:
    """Every open-ended wait on someone (plan 53: `on`, no date) across `items`
    (status rows), longest-waiting first: {id, displayId, title, version, step,
    text, until, reason, on, since, daysLeft, waitingDays}. Never due, never
    overdue — listed every day until the step is checked."""
    rows = [{"id": i["id"], "displayId": i.get("displayId"), "title": i["title"],
             "version": i["version"], **w}
            for i in items if i.get("lane") != "done"
            for w in i.get("waitingSteps") or []
            if w.get("on") and not w.get("until")]
    return sorted(rows, key=lambda d: (-(d.get("waitingDays") or 0), d["id"], d["step"]))


def format_awaiting(rows: list[dict]) -> list[str]:
    """One reminder line per open-ended wait (plan 53): who, since when, and the
    command that ends it."""
    out = []
    for d in rows:
        days = d.get("waitingDays")
        since = (f"since {d['since']}" if d.get("since") else "since ?") \
            + (f", {_days(days)}" if isinstance(days, int) else "")
        out.append(f"⏳ {d.get('displayId') or '#' + str(d['id'])} step {d['step']} "
                   f"awaiting {d['on']} ({since})"
                   + (f": {d['reason']}" if d.get("reason") else "")
                   + f" — {d['text']} → once they report back: roadmap.py check "
                     f"--plan {d['id']} --step {d['step']}")
    return out


def _public_branch(info: dict, item_id: int) -> dict:
    """Status payload branch record: discovery info minus the commit list (the
    item detail view fetches commits on demand, so status stays small)."""
    return {**{k: v for k, v in info.items() if k != "commits"}, "item": item_id}


def _discover(root: Path, cfg: dict) -> dict:
    """One discovery per status() call, settings taken from the config already
    in hand (no second read). Never raises: outside git, without git, or on any
    git trouble the result is simply empty."""
    settings = cfg.get("settings") or {}
    pattern = settings.get("branchPattern")
    if not isinstance(pattern, str) or not pattern:
        pattern = rmbranches.DEFAULT_PATTERN
    try:
        stale_days = int(settings.get("staleDays", rmbranches.DEFAULT_STALE_DAYS))
    except (TypeError, ValueError):
        stale_days = rmbranches.DEFAULT_STALE_DAYS
    integration = settings.get("integrationBranch")
    try:
        return rmbranches.discover(root, [i["id"] for i in cfg["items"]],
                                   pattern=pattern, stale_days=stale_days,
                                   integration=integration or None)
    except Exception:  # noqa: BLE001 — status must survive any git surprise
        return {"trunk": None, "items": {}, "other": []}


def status(root: Path, worktrees: bool = False, conflicts: bool = False,
           drift: bool = False) -> dict:
    """Status payload. `worktrees=True` adds the worktree map (plan 36) —
    opt-in because it costs one `git status` per linked worktree.
    `conflicts=True` adds branch conflict risk (plan 41) — opt-in because a
    cold cache costs one `git diff` per branch and one merge-tree per pair.
    `drift=True` adds scope drift (plan 42): top-level `scopeDrift`, and
    `offPlan` on each item row it checked — opt-in for the same diff cost."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    # Full progress map first — blockedBy for early ids must see later deps' progress.
    progress = _progress_map(root, cfg)
    found = _discover(root, cfg)
    by_name = {b["name"]: b for b in [*found["items"].values(), *found["other"]]}
    other_names = {b["name"] for b in found["other"]}
    claimed_from_other: set[str] = set()
    today = datetime.date.today()
    now = datetime.datetime.now(datetime.timezone.utc)
    items = []
    for item in cfg["items"]:
        done, total = progress.get(item["id"], (0, 0))
        pct = round(100 * done / total) if total else 0
        blocked_by = _incomplete_deps(item, progress, by_id)
        path = roadmap_dir(root) / item["file"]
        claim = read_claim(path) if path.exists() else None
        plan = parse_plan(path) if path.exists() else {}   # cached: no re-read
        # A claim naming its branch wins over discovery; a named branch that no
        # longer exists (deleted, or merged and not chosen) falls back to it.
        info = by_name.get((claim or {}).get("branch") or "") \
            or found["items"].get(item["id"])
        if info is not None and info["name"] in other_names:
            claimed_from_other.add(info["name"])
        branch = _public_branch(info, item["id"]) if info else None
        st = derive_status(done, total)
        # Waiting steps (plan 46): counted open in done/total; `waiting` counts
        # them separately and the lane flips once they are all that is left.
        wrows = _waiting_rows(path, today, now) if path.exists() else []
        waits = bool(wrows) and done + len(wrows) == total
        row = {**item, "displayId": display_id(item),
               "done": done, "total": total, "pct": pct,
               "status": st,
               "waiting": len(wrows), "waitingSteps": wrows,
               "dependsOn": list(item.get("dependsOn") or []),
               "blockedBy": blocked_by,
               "lane": derive_lane(st, claim, branch, waiting=waits),
               "claim": claim, "branch": branch,
               # Rulings (plan 34): dated decisions from the plan body.
               "rulings": list(plan.get("rulings") or []),
               "needsApproval": needs_approval(plan) if plan else False,
               # Bug routing (plan 47): origin link, back-links, in-place fixes.
               "foundIn": next(iter(meta_ids(plan.get("meta") or {}, "foundIn")), None),
               "bugsFound": meta_ids(plan.get("meta") or {}, "bugsFound"),
               "foundDuringBuild": list(plan.get("foundDuringBuild") or []),
               # Acceptance ledger (plan 43): {met, failed, total} over criteria.
               "acceptance": acceptance_summary(plan.get("acceptance") or [])}
        items.append(row)
    cur_items = [i for i in cfg["items"] if i["version"] == cfg["currentVersion"]]
    # Counts cover every item — callers may filter `items`, the summary stays global.
    counts = {key: dict(Counter(i[field] for i in items))
              for key, field in (("byType", "type"), ("byStatus", "status"),
                                 ("byVersion", "version"), ("byLane", "lane"))}
    counts["lanes"] = lane_counts(items)
    other = [_public_branch(b, b["item"]) for b in found["other"]
             if b["name"] not in claimed_from_other]
    # Numbered slots (plan 33): only present when settings.slots is configured,
    # so projects without it see an unchanged payload.
    extra = ({"slots": rmslots.slots_status(root, cfg, items, found)}
             if (cfg.get("settings") or {}).get("slots") else {})
    # Waiting steps due today or overdue, most overdue first (plan 46) — only
    # when some item has a waiting step, so other projects' payload is unchanged.
    if any(i["waiting"] for i in items):
        extra["waitingDue"] = due_waiting(items)
        # Open-ended waits on someone (plan 53): listed every day, never due.
        extra["waitingOn"] = awaiting_waits(items)
    # Run log (plan 38): last runs, trunk health, and skipped-line warnings.
    extra.update(rmruns.runs_status(root, cfg, found["trunk"]))
    # Work-in-progress limit (plan 40): only present when settings.wipLimit is set.
    wip = rmowners.wip(counts["lanes"]["inFlight"], cfg)
    if wip:
        extra["wip"] = wip
    out = {"project": cfg["project"], "currentVersion": cfg["currentVersion"],
           "versionComplete": _version_complete(cur_items, progress),
           "counts": counts, "items": items,
           "trunk": found["trunk"], "otherBranches": other,
           # Version forecast from recent pace (plan 44): {version: forecast}.
           "forecast": rmforecast.forecast(root, cfg, progress), **extra}
    if worktrees:
        out["worktrees"] = worktree_payload(root, out, cfg)
    if conflicts:
        out["conflicts"] = conflicts_payload(root, out, cfg,
                                             trunk_sha=found.get("trunkSha"))
    if drift:
        out["scopeDrift"] = scope_drift_payload(root, out, cfg)
        by_item = out["scopeDrift"]["byItem"]
        for row in items:
            if row["id"] in by_item:
                row["offPlan"] = by_item[row["id"]]
    return out


# --- scope drift per branch (plan 42) --------------------------------------
DRIFT_SHOWN = 10          # off-plan files listed per item in the text report


def _declared(root: Path, item: dict) -> list[str]:
    path = roadmap_dir(root) / item["file"]
    try:
        return list(parse_plan(path).get("declaredPaths") or []) \
            if path.exists() else []
    except (OSError, UnicodeDecodeError):
        return []


def scope_drift_payload(root: Path, st: dict, cfg: dict | None = None) -> dict:
    """Off-plan files on every open item branch of a status payload `st`
    (not done, carrying unmerged work): the files the branch itself changes
    (rmconflicts.own_changed_files — vs trunk, or vs the integration branch it
    was cut from) that neither its plan's declared paths nor the allow list
    (settings.scopeAllow + defaults) cover. Items sharing a branch are one
    entry judged against all their plans; an integration branch also counts
    the plans of the items landed in it. Returns
      {checked, flagged, noScope: [ids], unknown: [branches], allow,
       items: [{id, displayId, title, branch, items, base, declared,
                changed, offPlan, offPlanCount, noScope}],
       byItem: {id: offPlan list, or None when its entry has no declared scope}}
    items sort off-plan first (most files first), then no declared scope,
    then clean. Never raises."""
    out = {"checked": 0, "flagged": 0, "noScope": [], "unknown": [],
           "allow": [], "items": [], "byItem": {}}
    try:
        cfg = cfg if cfg is not None else read_config(root)
    except Exception:  # noqa: BLE001 — status must survive any surprise
        return out
    settings = cfg.get("settings") or {}
    integ = settings.get("integrationBranch") or None
    allow = scope_allow(settings)
    out["allow"] = allow
    nodes: dict[str, dict] = {}
    landed_in: dict[str, list[dict]] = {}
    for it in sorted(st.get("items") or [], key=lambda i: i["id"]):
        b = it.get("branch")
        if it.get("lane") == "done" or not _branch_has_work(b) or not b.get("sha"):
            continue
        if b.get("landedIn"):
            landed_in.setdefault(b["landedIn"], []).append(it)
        n = nodes.get(b["name"])
        if n is None:
            nodes[b["name"]] = {"lead": it, "members": [it]}
        else:
            n["members"].append(it)
    entries = []
    for name, n in nodes.items():
        lead = n["lead"]
        try:
            files, wb = rmconflicts.own_changed_files(root, name, None, integ)
        except Exception:  # noqa: BLE001
            files, wb = None, None
        if files is None:
            out["unknown"].append(name)
            continue
        plans = n["members"] + [x for x in landed_in.get(name, [])
                                if x not in n["members"]]
        declared = list(dict.fromkeys(p for x in plans for p in _declared(root, x)))
        no_scope = not declared
        flagged = [] if no_scope else off_plan(files, declared, allow)
        entries.append({
            "id": lead["id"], "displayId": lead.get("displayId"),
            "title": lead.get("title"), "branch": name,
            "items": [m["id"] for m in n["members"]],
            "base": ({"kind": wb["kind"], "ref": wb["ref"], "sha": wb["sha"]}
                     if wb else None),
            "declared": declared, "changed": len(files),
            "offPlan": flagged, "offPlanCount": len(flagged),
            "noScope": no_scope})
    entries.sort(key=lambda e: (0 if e["offPlanCount"] else
                                1 if e["noScope"] else 2,
                                -e["offPlanCount"], e["id"]))
    for e in entries:
        for i in e["items"]:
            out["byItem"][i] = None if e["noScope"] else list(e["offPlan"])
    out["checked"] = len(entries)
    out["flagged"] = sum(1 for e in entries if e["offPlanCount"])
    out["noScope"] = [i for e in entries if e["noScope"] for i in e["items"]]
    out["items"] = entries
    return out


def format_scope_drift(rep: dict | None, shown: int = DRIFT_SHOWN) -> str:
    """Terminal text for `status --drift`: a summary line, then each item
    branch with off-plan files (first `shown`), then the ones with no
    declared scope, then the clean ones on one line."""
    rep = rep or {}
    entries = rep.get("items") or []
    lines = [f"scope drift: {rep.get('checked', 0)} open item branches · "
             f"{rep.get('flagged', 0)} off-plan · "
             f"{sum(1 for e in entries if e['noScope'])} no declared scope"]

    def tag(e: dict) -> str:
        more = len(e.get("items") or []) - 1
        base = e.get("base") or {}
        since = (f", vs {base['ref']}" if base.get("kind") == "integration" else
                 f", since {base['sha'][:7]} on {base['ref']}"
                 if base.get("kind") == "fork" else "")
        return (f"{e.get('displayId') or '#' + str(e['id'])}"
                f"{f' +{more}' if more > 0 else ''} {e.get('title') or ''}"
                f" ({e['branch']}{since})")

    for e in entries:
        if e["offPlanCount"]:
            more = e["offPlanCount"] - shown
            files = ", ".join(e["offPlan"][:shown]) + (
                f", +{more} more" if more > 0 else "")
            lines.append(f"  {tag(e)} · {e['offPlanCount']} off-plan of "
                         f"{e['changed']} changed: {files}")
        elif e["noScope"]:
            lines.append(f"  {tag(e)} · no declared scope ({e['changed']} changed)")
    clean = [e for e in entries if not e["offPlanCount"] and not e["noScope"]]
    if clean:
        lines.append("  within plan: " + ", ".join(
            e.get("displayId") or "#" + str(e["id"]) for e in clean))
    if rep.get("unknown"):
        lines.append(f"  unreadable: {', '.join(rep['unknown'])}")
    return "\n".join(lines)


# --- branch conflict risk (plan 41) ----------------------------------------
def conflicts_payload(root: Path, st: dict, cfg: dict | None = None,
                      trunk_sha: str | None = None) -> dict:
    """Conflict risk across the open item branches of a status payload `st`
    already in hand: every not-done item whose branch carries unmerged work
    (rmconflicts.overlaps), using the branch tips in `st`. Without `trunk_sha`
    the trunk tip comes from the cached ref scan (one for-each-ref); every
    diff and merge-tree is cached on shas, so unchanged refs cost nothing
    more. Never raises."""
    try:
        if trunk_sha is None:
            cfg = cfg if cfg is not None else read_config(root)
            integ = (cfg.get("settings") or {}).get("integrationBranch") or None
            scanned = rmbranches._scan_cached(Path(root), None, integ)
            trunk_sha = scanned[1].get("trunkSha") if scanned else None
    except Exception:  # noqa: BLE001 — status must survive any git surprise
        trunk_sha = None
    cands = []
    for it in st.get("items") or []:
        b = it.get("branch")
        if it.get("lane") == "done" or not _branch_has_work(b) or not b.get("sha"):
            continue
        cands.append({"id": it["id"], "displayId": it.get("displayId"),
                      "title": it.get("title"), "branch": b["name"],
                      "sha": b["sha"], "landedIn": b.get("landedIn")})
    try:
        return rmconflicts.overlaps(root, trunk_sha, cands)
    except Exception:  # noqa: BLE001 — status must survive any git surprise
        return rmconflicts.overlaps(root, None, [])


# --- worktree map (plan 36) ------------------------------------------------
DEFAULT_WORKTREE_WARN = 20


def _worktree_warn(settings: dict) -> int:
    try:
        n = int(settings.get("worktreeWarn", DEFAULT_WORKTREE_WARN))
    except (TypeError, ValueError):
        return DEFAULT_WORKTREE_WARN
    return n if n >= 0 else DEFAULT_WORKTREE_WARN


def worktree_payload(root: Path, st: dict, cfg: dict | None = None,
                     max_age: float | None = None) -> dict:
    """The worktree map for a status payload `st` already in hand: every linked
    worktree (rmbranches.worktrees) tagged with the item its branch belongs to
    (the item's discovered or claimed branch, else settings.branchPattern), that
    item's lane and claim stage. {"trunk", "count", "safe", "warnAt", "over",
    "rows"}; `over` = count > settings.worktreeWarn (default 20). Never raises
    and never removes anything: `removeCmd` is text for the caller to print."""
    try:
        cfg = cfg if cfg is not None else read_config(root)
    except (ValueError, FileNotFoundError, OSError):
        cfg = {}
    settings = cfg.get("settings") or {}
    warn = _worktree_warn(settings)
    kw = {} if max_age is None else {"max_age": max_age}
    try:
        res = rmbranches.worktrees(
            root, integration=settings.get("integrationBranch") or None, **kw)
    except Exception:  # noqa: BLE001 — status must survive any git surprise
        res = {"trunk": None, "rows": []}
    items = st.get("items") or []
    by_branch: dict[str, dict] = {}
    for it in items:
        for name in ((it.get("claim") or {}).get("branch"),
                     (it.get("branch") or {}).get("name")):
            if name:
                by_branch.setdefault(name, it)
    by_id = {it["id"]: it for it in items}
    pattern = settings.get("branchPattern")
    name_re = rmbranches._pattern_re(pattern if isinstance(pattern, str) and pattern
                                     else rmbranches.DEFAULT_PATTERN)
    rows = []
    for r in res["rows"]:
        it = by_branch.get(r["branch"] or "")
        if it is None and r["branch"] and name_re:
            m = name_re.match(r["branch"])
            it = by_id.get(int(m.group(1))) if m else None
        rows.append({**r, "item": it["id"] if it else None,
                     "displayId": it.get("displayId") if it else None,
                     "title": it.get("title") if it else None,
                     "lane": it.get("lane") if it else None,
                     "stage": ((it.get("claim") or {}).get("stage") if it else None)})
    n = len(rows)
    return {"trunk": res["trunk"], "count": n,
            "safe": sum(1 for r in rows if r["safe"]),
            "warnAt": warn, "over": n > warn, "rows": rows}


def _ago(iso: str | None, now: datetime.datetime | None = None) -> str:
    """`5m` / `3h` / `2d` / `6w` since an ISO date; empty when unparsable."""
    if not iso:
        return ""
    try:
        when = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    secs = max(0, int((now - when).total_seconds()))
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return "now"


def format_worktrees(payload: dict | None) -> str:
    """Terminal table for `status --worktrees`, then the removal command for
    every safe worktree — printed for the user to run, never run here."""
    payload = payload or {"count": 0, "safe": 0, "warnAt": DEFAULT_WORKTREE_WARN,
                          "over": False, "rows": []}
    n, safe = payload["count"], payload["safe"]
    head = (f"worktrees: {n} linked · {safe} safe to remove"
            + (f" · over worktreeWarn ({payload['warnAt']})" if payload["over"] else ""))
    if not n:
        return head
    table = [("BRANCH", "ITEM", "LANE", "DIRTY", "UNMERGED", "STAGE", "AGE",
              "SAFE", "PATH")]
    for r in payload["rows"]:
        num = lambda v: "?" if v is None else str(v)
        table.append((
            r["branch"] or f"(detached {r['head'] or '?'})",
            r["displayId"] or (f"#{r['item']}" if r["item"] else "-"),
            r["lane"] or "-", num(r["dirty"]), num(r["ahead"]),
            r["stage"] or "-", _ago(r["lastDate"]) or "-",
            "yes" if r["safe"] else f"no ({r['reason']})", r["path"]))
    widths = [max(len(row[i]) for row in table) for i in range(len(table[0]) - 1)]
    lines = [head]
    for row in table:
        lines.append("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths))
                     + "  " + row[-1])
    cmds = [r["removeCmd"] for r in payload["rows"] if r["safe"] and r["removeCmd"]]
    if cmds:
        lines.append("safe to remove (run yourself; nothing was removed):")
        lines.extend(f"  {c}" for c in cmds)
    return "\n".join(lines)


def _item_done(progress: dict[int, tuple[int, int]], plan_id: int) -> bool:
    done, total = progress.get(plan_id, (0, 0))
    return total > 0 and done == total


def _incomplete_deps(item: dict, progress: dict[int, tuple[int, int]],
                     by_id: dict[int, dict]) -> list[int]:
    """Dependency ids that exist and are not 100% complete."""
    out = []
    for d in item.get("dependsOn") or []:
        if d not in by_id:
            continue
        if not _item_done(progress, d):
            out.append(d)
    return out


def _progress_map(root: Path, cfg: dict | None = None) -> dict[int, tuple[int, int]]:
    cfg = cfg or read_config(root)
    progress = {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        progress[item["id"]] = count_progress(path) if path.exists() else (0, 0)
    return progress


def incomplete_deps(root: Path, plan_id: int) -> list[int]:
    """Return dependency plan ids that are not yet 100% complete."""
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    if plan_id not in by_id:
        raise ValueError(f"no plan with id {plan_id}")
    return _incomplete_deps(by_id[plan_id], _progress_map(root, cfg), by_id)


def warn_incomplete_deps(root: Path, plan_id: int, force: bool = False) -> list[int]:
    """Warn when building an item whose dependencies are incomplete. Returns blocker ids.
    Non-blocking unless the caller chooses to stop; --force silences the warning."""
    blocked = incomplete_deps(root, plan_id)
    if blocked and not force:
        print(f"warning: #{plan_id} depends on incomplete item(s) {blocked}; "
              f"prefer finishing them first (`roadmap.py next`), or continue carefully",
              file=sys.stderr)
    return blocked


def next_item(root: Path, version: str | None = None,
              force: bool = False, quiet: bool = False,
              owner: str | None = None) -> dict | None:
    """Pick the next unfinished item in `version` (default: currentVersion).

    Order: explicit `order` field, then id. Skips items whose `dependsOn` targets are
    not 100% complete (unless force=True), and items held by another owner (plan
    40; `owner` defaults to rmowners.default_owner — force does not override a
    hold). Prints skipped items, and the settings.wipLimit warning, to stderr
    unless quiet=True. Returns an enriched
    status row, or None if every item is done / only blocked or held remain.
    """
    st = status(root)
    ver = _norm_version(version or st["currentVersion"])
    # A `waiting` item (plan 46) has nothing to do until a wait falls due; a due
    # one comes first (most overdue first) — verifying it is the next thing to do.
    def overdue(i: dict) -> int | None:
        left = [w["daysLeft"] for w in i.get("waitingSteps") or []
                if w.get("daysLeft") is not None and w["daysLeft"] <= 0]
        return min(left) if left else None
    candidates = [i for i in st["items"] if i["version"] == ver and i["pct"] < 100
                  and not (i["lane"] == "waiting" and overdue(i) is None)]
    candidates.sort(key=lambda i: (
        (0, overdue(i)) if i["lane"] == "waiting" else (1, 0),
        i.get("order", i["id"]), i["id"]))
    me = rmowners.clean_owner(owner) or rmowners.default_owner(root)
    ttl = rmowners.claim_ttl_hours(read_config(root))
    over = rmowners.wip_warning(st.get("wip"))
    if over and not quiet:
        print(f"warning: {over}", file=sys.stderr)
    skipped = []
    for item in candidates:
        blocked = item.get("blockedBy") or []
        if blocked and not force:
            skipped.append((item["displayId"], f"blocked by {blocked}"))
            continue
        held = rmowners.held_by_other(item.get("claim"), me, ttl)
        if held:
            a = rmowners.age(item.get("claim"))
            skipped.append((item["displayId"],
                            f"held by {held}" + (f", {a}" if a else "")))
            continue
        if skipped and not quiet:
            for sid, why in skipped:
                print(f"skipping {sid} ({why})", file=sys.stderr)
        return item
    if skipped and not quiet:
        for sid, why in skipped:
            print(f"skipping {sid} ({why})", file=sys.stderr)
        print(f"no unblocked unfinished items in v{ver}", file=sys.stderr)
        return None
    return None
