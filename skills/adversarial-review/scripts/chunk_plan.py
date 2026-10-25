#!/usr/bin/env python3
"""Chunk a whole repo for review: module split under a token budget, risk order,
coverage.json resume state, and optional CodeGraph context.

- Files are grouped by top-level module (first path component; files at the repo root
  form `(root)`). A module over the budget is split by sub-directory, then by file. A
  single file over the budget becomes its own chunk, marked oversized.
- Tokens are estimated at BYTES_PER_TOKEN bytes per token.
- Order: chunks holding changed files first, then chunks with security-relevant path
  names (auth, api, webhook, payment, secret, middleware, ...), then the rest by name.
  A run cut off part-way has covered what matters most.
- coverage.json records every chunk (id, files, tokens, risk, context path) and, per
  chunk, the members that finished it and each member's last status. `--resume` reads it
  back and skips (member, chunk) pairs already done.
- CodeGraph: when `<repo>/.codegraph/` exists and `codegraph` is on PATH, a chunk's
  context comes from `codegraph explore`. Only `explore` is ever run; never `init` or any
  indexing.
Stdlib only.
"""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

BYTES_PER_TOKEN = 4
DEFAULT_CHUNK_BUDGET = 20_000          # tokens; ~80 KB, under the 90 KB context cap
COVERAGE_FILE = "coverage.json"
COVERAGE_VERSION = 1
ROOT_MODULE = "(root)"
SKIP_PREFIXES = (".codegraph/",)        # the index itself is never a review chunk
SECURITY_WORDS = ("auth", "oauth", "api", "webhook", "payment", "billing", "secret",
                  "middleware", "login", "session", "token", "crypto", "permission",
                  "admin", "password", "credential", "acl", "rbac")
RISK_RANK = {"changed": 0, "security": 1, "normal": 2}
CODEGRAPH_TIMEOUT = 60
CODEGRAPH_MAX_FILES = 12
CODEGRAPH_MAX_QUERY_FILES = 40


def estimate_tokens(nbytes):
    return max(1, math.ceil(nbytes / BYTES_PER_TOKEN))


def module_of(rel):
    return rel.split("/", 1)[0] if "/" in rel else ROOT_MODULE


def is_security_path(rel):
    """True when a path component token starts with a security-relevant word."""
    for token in re.split(r"[/._\-\s]+", rel.lower()):
        if token and any(token.startswith(w) for w in SECURITY_WORDS):
            return True
    return False


def _component(rel, depth):
    parts = rel.split("/")
    return "/".join(parts[:depth + 1]) if depth < len(parts) - 1 else rel


def _split(items, budget, depth):
    """Greedy, order-preserving bins of (rel, tokens) under `budget`, grouping by the
    path component at `depth` and recursing into a group that alone exceeds it."""
    groups, order = {}, []
    for rel, tok in items:
        key = _component(rel, depth)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((rel, tok))
    bins, cur, cur_tok = [], [], 0
    for key in order:
        group = groups[key]
        g_tok = sum(t for _, t in group)
        if g_tok > budget:
            if cur:
                bins.append(cur)
                cur, cur_tok = [], 0
            if len(group) == 1:
                bins.append(group)                 # one file over budget: oversized
            else:
                bins.extend(_split(group, budget, depth + 1))
            continue
        if cur and cur_tok + g_tok > budget:
            bins.append(cur)
            cur, cur_tok = [], 0
        cur.extend(group)
        cur_tok += g_tok
    if cur:
        bins.append(cur)
    return bins


def plan_chunks(sizes, budget=DEFAULT_CHUNK_BUDGET, changed=()):
    """Ordered chunk dicts for {rel: bytes}. Ids c01.. follow the risk order."""
    if budget < 1:
        raise ValueError("--chunk-budget must be at least 1 token")
    changed = set(changed)
    modules = {}
    for rel in sorted(sizes):
        modules.setdefault(module_of(rel), []).append((rel, estimate_tokens(sizes[rel])))
    chunks = []
    for module in sorted(modules):
        bins = _split(modules[module], budget, 1 if module != ROOT_MODULE else 0)
        for n, items in enumerate(bins, 1):
            files = [r for r, _ in items]
            tokens = sum(t for _, t in items)
            risk = ("changed" if any(f in changed for f in files) else
                    "security" if any(is_security_path(f) for f in files) else "normal")
            label = module if len(bins) == 1 else f"{module} (part {n}/{len(bins)})"
            chunks.append({"label": label, "module": module, "files": files,
                           "tokens": tokens, "risk": risk,
                           "oversized": tokens > budget,
                           "changed": sum(1 for f in files if f in changed)})
    chunks.sort(key=lambda c: (RISK_RANK[c["risk"]], -c["changed"], c["label"]))
    width = max(2, len(str(len(chunks))))
    for i, c in enumerate(chunks, 1):
        c["id"] = f"c{i:0{width}d}"
        c["members_done"] = []
        c["status"] = {}
        c["context"] = ""
    return chunks


def plannable_files(repo, candidates, is_denied, deny, max_bytes):
    """({rel: bytes}, [(rel, reason)] not chunked). Denied, symlinked, hard-linked,
    oversized, binary or missing files never enter a chunk."""
    sizes, skipped = {}, []
    for rel in candidates:
        if any(rel.startswith(p) for p in SKIP_PREFIXES):
            continue
        pat = is_denied(rel, deny)
        if pat:
            skipped.append((rel, f"deny list ({pat})"))
            continue
        full = Path(repo) / rel
        if full.is_symlink():
            skipped.append((rel, "symlink"))
            continue
        try:
            st = os.lstat(full)
        except OSError:
            continue                              # deleted in the working tree
        if st.st_nlink > 1:
            skipped.append((rel, "hard link"))
            continue
        if st.st_size > max_bytes:
            skipped.append((rel, f"over {max_bytes // 1_000_000} MB"))
            continue
        try:
            with open(full, "rb") as fh:
                head = fh.read(8192)
        except OSError as exc:
            skipped.append((rel, f"unreadable: {exc.strerror or exc}"))
            continue
        if b"\0" in head:
            skipped.append((rel, "binary"))
            continue
        sizes[rel] = st.st_size
    return sizes, skipped


# --- coverage.json ------------------------------------------------------------------------

def new_coverage(chunks, budget, unchunked=(), created=""):
    return {"version": COVERAGE_VERSION, "target": "repo", "chunk_budget": budget,
            "bytes_per_token": BYTES_PER_TOKEN, "created": created,
            "chunks": chunks, "members": {}, "unchunked": [list(u) for u in unchunked]}


def save_coverage(run_dir, cov):
    """Atomic write (temp file + rename) so an interrupted run never leaves half a file."""
    run_dir = Path(run_dir)
    fd, tmp = tempfile.mkstemp(prefix=".coverage-", dir=run_dir)
    with os.fdopen(fd, "w") as fh:
        json.dump(cov, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, run_dir / COVERAGE_FILE)


def load_coverage(run_dir):
    path = Path(run_dir) / COVERAGE_FILE
    if not path.is_file():
        raise ValueError(f"--resume: no {COVERAGE_FILE} in {run_dir}")
    try:
        cov = json.loads(path.read_text())
    except ValueError as exc:
        raise ValueError(f"--resume: {path} is not valid JSON: {exc}") from None
    if not isinstance(cov, dict) or cov.get("version") != COVERAGE_VERSION \
            or not isinstance(cov.get("chunks"), list):
        raise ValueError(f"--resume: {path} is not a coverage file this runner writes")
    return cov


def mark(cov, chunk_id, member, status):
    """Record a member's status on a chunk; `ran` statuses add it to members_done."""
    for c in cov["chunks"]:
        if c["id"] == chunk_id:
            c["status"][member] = status
            if status.startswith("ran") and member not in c["members_done"]:
                c["members_done"].append(member)
            return c
    raise KeyError(chunk_id)


def todo_for(cov, member):
    """Chunks, in risk order, this member has not finished yet."""
    return [c for c in cov["chunks"] if member not in c["members_done"]]


def reviewed_count(cov, member):
    return sum(1 for c in cov["chunks"] if member in c["members_done"])


# --- usage budgeting --------------------------------------------------------------------

def plan_calls(remaining, floor, cost, todo):
    """Chunk calls a member may take: all `todo` when the window is unknown, otherwise
    as many as keep the remaining percent at or above `floor`, at `cost` percent each."""
    if remaining is None:
        return todo
    if cost <= 0:
        return todo if remaining > floor else 0
    return max(0, min(todo, math.floor((remaining - floor) / cost + 1e-9)))


# --- CodeGraph context ------------------------------------------------------------------

def has_codegraph(repo):
    return (Path(repo) / ".codegraph").is_dir()


def codegraph_argv(binary, repo, files, max_files=CODEGRAPH_MAX_FILES):
    """`codegraph explore -p <repo> --max-files N <files...>`. Only explore, never init."""
    query = list(files[:CODEGRAPH_MAX_QUERY_FILES]) or ["."]
    return [binary, "explore", "-p", str(repo), "--max-files", str(max_files), *query]


_PATH_TOKEN_RE = re.compile(r"[\w.@+-]+(?:/[\w.@+-]+)+|[\w@+-]*\.[\w.-]+")


def denied_paths_in(text, is_denied, deny):
    """Path-like tokens in `text` that the deny list matches."""
    hits = set()
    for tok in _PATH_TOKEN_RE.findall(text):
        tok = tok.strip(".:,;`'\"()[]")
        if tok and is_denied(tok, deny):
            hits.add(tok)
    return sorted(hits)


def codegraph_context(repo, files, env=None, timeout=CODEGRAPH_TIMEOUT,
                      is_denied=None, deny=()):
    """(text or None, note). None means: use raw files; the note says why."""
    if not has_codegraph(repo):
        return None, "raw files (no .codegraph/ index)"
    binary = shutil.which("codegraph", path=(env or os.environ).get("PATH"))
    if not binary:
        return None, "raw files (.codegraph/ present but `codegraph` not on PATH)"
    argv = codegraph_argv(binary, repo, files)
    try:
        proc = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"raw files (codegraph explore timed out after {timeout}s)"
    except OSError as exc:
        return None, f"raw files (codegraph explore failed to start: {type(exc).__name__})"
    if proc.returncode != 0 or not proc.stdout.strip():
        return None, f"raw files (codegraph explore exit {proc.returncode})"
    if is_denied is not None:
        hits = denied_paths_in(proc.stdout, is_denied, deny)
        if hits:
            return None, ("raw files (codegraph output named deny-listed path(s): "
                          + ", ".join(hits[:5]) + ")")
    return proc.stdout, "codegraph explore"
