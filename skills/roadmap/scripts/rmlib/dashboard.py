"""Local live progress dashboard for the roadmap CLI.

Kept out of roadmap.py so that module stays focused on the CLI/data layer. This
one owns the HTTP server, SSE stream, and JSON endpoints. It never imports
roadmap at module load — the roadmap module is passed in as `rm`, which both
avoids an import cycle and keeps the data layer the single source of truth.
"""
from __future__ import annotations
import hashlib
import http.server
import json
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_PORT = 4700
PORT_SPAN = 40
MAX_COMMITS = 20   # branch commits shown on an item page
MAX_DOC_BYTES = 2 * 1024 * 1024   # /api/note refuses anything bigger
DOC_DIRS = ("notes", "plans")     # the only .roadmap/ subdirs /api/note reads
FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.S)
# Root-relative note/plan references inside markdown: `.roadmap/notes/x.md`,
# `notes/x.md`, `(plans/007-x.md)` — candidates only; _doc_path validates.
DOC_REF_RE = re.compile(r"(?<![\w./-])((?:\.roadmap/)?(?:notes|plans)/[\w.-]+\.md)\b")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+\.md)\)")


def _dashboard_html() -> str:
    return (Path(__file__).resolve().parent / "dashboard.html").read_text(
        encoding="utf-8")


def _status_line(st: dict) -> str:
    items = st.get("items", [])
    td = sum(i.get("done", 0) for i in items)
    tt = sum(i.get("total", 0) for i in items)
    pct = round(100 * td / tt) if tt else 0
    active = sum(1 for i in items if i.get("status") == "active")
    ver = st.get("currentVersion") or "?"
    nvers = len({i.get("version") for i in items})
    flying = (st.get("counts") or {}).get("lanes", {}).get("inFlight", 0)
    return (f"current v{ver} · {pct}% ({td}/{tt}) · {active} active"
            + (f" · {flying} in flight" if flying else "")
            + f" · {nvers} version{'s' if nvers != 1 else ''}")


def _checkout_label(m: dict) -> str:
    return m.get("branch") or m.get("name") or "?"


def _summary_lines(data: dict, url: str | None, verbose: bool = False,
                   prefix: str = "") -> list[str]:
    """Terminal lines for one payload: ONE summary line (the trunk view, the
    checkout count and the URL, so the dashboard is findable from any line in
    the scrollback), plus one line per checkout only when `verbose`.
    A repo with 27 worktrees refreshes as one line, not 27."""
    roots, stats = data.get("_roots") or [], data.get("statuses") or []
    if not stats:
        return []
    ti = data.get("trunkRoot", 0)
    ti = ti if isinstance(ti, int) and 0 <= ti < len(stats) else 0
    n = len(stats)
    label = (f"[{(roots[ti].get('branch') if ti < len(roots) else None) or 'trunk'}] "
             if n > 1 else "")
    line = (f"{prefix}{label}{_status_line(stats[ti])}"
            + (f" · {n} checkouts" if n > 1 else "")
            + (f"  → {url}" if url else ""))
    out = [line]
    if verbose and n > 1:
        for m, st in zip(roots, stats):
            out.append(f"      [{_checkout_label(m)}] {_status_line(st)}")
    return out


def _roadmap_signature(rm, root: Path):
    """Cheap change token: newest mtime across .roadmap/ and ROADMAP.md."""
    latest = 0.0
    try:
        for f in rm.roadmap_dir(root).rglob("*"):
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass
        md = root / "ROADMAP.md"
        if md.exists():
            latest = max(latest, md.stat().st_mtime)
    except OSError:
        pass
    return latest


def _refs_signature(root: Path) -> str | None:
    """Change token for branch work, which never touches .roadmap/: one cheap
    `for-each-ref` per tick (names + tip shas). None outside git or on any git
    failure, so a repo without git simply never triggers on refs."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "for-each-ref", "refs/heads",
             "--format=%(refname) %(objectname)"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _worktree_signature(rm, root: Path):
    """Change token for the worktree map (plan 36): each linked worktree's
    branch, head and dirty count. The facts are cached on a 10 s budget, so a
    1 s tick runs no per-worktree git call more often than that. None when
    the API has no worktree hook or git fails."""
    facts_fn = getattr(rm, "worktree_facts", None)
    if facts_fn is None:
        return None
    try:
        facts = facts_fn(root)
    except Exception:  # noqa: BLE001 — the tick must survive any git surprise
        return None
    return [(w["path"], w["branch"], w["head"], w["dirty"], w["locked"],
             w["prunable"]) for w in facts or []]


def _safe_worktrees(rm, root: Path, st: dict) -> dict | None:
    """The worktree map for the trunk view's status `st`; None without the
    hook or on any failure (the panel simply does not render)."""
    fn = getattr(rm, "worktree_payload", None)
    if fn is None:
        return None
    try:
        return fn(root, st)
    except Exception:  # noqa: BLE001
        return None


def _safe_conflicts(rm, root: Path, st: dict) -> dict | None:
    """Branch conflict risk (plan 41) for the trunk view's status `st`; None
    without the hook or on any failure (the panel simply does not render)."""
    fn = getattr(rm, "conflicts_payload", None)
    if fn is None:
        return None
    try:
        return fn(root, st)
    except Exception:  # noqa: BLE001
        return None


def _safe_drift(rm, root: Path, st: dict) -> dict | None:
    """Scope drift (plan 42) for the trunk view's status `st`: off-plan files
    per open item branch. None without the hook or on any failure (cards and
    plan pages simply show no off-plan marks). Reuses the conflict item's
    cached per-branch diffs, so an unchanged-refs rebuild runs no git diff."""
    fn = getattr(rm, "scope_drift_payload", None)
    if fn is None:
        return None
    try:
        return fn(root, st)
    except Exception:  # noqa: BLE001
        return None

def _safe_attention(rm, root: Path, st: dict, conflicts: dict | None) -> list:
    """Needs-attention entries (plan 50) for the trunk view — the digest's
    ATTENTION checks, so the tab title counts exactly what `roadmap digest`
    lists. Empty without the hook or on any failure."""
    fn = getattr(rm, "attention", None)
    if fn is None or st.get("error"):
        return []
    try:
        return list(fn(root, {**st, "conflicts": conflicts} if conflicts else st))
    except Exception:  # noqa: BLE001 — the title count must never break a payload
        return []


def _pending_status() -> dict:
    """Placeholder for a checkout whose status is still being scanned (plan
    50's fast first paint): shaped like an empty status so every consumer
    (merge, summary lines, the page) handles it unchanged."""
    return {"project": None, "currentVersion": None, "items": [],
            "scanning": True}


def _safe_status(rm, root: Path) -> dict:
    try:
        return rm.status(root)
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"project": None, "currentVersion": None, "items": [],
                "error": str(e)}


def _doc_path(rm, root: Path, rel: str):
    """Resolve a root-relative markdown path for /api/note. Returns (code,
    Path|message): 200 with the file, 400 when the path is not allowed (empty,
    absolute, `..`/`.` parts, backslashes, not `.md`, not directly inside
    .roadmap/notes/ or .roadmap/plans/, or a symlink that resolves outside that
    directory), 404 when it is allowed but missing. Read-only, never creates."""
    if (not isinstance(rel, str) or not rel or "\0" in rel or "\\" in rel
            or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel)):
        return 400, "path not allowed"
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return 400, "path not allowed"
    if not parts[-1].lower().endswith(".md") or len(parts[-1]) <= 3:
        return 400, "only .md files"
    rd = rm.roadmap_dir(root)
    try:
        rd_rel = rd.relative_to(root).parts
    except ValueError:
        return 400, "path not allowed"
    if (len(parts) != len(rd_rel) + 2 or tuple(parts[:len(rd_rel)]) != rd_rel
            or parts[len(rd_rel)] not in DOC_DIRS):
        return 400, "only .roadmap/notes/*.md and .roadmap/plans/*.md"
    allowed = rd / parts[len(rd_rel)]
    try:
        root_real = root.resolve(strict=True)
        allowed_real = allowed.resolve(strict=True)
        if not allowed_real.is_relative_to(root_real):
            return 400, "path not allowed"
        real = (allowed / parts[-1]).resolve(strict=True)
    except (OSError, RuntimeError):
        return 404, "not found"
    if real.parent != allowed_real:
        return 400, "path not allowed"   # symlink escaping the directory
    if not real.is_file():
        return 404, "not found"
    return 200, real


def _read_doc(rm, root: Path, rel: str) -> tuple[int, dict]:
    code, res = _doc_path(rm, root, rel)
    if code != 200:
        return code, {"error": res, "path": rel}
    try:
        if res.stat().st_size > MAX_DOC_BYTES:
            return 400, {"error": "file too large", "path": rel}
        body = res.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 404, {"error": "not found", "path": rel}
    return 200, {"path": rel, "body": body}


def _norm_ref(rm, root: Path, ref: str, base: Path | None = None) -> str | None:
    """A markdown reference as a root-relative posix path IF it names an
    existing note/plan /api/note would serve, else None. Relative refs are
    tried against `base` (the referring file's directory), the .roadmap/ dir
    and the root, in that order."""
    ref = ref.strip().split("#", 1)[0]
    if not ref or "://" in ref:
        return None
    rd = rm.roadmap_dir(root)
    for b in [x for x in (base, rd, root) if x is not None]:
        try:
            cand = Path(b, ref).resolve()   # lexical + symlink normalisation
            rel = cand.relative_to(root.resolve()).as_posix()
        except (ValueError, OSError, RuntimeError):
            continue
        if _doc_path(rm, root, rel)[0] == 200:
            return rel
    return None


def _linked_docs(rm, root: Path, text: str, base: Path | None = None,
                 exclude: str | None = None) -> list[str]:
    """Root-relative paths of the existing notes/plans a markdown text links
    to or mentions, in order of first appearance, de-duplicated."""
    out: list[str] = []
    refs = [m.group(1) for m in MD_LINK_RE.finditer(text)]
    refs += [m.group(1) for m in DOC_REF_RE.finditer(text)]
    for ref in refs:
        rel = _norm_ref(rm, root, ref, base)
        if rel and rel != exclude and rel not in out:
            out.append(rel)
    return out


def _acceptance(bullets: list[dict]) -> dict:
    """{met, failed, total, bullets} — the status row's counts (criteria only;
    `Fails if` guards are never marked) plus every bullet for the plan page."""
    crit = [b for b in bullets if b.get("kind") == "criterion"]
    return {"met": sum(b.get("state") == "met" for b in crit),
            "failed": sum(b.get("state") == "failed" for b in crit),
            "total": len(crit), "bullets": list(bullets)}


def _item_detail(rm, root: Path, item_id: int) -> dict:
    """Full detail for one item: its plan checklist steps + note. Fetched lazily
    by the dashboard when a row is expanded, so status payloads stay small."""
    try:
        cfg = rm.read_config(root)
        item = next((i for i in cfg["items"] if i["id"] == item_id), None)
        if item is None:
            return {"error": f"no item #{item_id}"}
        rd = rm.roadmap_dir(root)
        pp = rd / item["file"]
        plan = rm.parse_plan(pp) if pp.exists() else {"steps": [], "meta": {}}
        try:
            text = pp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        plan_rel = None
        try:
            plan_rel = pp.relative_to(root).as_posix()
        except ValueError:
            pass
        # Notes the plan links to or mentions, plus its handoff note if any.
        notes = _linked_docs(rm, root, text, base=pp.parent, exclude=plan_rel)
        handoff = _norm_ref(rm, root, f"notes/{item_id}-handoff.md")
        if handoff and handoff not in notes:
            notes.append(handoff)
        detail = {"id": item_id, "title": item["title"], "type": item["type"],
                  "version": item["version"], "note": item.get("note"),
                  "file": item["file"], "planPath": plan_rel,
                  "status": item.get("status"),
                  # raw markdown, frontmatter stripped — the page renders it
                  # as text nodes only (never HTML)
                  "body": FRONTMATTER_RE.sub("", text, count=1),
                  "meta": plan.get("meta") or {},
                  "notes": notes,
                  "dependsOn": list(item.get("dependsOn") or []),
                  "blockedBy": [],
                  "steps": [{"done": d, "text": t,
                             **({"waiting": plan["waiting"][n]}
                                if n in (plan.get("waiting") or {}) else {})}
                            for n, (d, t) in enumerate(plan["steps"], 1)],
                  # follow-up links (plan 46), both directions
                  "followUpOf": item.get("followUpOf"),
                  "followUps": list(item.get("followUps") or []),
                  "waitingSteps": [],
                  "lane": None, "claim": None, "branch": None,
                  "rulings": list(plan.get("rulings") or []),
                  "needsApproval": False,
                  # Acceptance ledger (plan 43): counts plus each bullet's state
                  # and evidence (the status row carries the counts only).
                  "acceptance": _acceptance(plan.get("acceptance") or [])}
        # Lane/claim/branch come from status() so the expanded row agrees with
        # the list (claim branch override included); commits are added here
        # only, keeping the streamed status payload small.
        row = next((i for i in rm.status(root).get("items", [])
                    if i.get("id") == item_id), None)
        if row is not None:
            detail["lane"], detail["claim"] = row.get("lane"), row.get("claim")
            detail["blockedBy"] = list(row.get("blockedBy") or [])
            detail["needsApproval"] = bool(row.get("needsApproval"))
            detail["waitingSteps"] = list(row.get("waitingSteps") or [])
            for k in ("displayId", "pct", "done", "total",
                      "foundIn", "bugsFound", "foundDuringBuild"):   # plan 47
                detail[k] = row.get(k)
            # plan 49: who `claim` would default to, so the page's copy
            # buttons add --take only when someone else holds the item.
            owner_fn = getattr(rm, "default_owner", None)
            try:
                detail["me"] = owner_fn(root) if owner_fn else None
            except Exception:  # noqa: BLE001 — a git hiccup must not break the page
                detail["me"] = None
            if row.get("branch"):
                detail["branch"] = {
                    **row["branch"],
                    "commits": _branch_commits(
                        rm, root, row["branch"]["name"],
                        [i["id"] for i in cfg["items"]])}
        return detail
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"error": str(e)}


def _branch_commits(rm, root: Path, name: str, item_ids: list) -> list[dict]:
    """Newest-first commits on branch `name` that trunk lacks (max 20), as
    {sha, date, subject}. Empty when discovery is unavailable or fails — the
    detail view degrades to steps only, never to an error."""
    discover = getattr(rm, "discover_branches", None)
    if discover is None:
        return []
    try:
        found = discover(root, item_ids)
    except Exception:  # noqa: BLE001 — detail view must survive git surprises
        return []
    for info in [*found.get("items", {}).values(), *found.get("other", [])]:
        if info.get("name") == name:
            return [{k: c.get(k) for k in ("sha", "date", "subject")}
                    for c in (info.get("commits") or [])[:MAX_COMMITS]]
    return []


def _ideas(rm, root: Path) -> dict:
    """Idea Incubator bullets for one checkout, wherever the incubator lives
    (ROADMAP.md or settings.incubatorFile — the CLI resolves it)."""
    try:
        f = rm.incubator_file(root)
        bullets = []
        for i, b in enumerate(rm.list_incubator_bullets(root), 1):
            if b["body"] == "(add ideas here)":
                continue   # the init placeholder bullet is chrome, not an idea
            # `index` is the 1-based position `roadmap promote --index` takes;
            # `note` the linked .roadmap/notes file, when it exists.
            links = _linked_docs(rm, root, b["body"], base=f.parent)
            bullets.append({**b, "index": i,
                            "note": links[0] if links else None})
        return {"file": str(f.relative_to(root)) if f.is_relative_to(root)
                else str(f), "bullets": bullets}
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"error": str(e), "bullets": []}


DIGEST_SINCE = ("3h", "1d", "3d", "1w", "2w", "last")   # the page's selector


def _digest(rm, root: Path, since: str) -> dict:
    """Digest page data (plan 45): the CLI digest for one checkout plus its
    display rows. Read-only — `last` reads this user's stamp but never moves
    it. Conflicts are included: the broadcaster already computed them, so
    their sha-keyed cache is warm."""
    since = since if since in DIGEST_SINCE else "1d"
    try:
        d = rm.digest(root, since, conflicts=True, owner=rm.default_owner(root))
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"error": str(e), "since": since, "options": list(DIGEST_SINCE)}
    return {**d, "sections": rm.digest_sections(d), "sinceArg": since,
            "options": list(DIGEST_SINCE)}


# ---- full-text search (plan 49) ---------------------------------------------
SEARCH_MAX_Q = 200      # longer queries are refused
SEARCH_MAX_HITS = 300   # hits returned; `truncated` says when more matched
SNIPPET_CTX = 70        # characters kept either side of the match


def _snippet(text: str, needle: str) -> tuple[str, list[int] | None]:
    """A window of `text` around the first case-insensitive match of `needle`,
    with ellipses where it was cut, plus the match's [start, end] inside the
    returned snippet (None when the needle does not occur, e.g. whitespace
    collapsed away). The page highlights it with text nodes only."""
    at = text.lower().find(needle.lower())
    if at < 0:
        return (text if len(text) <= 2 * SNIPPET_CTX else text[:2 * SNIPPET_CTX] + "…",
                None)
    lo, hi = max(0, at - SNIPPET_CTX), min(len(text), at + len(needle) + SNIPPET_CTX)
    pre, post = ("…" if lo else ""), ("…" if hi < len(text) else "")
    start = len(pre) + at - lo
    return pre + text[lo:hi] + post, [start, start + len(needle)]


def _search(rm, root: Path, q: str) -> dict:
    """Dashboard full-text search: the CLI `search` (item titles/notes, plan
    bodies, incubator bullets) plus `.roadmap/notes/*.md`, each hit resolved to
    the dashboard page it opens — `id` (plan page), `idea` (incubator index as
    /api/ideas numbers it) or `path` (note page) — with a snippet around the
    match. Files are only reported when /api/note would serve them (no symlink
    escapes). Read-only."""
    q = (q or "").strip()
    if not q:
        return {"q": q, "hits": [], "error": "empty query"}
    if len(q) > SEARCH_MAX_Q:
        return {"q": q[:SEARCH_MAX_Q], "hits": [], "error": "query too long"}
    fn = getattr(rm, "search", None)
    if fn is None:
        return {"q": q, "hits": [], "error": "search unavailable"}
    try:
        cfg = rm.read_config(root)
        raw = fn(root, q, notes=True)
        idea_of = {b["lineNo"]: i
                   for i, b in enumerate(rm.list_incubator_bullets(root), 1)}
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"q": q, "hits": [], "error": str(e)}
    items = {i["id"]: i for i in cfg.get("items", [])}
    by_file = {}
    for it in items.values():
        try:
            by_file[(rm.roadmap_dir(root) / it["file"]).relative_to(root).as_posix()] = it
        except (ValueError, KeyError):
            pass
    ok_files: dict[str, bool] = {}
    hits = []
    for h in raw:
        out = {"kind": h["kind"], "ref": h.get("ref"), "line": h.get("line")}
        if h["kind"] == "item":
            it = items.get(h.get("id"))
            out.update(id=h.get("id"), field=h.get("field"),
                       title=(it or {}).get("title"))
        elif h["kind"] in ("plan", "note"):
            f = h.get("file") or ""
            if f not in ok_files:
                ok_files[f] = _doc_path(rm, root, f)[0] == 200
            if not ok_files[f]:
                continue
            out["path"] = f
            it = by_file.get(f) if h["kind"] == "plan" else None
            if it is not None:
                out.update(id=it["id"], title=it.get("title"))
        elif h["kind"] == "idea":
            out["idea"] = idea_of.get(h.get("line"))
        if out.get("id") is not None:
            it = items.get(out["id"]) or {}
            out["version"] = it.get("version")
            out["type"] = it.get("type")
        out["snippet"], out["match"] = _snippet(h.get("text") or "", q)
        hits.append(out)
    return {"q": q, "hits": hits[:SEARCH_MAX_HITS], "total": len(hits),
            "truncated": len(hits) > SEARCH_MAX_HITS}


# ---- version page (plan 49) -------------------------------------------------

def _changelog_block(md: str, version: str) -> str | None:
    """The `## v<version>` section of a rendered changelog (header included),
    or None when the version has no section there."""
    out: list[str] | None = None
    for line in md.splitlines():
        if line.startswith("## "):
            if out is not None:
                break
            if line == f"## v{version}" or line.startswith(f"## v{version} "):
                out = [line]
        elif out is not None:
            out.append(line)
    return "\n".join(out).strip() if out else None


def _version_page(rm, root: Path, v: str) -> dict:
    """Version page data: its items (status rows, so lanes and the branch
    overlay match the list), the forecast, and the unreleased changelog preview
    — the version's section of the public and internal renderers. Read-only:
    the renderers build text, nothing is written."""
    v = (v or "").strip().removeprefix("v")
    if not v or len(v) > 64:
        return {"version": v, "error": "missing version"}
    try:
        st = rm.status(root)
        cfg = rm.read_config(root)
    except (ValueError, FileNotFoundError, OSError) as e:
        return {"version": v, "error": str(e)}
    items = [i for i in st.get("items", []) if i.get("version") == v]
    if not items:
        return {"version": v, "error": f"no items target v{v}"}
    out = {"version": v, "currentVersion": st.get("currentVersion"),
           "items": items, "forecast": (st.get("forecast") or {}).get(v),
           "date": (cfg.get("versionDates") or {}).get(v),
           "summary": (cfg.get("releaseNotes") or {}).get(v),
           "done": sum(i.get("done", 0) for i in items),
           "total": sum(i.get("total", 0) for i in items),
           "public": None, "internal": None}
    try:
        if getattr(rm, "render_public_changelog", None):
            out["public"] = _changelog_block(rm.render_public_changelog(root)[0], v)
        if getattr(rm, "render_internal_changelog", None):
            out["internal"] = _changelog_block(rm.render_internal_changelog(root), v)
    except (ValueError, FileNotFoundError, OSError, KeyError) as e:
        out["changelogError"] = str(e)
    return out


def _discover_roots(rm, root: Path) -> list[tuple[Path, str | None]]:
    """All git checkouts of this repo (main + linked worktrees) that have a
    `.roadmap/`, as (path, branch) with the main checkout first. Outside git,
    or on any git failure, falls back to just [(root, None)].
    """
    roots: list[tuple[Path, str | None]] = []
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            path: Path | None = None
            branch: str | None = None
            entries: list[tuple[Path, str | None]] = []
            for line in out.stdout.splitlines() + [""]:
                if line.startswith("worktree "):
                    path, branch = Path(line[len("worktree "):]), None
                elif line.startswith("branch "):
                    branch = line[len("branch "):].removeprefix("refs/heads/")
                elif not line.strip() and path is not None:
                    entries.append((path, branch))
                    path = None
            # git lists the main checkout first; keep that order.
            roots = [(p.resolve(), b) for p, b in entries
                     if rm.roadmap_dir(p).exists()]
    except (OSError, subprocess.SubprocessError):
        pass
    cur = root.resolve()
    if not any(p == cur for p, _ in roots):
        roots.insert(0, (cur, None))
    return roots


def _trunk_root(statuses: list[dict], roots_meta: list[dict]) -> int:
    """Index of the checkout to show by default: the one on the trunk branch
    discovery resolved, else the main checkout (index 0)."""
    trunk = next((st.get("trunk") for st in statuses if st.get("trunk")), None)
    for i, m in enumerate(roots_meta):
        if trunk and m.get("branch") == trunk:
            return i
    return 0


def _merge_status(statuses: list[dict], roots_meta: list[dict]) -> dict:
    """Merge per-checkout status payloads into one 'all worktrees' view: items
    merged by id, the copy with the most steps done wins and is tagged with the
    checkout it lives on (`checkout`; `branch` stays the git branch overlay);
    currentVersion is the highest across checkouts.
    ponytail: same id with different meaning across branches → most-progressed
    copy wins; per-branch views remain in the dropdown for the exact picture.
    """
    items: dict[int, dict] = {}
    for i, st in enumerate(statuses):
        checkout = roots_meta[i].get("branch") or roots_meta[i]["name"]
        for it in st.get("items", []):
            cand = {**it, "_root": i, "checkout": checkout}
            cur = items.get(it["id"])
            if cur is None or ((cand.get("done", 0), cand.get("pct", 0))
                               > (cur.get("done", 0), cur.get("pct", 0))):
                items[it["id"]] = cand
    def vkey(v):
        return [int(x) if x.isdigit() else 0 for x in str(v).split(".")]
    vers = [st["currentVersion"] for st in statuses if st.get("currentVersion")]
    out = {"project": next((st.get("project") for st in statuses
                            if st.get("project")), None),
           "currentVersion": max(vers, key=vkey) if vers else None,
           "items": sorted(items.values(), key=lambda x: x["id"])}
    # Slot reservations (plan 33) are trunk truth: the merged view shows the
    # trunk checkout's. Absent unless settings.slots is configured.
    if statuses and "slots" in statuses[_trunk_root(statuses, roots_meta)]:
        out["slots"] = statuses[_trunk_root(statuses, roots_meta)]["slots"]
    # Version forecast (plan 44): the trunk checkout's, like slots.
    if statuses and "forecast" in statuses[_trunk_root(statuses, roots_meta)]:
        out["forecast"] = statuses[_trunk_root(statuses, roots_meta)]["forecast"]
    # The run log (plan 38) is trunk truth too: its runs and trunk health.
    # The WIP limit (plan 40) is a trunk setting; the page compares it with
    # the in-flight count it shows.
    for key in ("runs", "trunkHealth", "runWarnings", "wip"):
        if statuses and key in statuses[_trunk_root(statuses, roots_meta)]:
            out[key] = statuses[_trunk_root(statuses, roots_meta)][key]
    return out


def _project_port(root: Path) -> int:
    """Stable preferred port derived from the project path, so the same project
    always maps to the same port (one dashboard per project) while different
    projects land on different ports and coexist."""
    h = hashlib.md5(str(root.resolve()).encode("utf-8")).hexdigest()
    return DEFAULT_PORT + int(h, 16) % PORT_SPAN


def _running_dashboard(root: Path, port: int):
    """Return the URL if a dashboard for THIS project is already serving on
    `port`, else None. Matched via the X-Roadmap-Root response header."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
        with urllib.request.urlopen(req, timeout=0.4) as r:
            if r.headers.get("X-Roadmap-Root") == str(root.resolve()):
                return f"http://127.0.0.1:{port}"
    except Exception:
        return None
    return None


class _Broadcaster:
    """Single background watcher shared by every SSE client and the terminal.

    One thread scans every checkout's change-signature once per second and
    re-runs worktree discovery every RESCAN_TICKS seconds, so checkouts added
    or deleted while serving appear and disappear live. Each payload carries
    every root's status plus the merged view and `trunkRoot` (the default
    view: the trunk checkout with its branch overlay) — clients switch views
    locally, so N open tabs (and N worktrees) still cost one scanner.

    Branch commits never touch .roadmap/, so the signature also carries the
    ref list: one `git for-each-ref` per tick while refs are unchanged.
    """
    RESCAN_TICKS = 5

    def __init__(self, rm, origin: Path, verbose: bool = False,
                 fast_start: bool = False):
        self.rm, self.origin = rm, origin
        self.verbose = verbose
        self.url: str | None = None   # set by serve() once the port is bound
        self.cond = threading.Condition()
        self.version = 0
        # Plan 50: a fresh id per server process, carried in every payload and
        # header, so an open page can tell a restarted server from a dropped
        # connection; `updated` is when the payload last changed.
        self.instance = uuid.uuid4().hex[:12]
        self.updated = time.time()
        self.roots = _discover_roots(rm, origin)
        self._wt_root = origin    # trunk checkout once known (set by _dump)
        self._partial: list | None = None
        if fast_start and len(self.roots) > 1:
            # Fast first paint (plan 50): only the trunk checkout is scanned
            # before the server binds; the start() thread adds the other
            # checkouts as they finish. Signatures first, so a change made
            # during the scan is picked up by the first tick after it.
            self._sigs = self._signature()
            self._partial = self._first_statuses()
            self._core = self._dump(self._padded(self._partial),
                                    scanning=self._scan_progress())
        else:
            self._core = self._dump()
            self._sigs = self._signature()
        self.json = self._with_meta(self._core)

    def _signature(self) -> list:
        # Refs and worktrees are shared by every checkout of the repo: one
        # call covers all. The worktree part is time-budgeted (10 s).
        return ([_roadmap_signature(self.rm, p) for p, _ in self.roots]
                + [_refs_signature(self.origin),
                   _worktree_signature(self.rm, self._wt_root)])

    # ---- fast first paint (plan 50) ------------------------------------
    def _first_statuses(self) -> list:
        """The main checkout's status, plus the trunk checkout's when trunk is
        checked out elsewhere; every other slot None (not scanned yet)."""
        stats: list = [None] * len(self.roots)
        stats[0] = _safe_status(self.rm, self.roots[0][0])
        trunk = stats[0].get("trunk")
        t = next((i for i, (_, b) in enumerate(self.roots)
                  if trunk and b == trunk), 0)
        if stats[t] is None:
            stats[t] = _safe_status(self.rm, self.roots[t][0])
        return stats

    @staticmethod
    def _padded(stats: list) -> list[dict]:
        return [s if s is not None else _pending_status() for s in stats]

    def _scan_progress(self) -> dict:
        stats = self._partial or []
        return {"done": sum(s is not None for s in stats), "total": len(stats)}

    def _finish_scan(self) -> None:
        """Scan the checkouts the first payload skipped, publishing after each
        one, then publish the full payload (worktree map, conflicts)."""
        stats = self._partial
        if stats is None:
            return
        for i, (p, _) in enumerate(self.roots):
            if stats[i] is not None:
                continue
            stats[i] = _safe_status(self.rm, p)
            if any(s is None for s in stats):
                self._publish(self._dump(self._padded(stats),
                                         scanning=self._scan_progress()))
        self._partial = None
        self._publish(self._dump(stats))

    def _with_meta(self, core: str) -> str:
        """`core` (a JSON object) plus the instance id and change time. Kept
        out of `core` so the change check compares data only."""
        meta = json.dumps({"instance": self.instance,
                           "updated": round(self.updated * 1000)})
        return core[:-1] + ", " + meta[1:] if core.endswith("}") else core

    def _publish(self, core: str) -> bool:
        """Swap in a new payload and wake every SSE client; False (and no
        notification) when the data did not actually change."""
        if core == self._core:
            return False
        with self.cond:
            self._core = core
            self.updated = time.time()
            self.json = self._with_meta(core)
            self.version += 1
            self.cond.notify_all()
        return True

    def _dump(self, stats: list[dict] | None = None,
              scanning: dict | None = None) -> str:
        meta = [{"path": str(p), "branch": b, "name": p.name}
                for p, b in self.roots]
        if stats is None:
            stats = [_safe_status(self.rm, p) for p, _ in self.roots]
        merged = _merge_status(stats, meta) if len(stats) > 1 else stats[0]
        trunk = _trunk_root(stats, meta)
        # The worktree map is repo-wide: computed once, from the trunk view.
        self._wt_root = self.roots[trunk][0] if trunk < len(self.roots) else self.origin
        out = {"_roots": meta, "statuses": stats, "merged": merged,
               "trunkRoot": trunk}
        cf = None
        if scanning is not None:
            # Mid-scan (plan 50): the repo-wide panels wait for the full scan.
            out["scanning"] = scanning
        else:
            wt = _safe_worktrees(self.rm, self._wt_root, stats[trunk])
            if wt is not None:
                out["worktrees"] = wt
            cf = _safe_conflicts(self.rm, self._wt_root, stats[trunk])
            if cf is not None:
                out["conflicts"] = cf
            sd = _safe_drift(self.rm, self._wt_root, stats[trunk])
            if sd is not None:
                out["scopeDrift"] = sd
        out["attention"] = _safe_attention(self.rm, self._wt_root, stats[trunk], cf)
        return json.dumps(out)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        self._finish_scan()   # no-op unless started with fast_start
        tick = 0
        while True:
            time.sleep(1)
            tick += 1
            self._tick(rescan=tick % self.RESCAN_TICKS == 0)

    def _tick(self, rescan: bool = False) -> None:
        if rescan:
            new = _discover_roots(self.rm, self.origin)
            if [p for p, _ in new] != [p for p, _ in self.roots]:
                old = {p for p, _ in self.roots}
                self.roots = new
                self._sigs = []   # force a payload rebuild below
                cur = {p for p, _ in new}
                added = sum(1 for p in cur if p not in old)
                removed = sum(1 for p in old if p not in cur)
                print(f"  ↻ {time.strftime('%H:%M:%S')} worktrees now: "
                      f"{len(new)} checkout{'s' if len(new) != 1 else ''}"
                      f" (+{added} -{removed})"
                      + (f"  → {self.url}" if self.url else ""), flush=True)
                if self.verbose:
                    print("      " + ", ".join(b or p.name for p, b in new),
                          flush=True)
        sigs = self._signature()
        if sigs == self._sigs:
            return
        self._sigs = sigs
        snap = self._dump()
        # mtime signatures flap on every file touch (editors, agents, git);
        # only notify clients and print when the status actually changed.
        if not self._publish(snap):
            return
        for line in _summary_lines(json.loads(snap), self.url, self.verbose,
                                   prefix=f"  ↻ {time.strftime('%H:%M:%S')} "):
            print(line, flush=True)

    def snapshot(self):
        with self.cond:
            return self.version, self.json

    def wait(self, last_version: int, timeout: float):
        with self.cond:
            if self.version == last_version:
                self.cond.wait(timeout)
            return self.version, self.json


def serve(rm, root: Path, port: int | None = None,
          open_browser: bool = True, verbose: bool = False,
          bcast: "_Broadcaster | None" = None, handler_only: bool = False):
    """Run a local, read-only web dashboard that pushes live updates via SSE.

    One dashboard per project: port=None derives a stable port from the project
    path. If this project is already being served (in another terminal), point
    at that instance instead of starting a duplicate. Different projects get
    different ports and run side by side. An explicit port is honored strictly.
    Every refresh line in the terminal carries the URL; `verbose` adds one
    line per checkout under each summary.

    `handler_only` (plan 48) returns the per-project request Handler class
    instead of serving, wired to `bcast` — `serve_all` mounts one per project
    under /p/<slug>/, so every endpoint here works there too.
    """
    if not rm.roadmap_dir(root).exists():
        print("No .roadmap/ here — run `roadmap init` first, then `roadmap serve`.")
        return 0

    # One instance serves the main checkout AND every linked git worktree that
    # has a .roadmap/ (re-discovered live by the broadcaster). Port + dedupe
    # key on the primary (main-checkout) root, so `roadmap serve` from any
    # checkout converges on the same dashboard.
    # fast_start (plan 50): bind after the trunk scan only; the watcher
    # thread adds the other checkouts as they finish. Under serve --all (plan
    # 48) the hub passes its own lazily-ticking broadcaster in.
    bcast = bcast or _Broadcaster(rm, root, verbose=verbose, fast_start=True)
    primary = bcast.roots[0][0]
    root_id = str(primary)
    dashboard_html = _dashboard_html()

    def _item_root(query: str) -> Path:
        roots = bcast.roots   # live list — indices match the latest payload
        for pair in query.split("&"):
            k, _, v = pair.partition("=")
            if k == "root" and v.isdigit() and int(v) < len(roots):
                return roots[int(v)][0]
        return roots[0][0]

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Roadmap-Root", root_id)
            self.send_header("X-Roadmap-Instance", bcast.instance)   # plan 50
            self.end_headers()
            self.wfile.write(body)

        def _sse(self, bcast: _Broadcaster) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Roadmap-Root", root_id)
            self.send_header("X-Roadmap-Instance", bcast.instance)   # plan 50
            self.end_headers()
            ver, snap = bcast.snapshot()
            try:
                self.wfile.write(("data: " + snap + "\n\n").encode("utf-8"))
                self.wfile.flush()
                while True:
                    # Block until the shared watcher reports a change (or 15s
                    # keepalive). No per-client filesystem polling.
                    new_ver, new_snap = bcast.wait(ver, 15)
                    if new_ver != ver:
                        ver = new_ver
                        self.wfile.write(("data: " + new_snap + "\n\n").encode("utf-8"))
                    else:
                        self.wfile.write(b": ping\n\n")   # keepalive / disconnect probe
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            rroot = _item_root(query)
            if path == "/":
                self._send(200, dashboard_html.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif path == "/events":
                self._sse(bcast)
            elif path == "/api/status":
                self._send(200, bcast.snapshot()[1].encode("utf-8"),
                           "application/json")
            elif path == "/api/item":
                iid = None
                for pair in query.split("&"):
                    k, _, v = pair.partition("=")
                    if k == "id" and v.isdigit():
                        iid = int(v)
                payload = ({"error": "missing id"} if iid is None
                           else _item_detail(rm, rroot, iid))
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            elif path == "/api/note":
                rel = (urllib.parse.parse_qs(query).get("path") or [""])[0]
                code, payload = _read_doc(rm, rroot, rel)
                self._send(code, json.dumps(payload).encode("utf-8"),
                           "application/json")
            elif path == "/api/ideas":
                self._send(200, json.dumps(_ideas(rm, rroot)).encode("utf-8"),
                           "application/json")
            elif path == "/api/digest":
                since = (urllib.parse.parse_qs(query).get("since") or ["1d"])[0]
                self._send(200, json.dumps(_digest(rm, rroot, since)).encode("utf-8"),
                           "application/json")
            elif path == "/api/search":   # plan 49: full-text search
                q = (urllib.parse.parse_qs(query).get("q") or [""])[0]
                self._send(200, json.dumps(_search(rm, rroot, q)).encode("utf-8"),
                           "application/json")
            elif path == "/api/version":   # plan 49: version page
                v = (urllib.parse.parse_qs(query).get("v") or [""])[0]
                self._send(200, json.dumps(_version_page(rm, rroot, v)).encode("utf-8"),
                           "application/json")
            elif path == "/api/changelog":
                try:
                    payload = rm.changelog_json(rroot)
                except (ValueError, FileNotFoundError, OSError) as e:
                    payload = {"error": str(e)}
                self._send(200, json.dumps(payload).encode("utf-8"),
                           "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:  # silence per-request logging
            pass

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True   # worker threads die with the process

        def handle_error(self, request, client_address) -> None:
            # A browser closing an SSE stream resets the socket — that is normal,
            # not an error. Swallow it instead of dumping a traceback.
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError)):
                return
            super().handle_error(request, client_address)

    if handler_only:
        return Handler
    if port is None:
        preferred = _project_port(primary)
        # Already serving THIS project in another terminal? Point at it, don't
        # start a duplicate. Scan the span in case it landed on a fallback port.
        for candidate in range(preferred, preferred + PORT_SPAN):
            existing = _running_dashboard(primary, candidate)
            if existing:
                print(f"roadmap dashboard already running → {existing}\n"
                      "  This project is already being served (one dashboard "
                      "per project) — open the URL above; nothing new started.",
                      flush=True)
                if open_browser:
                    try:
                        webbrowser.open(existing)
                    except Exception:
                        pass
                return 0
        # Bind the project's stable port; if taken by something else, scan up.
        httpd = None
        for candidate in range(preferred, preferred + PORT_SPAN):
            try:
                httpd = Server(("127.0.0.1", candidate), Handler)
                break
            except OSError:
                continue
        if httpd is None:
            print(f"Error: no free port in {preferred}-{preferred + PORT_SPAN - 1} "
                  "(too many dashboards running?)", file=sys.stderr)
            return 1
    else:
        try:
            httpd = Server(("127.0.0.1", port), Handler)
        except OSError as e:
            print(f"Error: cannot bind 127.0.0.1:{port} — {e}", file=sys.stderr)
            return 1
    port = httpd.server_address[1]

    url = f"http://127.0.0.1:{port}"
    bcast.url = url
    bcast.start()

    print(f"roadmap dashboard → {url}  (Ctrl-C to stop)")
    data = json.loads(bcast.json)
    for line in _summary_lines(data, url, verbose, prefix="  "):
        print(line, flush=True)
    if len(data.get("statuses") or []) > 1 and not verbose:
        print("  (one line per refresh; `serve --verbose` adds per-checkout detail)",
              flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


# ---- all-projects home (plan 48) ---------------------------------------------
# `serve --all` (also `serve` outside any project): one server for every project
# in the per-user registry. `/` serves the same page in "all" mode; `/api/projects`
# the home cards; `/p/<slug>/<endpoint>` mounts that project's normal per-project
# Handler (built by serve(handler_only=True)), so every endpoint a single-project
# dashboard has works under the prefix with no duplication. A project's
# broadcaster starts the first time it is viewed and ticks only while one of its
# SSE streams is open; the home cards come from status() at most every HOME_TTL s.
ALL_PORT = 4690          # below the per-project span (4700+)
ALL_SPAN = 10
ALL_ROOT_ID = "*all-projects*"   # X-Roadmap-Root of the all-projects server
HOME_TTL = 10.0
MODE_META = '<meta name="roadmap-mode" content="project">'
MODE_META_ALL = '<meta name="roadmap-mode" content="all">'


class _LazyBroadcaster(_Broadcaster):
    """A project's broadcaster under `serve --all`: ticks only while at least
    one SSE client watches it; any other request refreshes it (at most once a
    second) so an idle project never serves a stale payload."""

    def __init__(self, *a, **k):
        self._tick_lock = threading.RLock()
        self._count_lock = threading.Lock()
        self.clients = 0
        self._refreshed = time.monotonic()
        super().__init__(*a, **k)

    def _tick(self, rescan: bool = False) -> None:
        with self._tick_lock:
            super()._tick(rescan=rescan)
            self._refreshed = time.monotonic()

    def _run(self) -> None:
        tick = 0
        while True:
            time.sleep(1)
            if self.clients <= 0:
                continue          # nobody watching: no git, no stat, no status()
            tick += 1
            self._tick(rescan=tick % self.RESCAN_TICKS == 0)

    def refresh(self, min_age: float = 1.0) -> None:
        if time.monotonic() - self._refreshed >= min_age:
            try:
                self._tick(rescan=True)
            except Exception:  # noqa: BLE001 — a refresh never fails a request
                pass

    def attach(self) -> None:
        with self._count_lock:
            self.clients += 1
        self.refresh()

    def detach(self) -> None:
        with self._count_lock:
            self.clients = max(0, self.clients - 1)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _card_alerts(st: dict, items: list[dict]) -> list[dict]:
    """The home card's alerts, each only where its feature is in use."""
    out = []
    ref = [i for i in items if (i.get("claim") or {}).get("verdict") == "REFUTED"
           and i.get("lane") != "done"]
    if ref:
        out.append({"kind": "refuted", "text": f"{len(ref)} REFUTED: " + ", ".join(
            i.get("displayId") or f"#{i.get('id')}" for i in ref)})
    clashes = (st.get("slots") or {}).get("clashes")
    if isinstance(clashes, int) and clashes > 0:
        out.append({"kind": "slots",
                    "text": f"{clashes} slot clash{'es' if clashes != 1 else ''}"})
    wip = st.get("wip") or {}
    if wip.get("over"):
        out.append({"kind": "wip", "text": f"{wip.get('count')} in flight "
                                           f"(WIP limit {wip.get('limit')})"})
    late = [d for d in st.get("waitingDue") or []
            if isinstance(d.get("daysLeft"), int) and d["daysLeft"] < 0]
    if late:
        out.append({"kind": "waiting", "text": f"{len(late)} waiting "
                                               f"step{'s' if len(late) != 1 else ''} overdue"})
    th = st.get("trunkHealth") or {}
    if th.get("green") is False:
        bad = [s.get("shard") for s in th.get("shards") or [] if s.get("result") == "fail"]
        out.append({"kind": "trunk", "text": "trunk suite failing"
                    + (f" ({', '.join(str(b) for b in bad)})" if bad else "")})
    return out


def _project_card(rm, row: dict) -> dict:
    """One home card from a registry row: status() of the project root only
    (no worktree scan, no conflicts). A missing path yields a greyed card."""
    card = {k: row.get(k) for k in ("slug", "name", "path", "lastSeen")}
    card["exists"] = bool(row.get("exists"))
    if not card["exists"]:
        return card
    root = Path(row["path"])
    st = _safe_status(rm, root)
    items = st.get("items") or []
    td = sum(i.get("done", 0) for i in items)
    tt = sum(i.get("total", 0) for i in items)
    lanes = (st.get("counts") or {}).get("lanes") or {}
    last = row.get("lastSeen")
    mtime = _roadmap_signature(rm, root)
    if mtime and (not last or _iso(mtime) > last):
        last = _iso(mtime)
    card.update({
        "project": st.get("project"), "version": st.get("currentVersion"),
        "items": len(items), "done": td, "total": tt,
        "pct": round(100 * td / tt) if tt else 0,
        "inFlight": lanes.get("inFlight", 0), "waiting": lanes.get("waiting", 0),
        "blocked": sum(1 for i in items if i.get("blockedBy")),
        "lastActivity": last, "alerts": _card_alerts(st, items)})
    if st.get("error"):
        card["error"] = st["error"]
    return card


class _Home:
    """State of the all-projects server: the cached home cards and the
    per-project mounts (broadcaster + Handler), created on first view."""

    def __init__(self, rm, verbose: bool = False):
        self.rm, self.verbose = rm, verbose
        self.base: str | None = None      # set once the port is bound
        self._card_lock = threading.Lock()
        self._mount_lock = threading.Lock()
        self._cards: dict[str, tuple[float, dict]] = {}
        self._mounts: dict[str, tuple[_LazyBroadcaster, type]] = {}

    def rows(self) -> list[dict]:
        try:
            return list(self.rm.registry_entries())
        except Exception:  # noqa: BLE001 — a broken registry is an empty one
            return []

    def cards(self) -> list[dict]:
        now = time.monotonic()
        out = []
        with self._card_lock:
            for row in self.rows():
                hit = self._cards.get(row["path"])
                if hit is None or now - hit[0] >= HOME_TTL \
                        or hit[1].get("exists") != bool(row.get("exists")):
                    try:
                        card = _project_card(self.rm, row)
                    except Exception as e:  # noqa: BLE001 — one bad project, one bad card
                        card = {**{k: row.get(k) for k in ("slug", "name", "path",
                                                           "lastSeen", "exists")},
                                "error": str(e)}
                    self._cards[row["path"]] = (now, card)
                else:   # names, slugs and lastSeen are always the registry's latest
                    card = {**hit[1], **{k: row.get(k)
                                         for k in ("slug", "name", "lastSeen")}}
                out.append(card)
        return out

    def mount(self, slug: str):
        """(broadcaster, Handler) for the project `slug`, started on first use;
        None when the slug is unknown or its path is gone."""
        row = next((r for r in self.rows() if r.get("slug") == slug), None)
        if row is None or not row.get("exists"):
            return None
        with self._mount_lock:
            hit = self._mounts.get(row["path"])
            if hit is not None:
                return hit
            try:
                root = Path(row["path"])
                b = _LazyBroadcaster(self.rm, root, verbose=self.verbose)
                handler = serve(self.rm, root, bcast=b, handler_only=True)
            except Exception:  # noqa: BLE001
                return None
            if not isinstance(handler, type):
                return None
            if self.base:
                b.url = f"{self.base}/#/p/{urllib.parse.quote(slug)}/"
            b.start()
            self._mounts[row["path"]] = (b, handler)
            return b, handler

    def mounted(self) -> int:
        return len(self._mounts)


def _delegate(outer, handler_cls, path: str) -> None:
    """Answer the request `outer` is handling with a per-project Handler, as if
    it had been sent to that project's own dashboard with `path`."""
    h = handler_cls.__new__(handler_cls)
    for k in ("server", "client_address", "request", "connection", "rfile",
              "wfile", "request_version", "requestline", "command", "headers",
              "raw_requestline", "close_connection"):
        if hasattr(outer, k):
            setattr(h, k, getattr(outer, k))
    h.path = path
    try:
        h.do_GET()
    finally:
        outer.close_connection = getattr(h, "close_connection", True)


def _running_all(port: int):
    """URL of an all-projects server already on `port`, else None."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
        with urllib.request.urlopen(req, timeout=0.4) as r:
            if r.headers.get("X-Roadmap-Root") == ALL_ROOT_ID:
                return f"http://127.0.0.1:{port}"
    except Exception:
        return None
    return None


def serve_all(rm, port: int | None = None, open_browser: bool = True,
              verbose: bool = False) -> int:
    """Serve the all-projects home page (plan 48). One instance per user:
    with port=None an already-running one is reused."""
    home = _Home(rm, verbose=verbose)
    page = _dashboard_html().replace(MODE_META, MODE_META_ALL, 1)

    class AllHandler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Roadmap-Root", ALL_ROOT_ID)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            if path == "/":
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/projects":
                self._json(200, {"projects": home.cards()})
            elif path == "/api/status":
                self._json(200, {"mode": "all", "projects": len(home.rows())})
            elif path.startswith("/p/"):
                slug, _, rest = path[len("/p/"):].partition("/")
                slug = urllib.parse.unquote(slug)
                mount = home.mount(slug)
                if mount is None:
                    self._json(404, {"error": f"no registered project {slug!r} "
                                              "(or its path no longer exists)"})
                    return
                bcast, handler = mount
                rest = "/" + rest
                if rest == "/":    # a typed /p/<slug>/ URL: the page routes by hash
                    self.send_response(302)
                    self.send_header("Location", f"/#/p/{urllib.parse.quote(slug)}/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if rest == "/events":
                    bcast.attach()
                    try:
                        _delegate(self, handler, rest)
                    finally:
                        bcast.detach()
                    return
                if bcast.clients <= 0:
                    bcast.refresh()
                _delegate(self, handler, rest + ("?" + query if query else ""))
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:
            pass

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address) -> None:
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                                ConnectionAbortedError)):
                return
            super().handle_error(request, client_address)

    httpd = None
    if port is None:
        for candidate in range(ALL_PORT, ALL_PORT + ALL_SPAN):
            existing = _running_all(candidate)
            if existing:
                print(f"roadmap home already running → {existing}\n"
                      "  One all-projects server per user — open the URL above; "
                      "nothing new started.", flush=True)
                if open_browser:
                    try:
                        webbrowser.open(existing)
                    except Exception:
                        pass
                return 0
        for candidate in range(ALL_PORT, ALL_PORT + ALL_SPAN):
            try:
                httpd = Server(("127.0.0.1", candidate), AllHandler)
                break
            except OSError:
                continue
        if httpd is None:
            print(f"Error: no free port in {ALL_PORT}-{ALL_PORT + ALL_SPAN - 1}",
                  file=sys.stderr)
            return 1
    else:
        try:
            httpd = Server(("127.0.0.1", port), AllHandler)
        except OSError as e:
            print(f"Error: cannot bind 127.0.0.1:{port} — {e}", file=sys.stderr)
            return 1
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    home.base = url
    n = len(home.rows())
    print(f"roadmap home → {url}  ({n} project{'s' if n != 1 else ''}; "
          "Ctrl-C to stop)", flush=True)
    if not n:
        print("  no projects registered yet — run `roadmap.py status` in a project "
              "to add it", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0
