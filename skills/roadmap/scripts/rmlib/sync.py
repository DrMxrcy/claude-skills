"""roadmap sync & status — recompute progress, render ROADMAP.md, derive status,
auto-advance the current version, health checks, and dependency/next-item logic.
Layer: rmcore + rmparse + rmchangelog + rmbranches (read-only git discovery)."""
from __future__ import annotations
import datetime
import sys
from collections import Counter
from pathlib import Path
from rmlib.core import (
    AUTO_END, AUTO_START, _norm_version, _set_frontmatter, _version_key,
    atomic_write, derive_status, display_id, read_config, roadmap_dir,
    write_config)
from rmlib.parse import (
    CLAIM_STAGES, count_progress, read_claim)
from rmlib import branches as rmbranches
from rmlib import slots as rmslots
from rmlib.changelog import (
    render_internal_changelog, render_public_changelog)


def render_region(cfg: dict, progress: dict) -> str:
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
            lines.append(f"- [{box}] **#{item['id']} {item['title']}** "
                         f"`{item['type']}` — {ipct}% "
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
    progress = {}
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        if path.exists():
            done, total = count_progress(path)
            progress[item["id"]] = (done, total)
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
    body = render_region(cfg, progress) if cfg["items"] else \
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


def derive_lane(status: str, claim: dict | None, branch: dict | None) -> str:
    if status == "done":
        return "done"
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
    under way. The one predicate behind `status --in-flight` and the counts."""
    return item.get("lane") != "done" and bool(item.get("branch") or item.get("claim"))


def lane_counts(items: list[dict]) -> dict[str, int]:
    """done / inFlight / active / planned — every item lands in exactly one.
    `active` holds trunk-active items with no branch and no claim."""
    out = {"done": 0, "inFlight": 0, "active": 0, "planned": 0}
    for i in items:
        if i.get("lane") == "done":
            out["done"] += 1
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


def status(root: Path) -> dict:
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    # Full progress map first — blockedBy for early ids must see later deps' progress.
    progress = _progress_map(root, cfg)
    found = _discover(root, cfg)
    by_name = {b["name"]: b for b in [*found["items"].values(), *found["other"]]}
    other_names = {b["name"] for b in found["other"]}
    claimed_from_other: set[str] = set()
    items = []
    for item in cfg["items"]:
        done, total = progress.get(item["id"], (0, 0))
        pct = round(100 * done / total) if total else 0
        blocked_by = _incomplete_deps(item, progress, by_id)
        path = roadmap_dir(root) / item["file"]
        claim = read_claim(path) if path.exists() else None
        # A claim naming its branch wins over discovery; a named branch that no
        # longer exists (deleted, or merged and not chosen) falls back to it.
        info = by_name.get((claim or {}).get("branch") or "") \
            or found["items"].get(item["id"])
        if info is not None and info["name"] in other_names:
            claimed_from_other.add(info["name"])
        branch = _public_branch(info, item["id"]) if info else None
        st = derive_status(done, total)
        row = {**item, "displayId": display_id(item),
               "done": done, "total": total, "pct": pct,
               "status": st,
               "dependsOn": list(item.get("dependsOn") or []),
               "blockedBy": blocked_by,
               "lane": derive_lane(st, claim, branch),
               "claim": claim, "branch": branch}
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
    return {"project": cfg["project"], "currentVersion": cfg["currentVersion"],
            "versionComplete": _version_complete(cur_items, progress),
            "counts": counts, "items": items,
            "trunk": found["trunk"], "otherBranches": other, **extra}


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
              force: bool = False, quiet: bool = False) -> dict | None:
    """Pick the next unfinished item in `version` (default: currentVersion).

    Order: explicit `order` field, then id. Skips items whose `dependsOn` targets are
    not 100% complete (unless force=True). Prints skipped blocked items to stderr
    unless quiet=True. Returns an enriched status row, or None if every item is done
    / only blocked remain.
    """
    st = status(root)
    ver = _norm_version(version or st["currentVersion"])
    candidates = [i for i in st["items"] if i["version"] == ver and i["pct"] < 100]
    candidates.sort(key=lambda i: (i.get("order", i["id"]), i["id"]))
    skipped = []
    for item in candidates:
        blocked = item.get("blockedBy") or []
        if blocked and not force:
            skipped.append((item["displayId"], blocked))
            continue
        if skipped and not quiet:
            for sid, deps in skipped:
                print(f"skipping {sid} (blocked by {deps})", file=sys.stderr)
        return item
    if skipped and not quiet:
        for sid, deps in skipped:
            print(f"skipping {sid} (blocked by {deps})", file=sys.stderr)
        print(f"no unblocked unfinished items in v{ver}", file=sys.stderr)
        return None
    return None
