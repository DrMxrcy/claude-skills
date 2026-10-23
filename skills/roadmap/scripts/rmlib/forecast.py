"""roadmap forecast (plan 44) — when will each open version finish, at recent pace?

Pace = checklist steps ticked per day over the last `settings.forecastDays` (default
14). A tick's date is the `(YYYY-MM-DD)` stamp on the dated evidence line `check`
writes under the step (`  > evidence: ... (2026-10-23)[ · tokens: N]`). A checked
step with no dated evidence line falls back to git: the author date of the commit
that turned its box from `[ ]` to `[x]` (read from `git log -p` of the roadmap dir,
window-limited, cached on HEAD sha so a long-lived `serve` process re-runs it only
when history moves).

Per open version: remaining steps, pace, forecast date and a range (pace ±1
standard deviation of the daily tick counts). Open versions are assumed to finish
in version order, so a later version's forecast also burns the steps still left in
earlier open versions (`ahead`). Fewer than MIN_TICKS ticks in the window → "not
enough history"; zero remaining → "done", never a forecast.

Optional `settings.versionTargets` ({"0.21.0": "2026-11-15"}) grades the forecast:
on track = expected finish on/before the target; at risk = expected after it but the
fast end of the range still makes it; late = even the fast end misses (or the target
date has passed with work left).

Read-only and never raises on git trouble. Layer: rmcore + rmparse only."""
from __future__ import annotations
import datetime
import math
import re
import statistics
import subprocess
from pathlib import Path
from rmlib.core import _norm_version, _version_key, roadmap_dir
from rmlib.parse import STEP_RE, _is_fence

DEFAULT_DAYS = 14
MIN_TICKS = 5
NOT_ENOUGH = "not enough history"
TARGET_STATES = ("on track", "at risk", "late")

# The stamp check_step appends: "(YYYY-MM-DD)" then an optional " · tokens: N".
_EVIDENCE_RE = re.compile(r"^\s*>\s*evidence:")
_STAMP_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)(?:\s*·\s*tokens:\s*\d+)?\s*$")

# (path) -> ((mtime_ns, size), [(checked, date|None), ...]) — like parse_plan's cache.
_STEP_CACHE: dict = {}
# (root, head, since) -> {plan basename: [tick dates]} — the git fallback.
_GIT_CACHE: dict = {}


def _date(s) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except (TypeError, ValueError):
        return None


def step_dates(path: Path) -> list[tuple[bool, datetime.date | None]]:
    """Each checklist step as (checked, date of its latest dated evidence line or
    None). Steps are counted exactly as parse_plan counts them (fences skipped)."""
    try:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return []
    hit = _STEP_CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    steps: list[list] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        sm = STEP_RE.match(line)
        if sm:
            steps.append([sm.group(2).lower() == "x", None])
        elif steps and _EVIDENCE_RE.match(line):
            m = _STAMP_RE.search(line)
            d = _date(m.group(1)) if m else None
            if d:     # several lines under one step (check, undo, re-check): latest wins
                steps[-1][1] = max(d, steps[-1][1]) if steps[-1][1] else d
    out = [(c, d) for c, d in steps]
    _STEP_CACHE[str(path)] = (key, out)
    return out


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def git_tick_dates(root: Path, since: datetime.date) -> dict[str, list[datetime.date]]:
    """Plan basename -> one date per box ticked in a commit since `since` (net per
    commit and file: a `[ ]`->`[x]` flip counts, a reworded checked step does not).
    Cached on (root, HEAD sha, since). {} outside git or on any git trouble."""
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    if not head:
        return {}
    key = (str(root), head, since.isoformat())
    if key in _GIT_CACHE:
        return _GIT_CACHE[key]
    rel = roadmap_dir(root)
    try:
        rel = rel.relative_to(root)
    except ValueError:
        pass
    log = _git(root, "log", f"--since={since.isoformat()} 00:00:00", "--date=short",
               "--format=%x01%ad", "-p", "--unified=0", "--no-color", "--no-ext-diff",
               "--", str(rel)) or ""
    out: dict[str, list[datetime.date]] = {}
    for chunk in log.split("\x01")[1:]:
        lines = chunk.splitlines()
        day = _date(lines[0]) if lines else None
        if not day or day < since:
            continue
        net: dict[str, int] = {}
        cur, in_header = None, False
        for line in lines[1:]:
            if line.startswith("diff --git "):      # file header until the first hunk
                cur = line.rsplit("/", 1)[-1].strip('"')
                in_header = True
                continue
            if line.startswith("@@"):
                in_header = False
                continue
            if in_header or cur is None or not cur.endswith(".md"):
                continue
            if line[:1] in ("+", "-"):
                sm = STEP_RE.match(line[1:])
                if sm and sm.group(2).lower() == "x":
                    net[cur] = net.get(cur, 0) + (1 if line[0] == "+" else -1)
        for name, n in net.items():
            out.setdefault(name, []).extend([day] * max(0, n))
    if len(_GIT_CACHE) > 32:
        _GIT_CACHE.clear()
    _GIT_CACHE[key] = out
    return out


def collect_ticks(root: Path, cfg: dict, today: datetime.date, days: int
                  ) -> tuple[list[tuple[datetime.date, str]], datetime.date | None]:
    """(ticks, earliest) — ticks = [(date, version)] for every checked step dated
    within the window [today-days+1, today]; earliest = the oldest tick date known
    at all (evidence dates reach further back than the window-limited git log)."""
    since = today - datetime.timedelta(days=days - 1)
    ticks: list[tuple[datetime.date, str]] = []
    earliest = None
    undated: list[tuple[dict, int, list[datetime.date]]] = []
    for item in cfg["items"]:
        path = roadmap_dir(root) / item["file"]
        steps = step_dates(path)
        dated = [d for c, d in steps if c and d]
        n_undated = sum(1 for c, d in steps if c and not d)
        if dated:
            first = min(dated)
            earliest = first if earliest is None else min(earliest, first)
        ticks += [(d, item["version"]) for d in dated if since <= d <= today]
        if n_undated:
            undated.append((item, n_undated, dated))
    if undated:
        from_git = git_tick_dates(root, since)
        for item, n, dated in undated:
            pool = list(from_git.get(Path(item["file"]).name, []))
            for d in dated:          # a dated tick is already counted: drop its commit
                if d in pool:
                    pool.remove(d)
            for d in sorted(pool)[-n:]:
                if since <= d <= today:
                    ticks.append((d, item["version"]))
                    earliest = d if earliest is None else min(earliest, d)
    return ticks, earliest


def _settings(cfg: dict) -> tuple[int, dict[str, datetime.date]]:
    s = cfg.get("settings") or {}
    try:
        days = int(s.get("forecastDays", DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = days if days >= 1 else DEFAULT_DAYS
    raw = s.get("versionTargets")
    targets = {}
    if isinstance(raw, dict):
        for v, d in raw.items():
            dd = _date(d)
            if isinstance(v, str) and dd:
                targets[_norm_version(v)] = dd
    return days, targets


def target_status(target: datetime.date | None, today: datetime.date, remaining: int,
                  date: datetime.date | None, fast: datetime.date | None) -> str | None:
    """on track / at risk / late (see module doc); None without a target, for a
    done version, or when there is no forecast and the target has not passed."""
    if target is None or remaining <= 0:
        return None
    if target < today:
        return "late"
    if date is None:
        return None
    if date <= target:
        return "on track"
    return "at risk" if fast is not None and fast <= target else "late"


def forecast(root: Path, cfg: dict, progress: dict[int, tuple[int, int]],
             today: datetime.date | None = None) -> dict[str, dict]:
    """{version: forecast} for every open version, ascending. Open = a version with
    steps left, or a finished one not yet behind currentVersion (shown as done).
    Shipped versions below currentVersion are omitted."""
    today = today or datetime.date.today()
    days, targets = _settings(cfg)
    by_version: dict[str, list] = {}
    for item in cfg["items"]:
        by_version.setdefault(item["version"], []).append(item)
    cur_key = _version_key(_norm_version(cfg["currentVersion"]))
    remaining = {v: sum(max(0, progress.get(i["id"], (0, 0))[1]
                            - progress.get(i["id"], (0, 0))[0]) for i in its)
                 for v, its in by_version.items()}
    versions = sorted((v for v in by_version
                       if remaining[v] > 0 or _version_key(v) >= cur_key),
                      key=_version_key)
    if not versions:
        return {}
    ticks, earliest = collect_ticks(root, cfg, today, days)
    # The pace window is `days` long, or shorter when history itself is shorter
    # (20 ticks over a 10-day-old project is 2/day, not 20/14).
    span = days if earliest is None else max(1, min(days, (today - earliest).days + 1))
    start = today - datetime.timedelta(days=span - 1)
    daily = [0] * span
    by_ver_day: dict[str, list[int]] = {}
    for d, v in ticks:
        if d >= start:
            daily[(d - start).days] += 1
            by_ver_day.setdefault(v, [0] * span)[(d - start).days] += 1
    n_ticks = sum(daily)
    pace = n_ticks / span
    sd = statistics.pstdev(daily) if span > 1 else 0.0
    out: dict[str, dict] = {}
    ahead = 0
    for v in versions:
        left = remaining[v]
        per_day = by_ver_day.get(v, [0] * span)
        burn, acc = [], left
        for n in reversed(per_day):     # remaining at the end of each window day
            burn.append(acc)
            acc += n
        burn.append(acc)                # ... and at the window's start
        target = targets.get(v)
        f = {"version": v, "remaining": left, "ahead": ahead,
             "pace": round(pace, 2), "sd": round(sd, 2), "ticks": n_ticks,
             "windowDays": span, "state": "forecast", "message": None,
             "days": None, "date": None, "range": None,
             "target": target.isoformat() if target else None, "targetStatus": None,
             "burndown": list(reversed(burn))}
        if left <= 0:
            f["state"] = "done"
        elif n_ticks < MIN_TICKS or pace <= 0:
            f["state"], f["message"] = "insufficient", NOT_ENOUGH
            f["targetStatus"] = target_status(target, today, left, None, None)
        else:
            todo = left + ahead
            n_days = math.ceil(todo / pace)
            date = today + datetime.timedelta(days=n_days)
            fast = today + datetime.timedelta(days=math.ceil(todo / (pace + sd)))
            slow = (today + datetime.timedelta(days=math.ceil(todo / (pace - sd)))
                    if pace - sd > 0 else None)
            f.update(days=n_days, date=date.isoformat(),
                     range=[fast.isoformat(), slow.isoformat() if slow else None],
                     targetStatus=target_status(target, today, left, date, fast))
        out[v] = f
        ahead += max(0, left)
    return out


def summary(f: dict | None) -> str:
    """One-line text form for `status` version headers."""
    if not f:
        return ""
    if f["state"] == "done":
        return "done"
    left = f"{f['remaining']} step{'s' if f['remaining'] != 1 else ''} left"
    if f.get("ahead"):
        left += f" (+{f['ahead']} ahead)"
    if f["state"] == "insufficient":
        s = (f"{left} · {NOT_ENOUGH} ({f['ticks']} tick{'s' if f['ticks'] != 1 else ''}"
             f" in {f['windowDays']}d)")
    else:
        lo, hi = f["range"]
        s = (f"{left} · {f['pace']:g}/day · forecast {f['date']} "
             f"({lo}..{hi or '?'})")
    if f.get("target"):
        s += f" · target {f['target']}" + (f": {f['targetStatus']}"
                                             if f.get("targetStatus") else "")
    return s
