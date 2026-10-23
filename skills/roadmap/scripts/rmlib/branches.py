"""roadmap branch discovery — read in-flight work straight from git.

Branches named `roadmap/<id>` (settings.branchPattern) and commits tagged
`(plan N)` / `(bug N)` carry built work long before any trunk checkbox is
ticked. This module maps them to items without touching `.roadmap/`.
Layer: rmcore only (read-only, never writes, never raises on git trouble).

Git cost is bounded regardless of branch count: one `for-each-ref` call is the
cache key, and only when refs changed do we spend two more (ahead/behind for
every branch at once, one `log` across all unmerged tips), plus one when
settings.integrationBranch is set (which branch tips it contains — `landed`).
"""
from __future__ import annotations
import datetime
import re
import subprocess
import threading
from pathlib import Path
from rmlib.core import read_config

DEFAULT_PATTERN = "roadmap/{id}"
DEFAULT_STALE_DAYS = 7
MAX_COMMITS = 20  # per-branch commit list kept for the item detail view
TAG_RE = re.compile(r"\((?:plan|bug)\s+#?(\d+)\)", re.IGNORECASE)

# Field separator inside git --format output (subjects may contain tabs).
_SEP = "\x1f"
_REF_FIELDS = ["%(refname:short)", "%(objectname)", "%(objectname:short)",
               "%(committerdate:iso-strict)", "%(HEAD)", "%(worktreepath)",
               "%(subject)"]

# (root, requested trunk, integration branch) -> (for-each-ref stdout,
# git-derived branch data). Only git facts are cached; item mapping and
# staleness are recomputed per call so a changed item list or a passing day
# never needs another git call.
_CACHE: dict[tuple[str, str | None, str | None], tuple[str, dict]] = {}
_LOCK = threading.Lock()
_FROM_SETTINGS = object()   # discover(integration=...) default: read the config


def _empty(trunk: str | None = None) -> dict:
    return {"trunk": trunk, "items": {}, "other": []}


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _settings(root: Path) -> dict:
    try:
        return read_config(root).get("settings") or {}
    except (OSError, ValueError):
        return {}


def _pattern_re(pattern: str) -> re.Pattern | None:
    """`roadmap/{id}` -> matches `roadmap/7` and `roadmap/7-anything`."""
    if "{id}" not in pattern:
        return None
    body = re.escape(pattern).replace(re.escape("{id}"), r"(\d+)")
    return re.compile(rf"^{body}(?:-.+)?$")


def _list_refs(root: Path) -> tuple[str, list[dict]] | None:
    """One for-each-ref call -> (raw stdout as cache signature, parsed refs).
    Retries without %(worktreepath) for git older than 2.23."""
    fields = _REF_FIELDS
    raw = _git(root, "for-each-ref", "refs/heads",
               "--format=" + _SEP.join(fields))
    if raw is None:
        fields = [f for f in fields if f != "%(worktreepath)"]
        raw = _git(root, "for-each-ref", "refs/heads",
                   "--format=" + _SEP.join(fields))
        if raw is None:
            return None
    refs = []
    for line in raw.splitlines():
        parts = line.split(_SEP, len(fields) - 1)
        if len(parts) != len(fields):
            continue
        row = dict(zip(fields, parts))
        refs.append({"name": row["%(refname:short)"],
                     "sha": row["%(objectname)"],
                     "short": row["%(objectname:short)"],
                     "date": row["%(committerdate:iso-strict)"],
                     "head": row["%(HEAD)"] == "*",
                     "worktree": row.get("%(worktreepath)") or None,
                     "subject": row["%(subject)"]})
    return raw, refs


def _pick_trunk(refs: list[dict], trunk: str | None) -> str | None:
    """Explicit trunk if it exists locally, else main, master, then whatever
    branch the checkout is on. Read from the ref list, so it costs no call."""
    names = {r["name"] for r in refs}
    if trunk:
        return trunk if trunk in names else None
    for cand in ("main", "master"):
        if cand in names:
            return cand
    return next((r["name"] for r in refs if r["head"]), None)


def _ahead_behind(root: Path, trunk: str, refs: list[dict]) -> dict[str, tuple[int, int]]:
    """{branch: (ahead, behind)} vs trunk. One call on git >= 2.41
    (%(ahead-behind:)); otherwise one rev-list per branch."""
    out: dict[str, tuple[int, int]] = {}
    raw = _git(root, "for-each-ref", "refs/heads",
               f"--format=%(refname:short){_SEP}%(ahead-behind:refs/heads/{trunk})")
    if raw is not None:
        for line in raw.splitlines():
            name, _, ab = line.partition(_SEP)
            a, _, b = ab.partition(" ")
            if a.isdigit() and b.isdigit():
                out[name] = (int(a), int(b))
        return out
    for r in refs:
        counts = _git(root, "rev-list", "--left-right", "--count",
                      f"refs/heads/{trunk}...{r['sha']}")
        if counts:
            behind, _, ahead = counts.strip().partition("\t")
            if ahead.isdigit() and behind.isdigit():
                out[r["name"]] = (int(ahead), int(behind))
    return out


def _branch_commits(root: Path, trunk: str, tips: dict[str, str]) -> dict[str, list[dict]]:
    """{branch: [commit, ...]} for commits on each branch but not on trunk,
    newest first. One `git log` across every tip, then a parent walk per tip
    to attribute commits shared by several branches to each of them."""
    if not tips:
        return {}
    raw = _git(root, "log", f"--format=%H{_SEP}%h{_SEP}%P{_SEP}%cI{_SEP}%s",
               *sorted(set(tips.values())), "--not", f"refs/heads/{trunk}")
    if raw is None:
        return {}
    order: list[str] = []
    commits: dict[str, dict] = {}
    for line in raw.splitlines():
        parts = line.split(_SEP, 4)
        if len(parts) != 5:
            continue
        sha, short, parents, date, subject = parts
        order.append(sha)
        commits[sha] = {"sha": short, "date": date, "subject": subject,
                        "parents": parents.split(),
                        "tags": sorted({int(n) for n in TAG_RE.findall(subject)})}
    result: dict[str, list[dict]] = {}
    for name, tip in tips.items():
        seen: set[str] = set()
        stack = [tip]
        while stack:
            sha = stack.pop()
            if sha in seen or sha not in commits:  # absent = already on trunk
                continue
            seen.add(sha)
            stack.extend(commits[sha]["parents"])
        result[name] = [commits[s] for s in order if s in seen]
    return result


def _contained_in(root: Path, target: str) -> set[str]:
    """Names of every local branch whose tip `target` already contains — one
    for-each-ref call for all branches at once. Empty on any git trouble."""
    raw = _git(root, "for-each-ref", "refs/heads", f"--merged={target}",
               "--format=%(refname:short)")
    return set(raw.split()) if raw else set()


def _scan(root: Path, trunk: str, refs: list[dict],
          integration: str | None = None) -> dict:
    """The git-derived (cacheable) part: every non-trunk branch with its
    ahead/behind counts and its unmerged commits. With an `integration` branch,
    a branch not yet merged to trunk whose tip the integration branch contains
    is `landed` there (landedSha = the integration tip that contains it)."""
    counts = _ahead_behind(root, trunk, refs)
    tips = {r["name"]: r["sha"] for r in refs}
    landed_in = (_contained_in(root, f"refs/heads/{integration}")
                 if integration else set())
    branches = []
    for r in refs:
        if r["name"] == trunk:
            continue
        ahead, behind = counts.get(r["name"], (0, 0))
        merged = r["name"] in counts and ahead == 0
        landed = not merged and r["name"] in landed_in
        branches.append({**r, "ahead": ahead, "behind": behind,
                         "merged": merged, "landed": landed,
                         "landedIn": integration if landed else None,
                         "landedSha": tips[integration] if landed else None})
    tips = {b["name"]: b["sha"] for b in branches if not b["merged"]}
    per_branch = _branch_commits(root, trunk, tips)
    for b in branches:
        b["commits"] = per_branch.get(b["name"], [])
    return {"trunk": trunk, "integration": integration, "branches": branches}


_EPOCH = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _when(date: str) -> datetime.datetime:
    """Parse a git ISO date; unparsable sorts oldest (and never reads stale)."""
    try:
        when = datetime.datetime.fromisoformat(date)
    except ValueError:
        return _EPOCH
    return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)


def _is_stale(date: str, stale_days: int, now: datetime.datetime) -> bool:
    when = _when(date)
    return when != _EPOCH and now - when > datetime.timedelta(days=stale_days)


def _info(b: dict, item: int | None, stale_days: int,
          now: datetime.datetime) -> dict:
    """Public per-branch record. taggedCommits counts commits tagged for
    `item` (0 for unattributed branches). `sha` is the full tip; `landed`
    (plan 32) marks a branch the integration branch contains but trunk does not."""
    tagged = sum(1 for c in b["commits"] if item is not None and item in c["tags"])
    return {"name": b["name"], "item": item, "ahead": b["ahead"],
            "behind": b["behind"], "lastCommit": b["short"],
            "lastSubject": b["subject"], "lastDate": b["date"],
            "merged": b["merged"], "worktree": b["worktree"],
            "sha": b["sha"], "landed": b.get("landed", False),
            "landedIn": b.get("landedIn"), "landedSha": b.get("landedSha"),
            "taggedCommits": tagged,
            "stale": _is_stale(b["date"], stale_days, now),
            "commits": [{k: c[k] for k in ("sha", "date", "subject")}
                        for c in b["commits"][:MAX_COMMITS]]}


def discover(root: Path, item_ids=None, trunk: str | None = None,
             pattern: str | None = None, stale_days: int | None = None,
             integration=_FROM_SETTINGS) -> dict:
    """Map git branches and tagged commits to roadmap items.

    Returns {"trunk": name|None, "items": {id: branchinfo}, "other": [branchinfo]}.
    An item gets the branch named for it (settings.branchPattern, default
    `roadmap/{id}` or `roadmap/{id}-<suffix>`; unmerged and newest preferred),
    else the unmerged branch carrying the most `(plan N)`/`(bug N)` commits.
    `other` holds every unmerged non-trunk branch not chosen for an item.
    `item_ids` limits which ids may be attributed (None = any). Outside git,
    with no commits, or with no resolvable trunk, the result is empty.
    `integration` (default: settings.integrationBranch; None = off) names the
    branch work merges into before trunk; branches it contains read `landed`.
    It is ignored when it is the trunk or does not exist locally.
    """
    root = Path(root)
    settings = None
    if pattern is None or stale_days is None or integration is _FROM_SETTINGS:
        settings = _settings(root)
    if integration is _FROM_SETTINGS:
        integration = settings.get("integrationBranch")
    if pattern is None:
        pattern = settings.get("branchPattern")
        if not isinstance(pattern, str) or not pattern:
            pattern = DEFAULT_PATTERN
    if stale_days is None:
        try:
            stale_days = int(settings.get("staleDays", DEFAULT_STALE_DAYS))
        except (TypeError, ValueError):
            stale_days = DEFAULT_STALE_DAYS

    listed = _list_refs(root)
    if listed is None:
        return _empty()
    sig, refs = listed
    resolved = _pick_trunk(refs, trunk)
    if resolved is None:
        return _empty()
    names = {r["name"] for r in refs}
    if not isinstance(integration, str) or integration == resolved \
            or integration not in names:
        integration = None
    key = (str(root.resolve()), trunk, integration)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == sig:
        data = hit[1]
    else:
        data = _scan(root, resolved, refs, integration)
        with _LOCK:
            _CACHE[key] = (sig, data)

    allowed = None if item_ids is None else {int(i) for i in item_ids}
    name_re = _pattern_re(pattern)
    now = datetime.datetime.now(datetime.timezone.utc)

    # Candidate branches per item: by name first, then by tagged commits.
    named: dict[int, list[dict]] = {}
    tagged: dict[int, list[tuple[int, dict]]] = {}
    for b in data["branches"]:
        m = name_re.match(b["name"]) if name_re else None
        if m and (allowed is None or int(m.group(1)) in allowed):
            named.setdefault(int(m.group(1)), []).append(b)
        if b["merged"]:
            continue
        counts: dict[int, int] = {}
        for c in b["commits"]:
            for n in c["tags"]:
                counts[n] = counts.get(n, 0) + 1
        for n, k in counts.items():
            if allowed is None or n in allowed:
                tagged.setdefault(n, []).append((k, b))

    items: dict[int, dict] = {}
    chosen: set[str] = set()
    for n in sorted(set(named) | set(tagged)):
        # Unmerged work wins: an open named branch, then the open branch with
        # the most tagged commits, and only then a named branch already merged.
        live = [b for b in named.get(n, []) if not b["merged"]]
        if live:
            best = max(live, key=lambda b: _when(b["date"]))
        elif n in tagged:
            best = max(tagged[n], key=lambda kb: (kb[0], _when(kb[1]["date"])))[1]
        else:
            best = max(named[n], key=lambda b: _when(b["date"]))
        items[n] = _info(best, n, stale_days, now)
        chosen.add(best["name"])

    other = []
    for b in data["branches"]:
        if b["merged"] or b["name"] in chosen:
            continue
        m = name_re.match(b["name"]) if name_re else None
        item = int(m.group(1)) if m and (allowed is None
                                         or int(m.group(1)) in allowed) else None
        other.append(_info(b, item, stale_days, now))
    return {"trunk": resolved, "items": items, "other": other}
