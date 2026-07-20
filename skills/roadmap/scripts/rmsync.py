"""roadmap sync & status — recompute progress, render ROADMAP.md, derive status,
auto-advance the current version, health checks, and dependency/next-item logic.
Layer: rmcore + rmparse + rmchangelog."""
from __future__ import annotations
import datetime
import sys
from pathlib import Path
from rmcore import (
    AUTO_END, AUTO_START, _norm_version, _set_frontmatter, _version_key,
    atomic_write, derive_status, read_config, roadmap_dir, write_config)
from rmparse import (
    count_progress)
from rmchangelog import (
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
    # stamp a completion date the first time a version reaches 100% (deterministic changelog)
    version_dates = cfg.setdefault("versionDates", {})
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    for version, vitems in by_version.items():
        if version in version_dates:
            continue
        if vitems and all(progress.get(i["id"], (0, 0))[1] > 0
                          and progress.get(i["id"], (0, 0))[0] == progress.get(i["id"], (0, 0))[1]
                          for i in vitems):
            version_dates[version] = datetime.date.today().isoformat()
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
    """Size warnings for ROADMAP.md: the dashboard should stay skimmable. The auto
    region is bounded by collapsing shipped versions; the free-form region only stays
    short if prose lives in .roadmap/notes/ files instead of inline. Checked by both
    line count and character volume (prose dumps often sit on few, very long lines)."""
    rm = root / "ROADMAP.md"
    if not rm.exists():
        return []
    lines = rm.read_text(encoding="utf-8").splitlines()
    warnings = []
    in_auto = False
    freeform = chars = 0
    for line in lines:
        if AUTO_START in line:
            in_auto = True
        elif AUTO_END in line:
            in_auto = False
        elif not in_auto and line.strip():
            freeform += 1
            chars += len(line)
    if freeform > MAX_FREEFORM_LINES or chars > MAX_FREEFORM_CHARS:
        size = (f"{freeform} lines (> {MAX_FREEFORM_LINES})"
                if freeform > MAX_FREEFORM_LINES
                else f"{chars} characters (> {MAX_FREEFORM_CHARS})")
        warnings.append(
            f"ROADMAP.md free-form region is {size}. Move long-form notes into linked "
            "files via `roadmap.py idea --title ... --body-file ...` and keep one "
            "bullet per idea.")
    if len(lines) > MAX_ROADMAP_LINES:
        warnings.append(
            f"ROADMAP.md is {len(lines)} lines (> {MAX_ROADMAP_LINES}). Shipped versions "
            "collapse automatically on sync (settings.collapseShipped); trim the "
            "free-form region into .roadmap/notes/ files.")
    return warnings


def status(root: Path) -> dict:
    cfg = read_config(root)
    by_id = {i["id"]: i for i in cfg["items"]}
    # Full progress map first — blockedBy for early ids must see later deps' progress.
    progress = _progress_map(root, cfg)
    items = []
    for item in cfg["items"]:
        done, total = progress.get(item["id"], (0, 0))
        pct = round(100 * done / total) if total else 0
        blocked_by = _incomplete_deps(item, progress, by_id)
        row = {**item, "done": done, "total": total, "pct": pct,
               "status": derive_status(done, total),
               "dependsOn": list(item.get("dependsOn") or []),
               "blockedBy": blocked_by}
        items.append(row)
    return {"project": cfg["project"], "currentVersion": cfg["currentVersion"],
            "items": items}


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
            skipped.append((item["id"], blocked))
            continue
        if skipped and not quiet:
            for sid, deps in skipped:
                print(f"skipping #{sid} (blocked by {deps})", file=sys.stderr)
        return item
    if skipped and not quiet:
        for sid, deps in skipped:
            print(f"skipping #{sid} (blocked by {deps})", file=sys.stderr)
        print(f"no unblocked unfinished items in v{ver}", file=sys.stderr)
        return None
    return None
