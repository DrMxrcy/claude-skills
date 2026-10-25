"""roadmap branch discovery — read in-flight work straight from git.

Branches named `roadmap/<id>` (settings.branchPattern) and commits tagged
`(plan N)` / `(bug N)` carry built work long before any trunk checkbox is
ticked. This module maps them to items without touching `.roadmap/`.
Layer: rmcore only (read-only, never writes, never raises on git trouble).

Git cost is bounded regardless of branch count: one `for-each-ref` call is the
cache key, and only when refs changed do we spend two more (ahead/behind for
every branch at once, one `log` across all unmerged tips), plus one per
integration branch matched by settings.integrationBranch (which branch tips it
contains — `landed`).
"""
from __future__ import annotations
import datetime
import fnmatch
import re
import shlex
import subprocess
import threading
import time
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

# (root, requested trunk, matched integration branches) -> (for-each-ref
# stdout, git-derived branch data). Only git facts are cached; item mapping and
# staleness are recomputed per call so a changed item list or a passing day
# never needs another git call.
_CACHE: dict[tuple[str, str | None, tuple[str, ...]], tuple[str, dict]] = {}
_LOCK = threading.Lock()
_FROM_SETTINGS = object()   # discover(integration=...) default: read the config


def _empty(trunk: str | None = None) -> dict:
    return {"trunk": trunk, "items": {}, "other": []}


def _git(root: Path, *args: str, stdin: str | None = None) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], input=stdin,
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
        commits[sha] = {"sha": short, "full": sha, "date": date, "subject": subject,
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


def integration_patterns(value) -> tuple[str, ...]:
    """settings.integrationBranch as a tuple of fnmatch patterns: one branch
    name, or a list of names / globs (`["fix/trunk-*", "roadmap/v0.8.0"]`).
    Anything else (unset, empty, a non-string entry) contributes nothing."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict.fromkeys(v.strip() for v in value
                               if isinstance(v, str) and v.strip()))


def _match_integrations(patterns: tuple[str, ...], refs: list[dict],
                        trunk: str) -> tuple[str, ...]:
    """Expand integration patterns against the local branch names (trunk never
    matches). Case-sensitive, like git refs; sorted so the cache key is stable."""
    if not patterns:
        return ()
    return tuple(sorted(r["name"] for r in refs if r["name"] != trunk
                        and any(fnmatch.fnmatchcase(r["name"], p) for p in patterns)))


def _scan(root: Path, trunk: str, refs: list[dict],
          integrations: tuple[str, ...] = ()) -> dict:
    """The git-derived (cacheable) part: every non-trunk branch with its
    ahead/behind counts and its unmerged commits. A branch not yet merged to
    trunk whose tip any integration branch contains is `landed` there
    (landedIn = that branch, the newest-committed when several contain it;
    landedSha = its tip). One for-each-ref --merged call per integration branch."""
    counts = _ahead_behind(root, trunk, refs)
    by_name = {r["name"]: r for r in refs}
    newest_first = sorted(integrations, key=lambda n: _when(by_name[n]["date"]),
                          reverse=True)
    holds = {n: _contained_in(root, f"refs/heads/{n}") for n in newest_first}
    branches = []
    for r in refs:
        if r["name"] == trunk:
            continue
        ahead, behind = counts.get(r["name"], (0, 0))
        merged = r["name"] in counts and ahead == 0
        into = None if merged else next(
            (n for n in newest_first if r["name"] in holds[n]), None)
        branches.append({**r, "ahead": ahead, "behind": behind,
                         "merged": merged, "landed": into is not None,
                         "landedIn": into,
                         "landedSha": by_name[into]["sha"] if into else None})
    tips = {b["name"]: b["sha"] for b in branches if not b["merged"]}
    per_branch = _branch_commits(root, trunk, tips)
    for b in branches:
        b["commits"] = per_branch.get(b["name"], [])
    _mark_inherited(branches, tips, integrations)
    head = by_name.get(trunk, {})
    return {"trunk": trunk, "integrations": list(integrations),
            "trunkSha": head.get("sha"), "trunkDate": head.get("date"),
            "trunkSubject": head.get("subject"), "branches": branches}


def _mark_inherited(branches: list[dict], tips: dict[str, str],
                    integrations: tuple[str, ...] = ()) -> None:
    """Set b["inherited"]: full shas of commits a branch only carries because it
    was built on top of other work, so their `(plan N)` tags must not attribute
    item N to it (plan 32). A commit is inherited when it is reachable from
    another branch whose tip is an ancestor of this one (a base it was cut from,
    or a branch merged into it), or — for a branch no integration branch
    contains — from any integration branch (it was cut from integration, and
    that work belongs to the items already landed there). Every matched
    integration branch counts the same. Pure set work on the commit lists
    already fetched: no extra git call."""
    reach = {b["name"]: {c["full"] for c in b["commits"]} for b in branches
             if b["name"] in tips}
    integ: set[str] = set()
    for n in integrations:
        integ |= reach.get(n, set())
    for b in branches:
        own = reach.get(b["name"])
        if not own:
            b["inherited"] = frozenset()
            continue
        inherited: set[str] = set()
        for other, tip in tips.items():
            if other != b["name"] and tip != b["sha"] and tip in own:
                inherited |= reach[other]
        if integ and b["name"] not in integrations and not b.get("landed"):
            inherited |= own & integ
        b["inherited"] = frozenset(inherited & own)


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
    skip = b.get("inherited") or ()
    tagged = sum(1 for c in b["commits"] if item is not None and item in c["tags"]
                 and c["full"] not in skip)
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


def _scan_cached(root: Path, trunk: str | None,
                 integration) -> tuple[str, dict] | None:
    """(resolved trunk, git-derived branch data), cached on the ref list: one
    for-each-ref call when refs are unchanged. None outside git, with no
    commits, or with no resolvable trunk."""
    listed = _list_refs(root)
    if listed is None:
        return None
    sig, refs = listed
    resolved = _pick_trunk(refs, trunk)
    if resolved is None:
        return None
    integrations = _match_integrations(integration_patterns(integration),
                                       refs, resolved)
    key = (str(Path(root).resolve()), trunk, integrations)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == sig:
        return resolved, hit[1]
    data = _scan(root, resolved, refs, integrations)
    with _LOCK:
        _CACHE[key] = (sig, data)
    return resolved, data


def discover(root: Path, item_ids=None, trunk: str | None = None,
             pattern: str | None = None, stale_days: int | None = None,
             integration=_FROM_SETTINGS) -> dict:
    """Map git branches and tagged commits to roadmap items.

    Returns {"trunk": name|None, "items": {id: branchinfo}, "other": [branchinfo]}
    (plus "trunkSha", the trunk tip, when a trunk resolved).
    An item gets the branch named for it (settings.branchPattern, default
    `roadmap/{id}` or `roadmap/{id}-<suffix>`; unmerged and newest preferred),
    else the unmerged branch carrying the most `(plan N)`/`(bug N)` commits.
    `other` holds every unmerged non-trunk branch not chosen for an item.
    `item_ids` limits which ids may be attributed (None = any). Outside git,
    with no commits, or with no resolvable trunk, the result is empty.
    `integration` (default: settings.integrationBranch; None = off) names the
    branch work merges into before trunk — one name, or a list of names and
    fnmatch globs expanded against local branches; branches any of them
    contains read `landed`. The trunk and patterns matching no local branch
    are ignored.
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

    scanned = _scan_cached(root, trunk, integration)
    if scanned is None:
        return _empty()
    resolved, data = scanned

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
        skip = b.get("inherited") or ()
        for c in b["commits"]:
            if c["full"] in skip:       # carried from a base branch, not its work
                continue
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
    return {"trunk": resolved, "trunkSha": data.get("trunkSha"),  # plan 41
            "items": items, "other": other}


# --- containment checks for landed claims (plan 32) -----------------------

def resolve_commits(root: Path, revs) -> dict[str, str | None]:
    """{rev: full commit sha, or None when it names no commit}. One
    `cat-file --batch-check` call for every rev (branch names, short or full
    shas, tags). A rev containing whitespace never resolves."""
    revs = list(dict.fromkeys(str(r) for r in revs))
    out: dict[str, str | None] = {r: None for r in revs}
    ask = [r for r in revs if r and not any(c.isspace() for c in r)]
    if not ask:
        return out
    raw = _git(Path(root), "cat-file", "--batch-check=%(objectname) %(objecttype)",
               stdin="".join(f"{r}^{{commit}}\n" for r in ask))
    if raw is None:
        return out
    lines = raw.splitlines()
    if len(lines) != len(ask):
        return out
    for rev, line in zip(ask, lines):
        sha, _, kind = line.partition(" ")
        if kind == "commit" and re.fullmatch(r"[0-9a-f]{40,64}", sha):
            out[rev] = sha
    return out


def contained(root: Path, target: str, shas) -> set[str] | None:
    """The subset of full commit `shas` that `target` contains (each is target
    itself or one of its ancestors). One `rev-list` call: a sha is outside
    target exactly when it is listed among the commits target lacks. None on
    any git trouble — callers must treat that as "not proven contained"."""
    shas = sorted({s for s in shas if s})
    if not shas:
        return set()
    raw = _git(Path(root), "rev-list", *shas, "--not", target)
    if raw is None:
        return None
    outside = set(raw.split())
    return {s for s in shas if s not in outside}


# --- worktree map (plan 36) ------------------------------------------------
#
# `git worktree list` is one call for the whole repo; the dirty count is one
# `git status --porcelain` per worktree. Both are cached with a time budget
# (DIRTY_MAX_AGE), so a 1 s dashboard tick runs no per-worktree git call more
# often than every 10 s. Commit facts of detached heads are immutable and
# cached by sha. Nothing here ever removes a worktree or a branch: the removal
# command for a safe worktree is only returned as text.

DIRTY_MAX_AGE = 10.0
_now = time.monotonic                      # monkeypatched by tests
_WT_LIST: dict[str, tuple[float, list[dict] | None]] = {}
_DIRTY: dict[str, tuple[float, int | None]] = {}
_HEADS: dict[str, dict] = {}               # sha -> {date, subject}
_UNMERGED: dict[tuple[str, str], int] = {}  # (trunk sha, head sha) -> count


def _parse_worktrees(raw: str) -> list[dict]:
    """`git worktree list --porcelain` -> one dict per entry, main first."""
    out: list[dict] = []
    cur: dict | None = None
    for line in raw.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):], "head": None,
                   "branch": None, "detached": False, "bare": False,
                   "locked": False, "prunable": False}
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].strip().removeprefix("refs/heads/")
        elif line == "detached":
            cur["detached"] = True
        elif line == "bare":
            cur["bare"] = True
        elif line.split(" ", 1)[0] == "locked":
            cur["locked"] = True
        elif line.split(" ", 1)[0] == "prunable":
            cur["prunable"] = True
        elif not line.strip():
            out.append(cur)
            cur = None
    for i, w in enumerate(out):
        w["main"] = i == 0
    return out


def _fresh(entry, max_age: float) -> bool:
    return entry is not None and _now() - entry[0] < max_age


def list_worktrees(root: Path, max_age: float = DIRTY_MAX_AGE) -> list[dict] | None:
    """Every worktree of the repo (main first), re-listed at most every
    `max_age` seconds. None outside git or on any git trouble."""
    key = str(Path(root).resolve())
    with _LOCK:
        hit = _WT_LIST.get(key)
    if _fresh(hit, max_age):
        return hit[1]
    raw = _git(Path(root), "worktree", "list", "--porcelain")
    rows = _parse_worktrees(raw) if raw is not None else None
    with _LOCK:
        _WT_LIST[key] = (_now(), rows)
    return rows


def dirty_count(path: str, max_age: float = DIRTY_MAX_AGE) -> int | None:
    """Changed + untracked paths in one worktree (`git status --porcelain`
    lines), refreshed at most every `max_age` seconds. --no-optional-locks so
    polling never takes the worktree's index lock. None when the worktree is
    missing or git fails."""
    with _LOCK:
        hit = _DIRTY.get(path)
    if _fresh(hit, max_age):
        return hit[1]
    raw = (_git(Path(path), "--no-optional-locks", "status", "--porcelain")
           if Path(path).is_dir() else None)
    n = None if raw is None else sum(1 for l in raw.splitlines() if l.strip())
    with _LOCK:
        _DIRTY[path] = (_now(), n)
    return n


def worktree_facts(root: Path, max_age: float = DIRTY_MAX_AGE) -> list[dict] | None:
    """Linked (non-main, non-bare) worktrees with their dirty counts — the
    time-budgeted part only, no ref scan. Cheap enough for a 1 s tick: zero git
    calls while the budget holds, then one list + one status per worktree."""
    rows = list_worktrees(root, max_age)
    if rows is None:
        return None
    return [{**w, "dirty": None if w["prunable"] else dirty_count(w["path"], max_age)}
            for w in rows if not w["main"] and not w["bare"]]


def _head_facts(root: Path, shas) -> dict[str, dict]:
    """{sha: {date, subject}} for commit shas, one `git show -s` call for
    every sha not yet cached (commits never change)."""
    want = sorted({s for s in shas if s and s not in _HEADS})
    if want:
        raw = _git(root, "show", "-s", f"--format=%H{_SEP}%cI{_SEP}%s", *want)
        for line in (raw or "").splitlines():
            parts = line.split(_SEP, 2)
            if len(parts) == 3:
                _HEADS[parts[0]] = {"date": parts[1], "subject": parts[2]}
    return {s: _HEADS[s] for s in shas if s in _HEADS}


def _unmerged_heads(root: Path, trunk: str, trunk_sha: str,
                    heads: dict[str, str]) -> dict[str, int]:
    """{key: commits on that head sha but not on trunk} for detached heads,
    one `git log` across every uncached head (cached on (trunk, head) sha)."""
    want = {k: sha for k, sha in heads.items()
            if (trunk_sha, sha) not in _UNMERGED}
    if want:
        per = _branch_commits(root, trunk, want)
        if per:                     # {} only on git trouble: leave uncached
            for k, sha in want.items():
                _UNMERGED[(trunk_sha, sha)] = len(per.get(k, []))
    return {k: _UNMERGED[(trunk_sha, sha)] for k, sha in heads.items()
            if (trunk_sha, sha) in _UNMERGED}


def worktrees(root: Path, trunk: str | None = None, integration=_FROM_SETTINGS,
              max_age: float = DIRTY_MAX_AGE) -> dict:
    """Linked worktrees as rows: path, branch, head, dirty count, unmerged
    commits vs trunk (`ahead`), merged / landed, last commit date + subject,
    and `safe` — clean, not locked, not the trunk, and its branch fully merged
    into trunk (or no branch: a detached head trunk already contains). `reason`
    says why a row is not safe; `removeCmd` is the command for a safe one
    (printed, never run). Returns {"trunk": name|None, "rows": [...]}; rows
    are empty outside git. Item mapping and lanes are the caller's (sync)."""
    root = Path(root)
    if integration is _FROM_SETTINGS:
        integration = _settings(root).get("integrationBranch")
    facts = worktree_facts(root, max_age)
    if not facts:
        return {"trunk": None, "rows": []}
    scanned = _scan_cached(root, trunk, integration)
    resolved, data = scanned if scanned else (None, {"branches": []})
    by_name = {b["name"]: b for b in data["branches"]}
    trunk_sha = data.get("trunkSha")
    loose = {w["path"]: w["head"] for w in facts
             if w["head"] and w["branch"] not in by_name
             and w["branch"] != resolved}
    unmerged = (_unmerged_heads(root, resolved, trunk_sha, loose)
                if resolved and trunk_sha and loose else {})
    heads = _head_facts(root, loose.values()) if loose else {}
    rows = []
    for w in facts:
        b = by_name.get(w["branch"] or "")
        on_trunk = bool(resolved) and w["branch"] == resolved
        if b is not None:
            # Unmerged with nothing ahead only happens when ahead/behind could
            # not be read: unknown, so never safe.
            ahead = b["ahead"] if b["merged"] or b["ahead"] else None
            behind, merged = b["behind"], b["merged"]
            date, subject = b["date"], b["subject"]
            landed_in = b.get("landedIn")
        else:
            ahead = 0 if on_trunk else unmerged.get(w["path"])
            behind, landed_in = None, None
            merged = on_trunk or ahead == 0
            h = heads.get(w["head"] or "", {})
            date, subject = h.get("date"), h.get("subject")
            if on_trunk:
                date, subject = data.get("trunkDate"), data.get("trunkSubject")
        reasons = []
        if w["prunable"]:
            reasons.append("missing (git worktree prune)")
        if w["locked"]:
            reasons.append("locked")
        if on_trunk:
            reasons.append("trunk checkout")
        if w["dirty"] is None and not w["prunable"]:
            reasons.append("dirty count unknown")
        elif w["dirty"]:
            reasons.append(f"{w['dirty']} dirty")
        if ahead is None:
            reasons.append("unmerged count unknown")
        elif ahead:
            reasons.append(f"{ahead} unmerged")
        if resolved is None:
            reasons.append("no trunk")
        safe = not reasons
        rows.append({"path": w["path"], "branch": w["branch"],
                     "head": (w["head"] or "")[:7] or None,
                     "detached": w["detached"] or w["branch"] is None,
                     "locked": w["locked"], "prunable": w["prunable"],
                     "dirty": w["dirty"], "ahead": ahead, "behind": behind,
                     "merged": bool(merged), "landedIn": landed_in,
                     "lastDate": date, "lastSubject": subject,
                     "safe": safe, "reason": "; ".join(reasons) or None,
                     "removeCmd": (f"git worktree remove {shlex.quote(w['path'])}"
                                   if safe else None)})
    return {"trunk": resolved, "rows": rows}
