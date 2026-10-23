#!/usr/bin/env python3
"""Adversarial review across installed agent CLIs, read-only, with deterministic triage.

Fans one adversarial prompt out to every installed member CLI in parallel, each in a
verified read-only mode, under a wall-time cap. Writes one <member>.md per member and a
summary.md (status table + ranked findings) to .roadmap/notes/review-<date>-<slug>/.
Claude does the final judgement on that summary; this script only collects and ranks.

Usage:
  run_review.py [TARGET] [--base REF] [--members a,b] [--exclude a,b] [--refute]
                [--timeout 300] [--repo PATH] [--out-dir DIR] [--list]

TARGET (default: diff):
  diff                working tree vs HEAD (or <base>...HEAD with --base)
  branch:<base>       committed changes on this branch: git diff <base>...HEAD
  version:<v>         every plan file in .roadmap/plans/ targeting version <v>
  plan:<id>           one plan file (e.g. plan:29)
  repo                the whole repo, including ROADMAP.md and .roadmap/ state

--refute adds a second round: each member that ran gets the evidenced findings it did
not report itself (fresh process) and tries to disprove them with cited evidence.

Exit codes: 0 review written; 1 bad target or not a git repo; 2 read-only guard
violated (a member changed the working tree) — the run is marked failed.
Stdlib only.
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPT_FILE = SKILL_DIR / "prompts" / "adversarial.md"
REFUTE_PROMPT_FILE = SKILL_DIR / "prompts" / "refute.md"

DEFAULT_TIMEOUT = 300          # per-member wall-time cap, seconds
VERSION_PROBE_TIMEOUT = 15     # `<cli> --version` cap, seconds
MAX_CONTEXT_BYTES = 90_000     # stays under Linux's 128 KiB single-argv limit

# --- opencode model config (the one place these ids live) -------------------------
# Primary is the OpenCode Go model; on usage limit or failure the member retries once
# on the free fallback. No further cascade.
OPENCODE_PRIMARY_MODEL = "opencode-go/deepseek-v4.1-flash"
OPENCODE_FALLBACK_MODEL = "opencode/deepseek-v4.1-flash-free"
OPENCODE_FALLBACK_LABEL = "free"
# opencode v2's shipped `plan` agent only denies edits; it still allows shell (a probe
# ran python and wrote a .pyc). Append rules for the plan agent: deny every action,
# then allow read/glob/grep (last matching rule wins). Needs --standalone so a private
# server reads this env instead of the shared background service.
OPENCODE_READONLY_CONFIG = json.dumps({"agents": {"plan": {"permissions": [
    {"action": "*", "resource": "*", "effect": "deny"},
    {"action": "read", "resource": "*", "effect": "allow"},
    {"action": "glob", "resource": "*", "effect": "allow"},
    {"action": "grep", "resource": "*", "effect": "allow"},
]}}}, separators=(",", ":"))

# Every member call is a fresh process and a fresh session. Any argv token equal to one
# of these, or starting with one plus "=" or "-" (e.g. --session-id, --fork=x), is
# refused. codex's `-s` is its sandbox flag and is allowed only as `-s read-only`.
SESSION_FLAGS = ("--session", "--fork", "--continue", "--resume", "--from-pr",
                 "--conversation", "-c", "-s", "-r")
SESSION_SUBCOMMANDS = frozenset({"resume", "fork"})

# Specific phrases only: bare "quota", "429" or "insufficient" (e.g. "401 insufficient
# permissions") are auth/other errors, not usage limits.
USAGE_LIMIT_RE = re.compile(
    r"usage limit|rate[ -]?limit(?:ed)?|quota exceeded|exceeded (?:your )?(?:current )?quota"
    r"|insufficient[_ ]quota|too many requests|429 too many requests|limit reached",
    re.IGNORECASE,
)
MIN_EVIDENCE_CHARS = 10        # non-space characters a finding's evidence must carry
FINDING_RE = re.compile(r"^\s*[`>*-]*\s*FINDING\|", re.MULTILINE)
REFUTE_RE = re.compile(r"^\s*[`>*-]*\s*REFUTE\|", re.MULTILINE)
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LOCATION_RE = re.compile(r"^(?P<path>\S+?):(?P<line>\d+)(?:-\d+)?$")
SEVERITIES = ("critical", "high", "medium", "low")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}


# --- member registry ------------------------------------------------------------------

@dataclass
class Member:
    name: str
    binary: str
    proof: str                     # one-line read-only proof (full detail: references/members.md)
    prompt_on_stdin: bool = False
    output_file: bool = False      # codex: final message comes from -o <file>
    models: tuple = ()             # opencode: (primary, fallback)
    env: dict = field(default_factory=dict)

    def argv(self, binary_path, prompt, outfile=None, model=None):
        b = binary_path
        if self.name == "codex":
            # `-s` here is codex's --sandbox, not a session flag.
            return [b, "exec", "--skip-git-repo-check", "-s", "read-only",
                    "--color", "never", "-o", str(outfile), "-"]
        if self.name == "cursor-agent":
            return [b, "-p", "--output-format", "text", "--mode", "ask", "--trust", prompt]
        if self.name == "agy":
            # -p consumes the next argument as the prompt, so it must come last.
            return [b, "--mode", "plan", "-p", prompt]
        if self.name == "claude":
            return [b, "-p", "--tools", "Read,Grep,Glob",
                    "--disallowedTools", "Edit,Write,NotebookEdit,Bash",
                    "--permission-mode", "plan", "--permission-prompts", "none",
                    "--strict-mcp-config", "--settings", '{"disableAllHooks":true}']
        if self.name == "opencode":
            return [b, "run", "--standalone", "-m", model, "--agent", "plan", prompt]
        raise ValueError(f"no invocation for member {self.name}")


MEMBERS = [
    Member("codex", "codex", "sandbox `-s read-only`: write attempt denied by the sandbox",
           prompt_on_stdin=True, output_file=True),
    Member("cursor-agent", "cursor-agent",
           "`--mode ask`: write attempt refused (`--mode plan` with -p DID write; not used)"),
    Member("agy", "agy", "`--mode plan`: write attempt refused, no file created"),
    Member("claude", "claude",
           "`--tools Read,Grep,Glob` + plan mode + hooks disabled: no write tool exists",
           prompt_on_stdin=True),
    Member("opencode", "opencode",
           "`--agent plan` + config denying all but read/glob/grep: shell and write refused",
           models=(OPENCODE_PRIMARY_MODEL, OPENCODE_FALLBACK_MODEL),
           env={"OPENCODE_CONFIG_CONTENT": OPENCODE_READONLY_CONFIG}),
]

# Installed CLIs that are deliberately never run (no verified read-only prompt mode).
EXCLUDED = {
    "kimi": "no read-only prompt mode (`kimi -p` rejects `--plan`: "
            "\"Cannot combine --prompt with --plan\")",
}


def session_flags_in(member, argv, prompt=None):
    """Session/continue/fork flags present in argv (empty == fresh session)."""
    found = []
    args = argv[1:]
    for i, arg in enumerate(args):
        if prompt is not None and arg == prompt:
            continue
        if arg in SESSION_SUBCOMMANDS:
            found.append(arg)
            continue
        for flag in SESSION_FLAGS:
            if arg == flag or arg.startswith(flag + "=") or arg.startswith(flag + "-"):
                if member.name == "codex" and flag == "-s" and arg == "-s" \
                        and i + 1 < len(args) and args[i + 1] == "read-only":
                    break  # codex sandbox flag, read-only only
                found.append(arg)
                break
    return found


# --- results ----------------------------------------------------------------------------

@dataclass
class Attempt:
    status: str          # ran | skipped: usage limit | failed: <reason>
    reason: str
    output: str
    returncode: object
    seconds: float
    argv: list
    model: str = ""


@dataclass
class MemberResult:
    name: str
    status: str
    reason: str
    version: str = ""
    attempts: list = field(default_factory=list)

    @property
    def output(self):
        return self.attempts[-1].output if self.attempts else ""

    @property
    def ran(self):
        return self.status.startswith("ran")


# --- subprocess helpers -------------------------------------------------------------

def _run_capped(argv, cwd, timeout, stdin_text=None, extra_env=None):
    """Run argv in its own process group; kill the whole group on timeout.

    Returns (returncode or None on timeout, stdout, stderr, seconds).
    """
    start = time.monotonic()
    proc = subprocess.Popen(
        argv, cwd=cwd, text=True,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
        env={**os.environ, "NO_COLOR": "1", **(extra_env or {})},
    )
    try:
        out, err = proc.communicate(input=stdin_text, timeout=timeout)
        return (proc.returncode, ANSI_RE.sub("", out or ""), ANSI_RE.sub("", err or ""),
                time.monotonic() - start)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return None, out or "", err or "", time.monotonic() - start


def _last_line(text):
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


_REPLY_LINE_RE = re.compile(r"^\s*[`>*-]*\s*(FINDING|REFUTE|UPHOLD)\|", re.MULTILINE)


def classify(returncode, combined, timeout, stderr=""):
    """Map a finished attempt to (status, reason).

    The usage-limit pattern is checked on every exit code. On exit 0 it is checked on
    stderr, and on the reply only when the reply carries no FINDING/REFUTE/UPHOLD
    lines — so a real review that merely discusses rate limiting still counts as ran.
    """
    if returncode is None:
        return f"failed: timeout after {timeout}s", "wall-time cap hit; process group killed"
    if returncode == 0:
        haystack = stderr if _REPLY_LINE_RE.search(combined) else combined
    else:
        haystack = combined
    match = USAGE_LIMIT_RE.search(haystack)
    if match:
        return "skipped: usage limit", f"exit {returncode}; matched {match.group(0)!r}: " \
                                       f"{_last_line(haystack)}"
    if returncode == 0:
        return "ran", ""
    return f"failed: exit {returncode}", _last_line(combined)


def _display_argv(argv, prompt):
    return ["<prompt>" if a == prompt else a for a in argv]


def _attempt(member, binary_path, prompt, repo, timeout, model=None, cap_label=None):
    tmpdir = tempfile.mkdtemp(prefix=f"advrev-{member.name}-")
    outfile = Path(tmpdir) / "last-message.txt"
    try:
        argv = member.argv(binary_path, prompt, outfile=outfile, model=model)
        shown = _display_argv(argv, prompt)
        bad = session_flags_in(member, argv, prompt)
        if bad:  # defence in depth; the registry never builds these
            return Attempt("failed: session flag", f"refused to run with {bad}", "", None,
                           0.0, shown, model or "")
        try:
            rc, out, err, secs = _run_capped(
                argv, repo, timeout, stdin_text=prompt if member.prompt_on_stdin else None,
                extra_env=member.env)
        except OSError as exc:
            return Attempt(f"failed: {type(exc).__name__}", str(exc), "", None, 0.0,
                           shown, model or "")
        body = out
        if member.output_file and outfile.is_file():
            body = outfile.read_text(errors="replace") or out
        combined = "\n".join(x for x in (out, err, body if body is not out else "") if x)
        status, reason = classify(rc, combined, cap_label or timeout, stderr=err)
        if status != "ran" and err.strip():
            body = f"{body}\n\n--- stderr ---\n{err}".strip()
        return Attempt(status, reason, body, rc, secs, shown, model or "")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def probe_version(binary_path, repo, cap=VERSION_PROBE_TIMEOUT):
    try:
        rc, out, err, _ = _run_capped([binary_path, "--version"], repo, cap)
    except OSError as exc:
        return False, str(exc)
    text = (out or err).strip().splitlines()
    first = text[0][:120] if text else ""
    if rc is None:
        return False, f"--version timed out after {cap}s"
    if rc != 0:
        return False, f"--version exit {rc}: {first}"
    return True, first


def run_member(member, prompt, repo, timeout, probe=True):
    """Run one member under ONE wall-time budget of `timeout` seconds in total: the
    --version probe (at most 15 s of it), the call, and opencode's fallback retry,
    which only gets whatever budget the primary left."""
    deadline = time.monotonic() + timeout
    remaining = lambda: deadline - time.monotonic()  # noqa: E731
    path = shutil.which(member.binary)
    if not path:
        return MemberResult(member.name, "skipped: not installed",
                            f"`{member.binary}` not on PATH")
    version = ""
    if probe:
        ok, version = probe_version(path, repo, min(VERSION_PROBE_TIMEOUT, timeout))
        if not ok:
            return MemberResult(member.name, "failed: version probe", version)

    if not member.models:
        att = _attempt(member, path, prompt, repo, max(remaining(), 0.1), cap_label=timeout)
        return MemberResult(member.name, att.status, att.reason, version, [att])

    primary, fallback = member.models
    first = _attempt(member, path, prompt, repo, max(remaining(), 0.1), model=primary,
                     cap_label=timeout)
    if first.status == "ran":
        return MemberResult(member.name, "ran", f"model {primary}", version, [first])
    why = "usage limit" if first.status == "skipped: usage limit" else first.status
    if remaining() < 1:
        return MemberResult(member.name, first.status,
                            f"{primary}: {first.reason}; no budget left for fallback "
                            f"{fallback} within the {timeout}s cap", version, [first])
    second = _attempt(member, path, prompt, repo, remaining(), model=fallback,
                      cap_label=timeout)
    attempts = [first, second]
    note = f"after {why} on {primary}"
    if second.status == "ran":
        return MemberResult(member.name, f"ran (fallback: {OPENCODE_FALLBACK_LABEL}, {note})",
                            f"model {fallback}; primary: {first.reason or first.status}",
                            version, attempts)
    if second.status == "skipped: usage limit":
        return MemberResult(member.name, "skipped: usage limit",
                            f"{primary}: {first.reason or first.status}; "
                            f"{fallback}: {second.reason}", version, attempts)
    return MemberResult(member.name, second.status,
                        f"fallback {fallback} {note}: {second.reason}", version, attempts)


# --- read-only guard ------------------------------------------------------------------

def _git(repo, *args, check=True):
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.decode(errors='replace').strip()}")
    return res.stdout


def _sha1(path):
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


def snapshot(repo, exclude_rel):
    """{path: (porcelain XY, content sha1)} for every dirty or untracked path, plus
    EVERY file under .roadmap/ (tracked, untracked or gitignored), minus exclude_rel.

    Hashing content catches a member editing a file that was already dirty, which
    plain `git status --porcelain` would not show. Gitignored files outside .roadmap/
    are not covered (see references/members.md).
    """
    raw = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    tokens = raw.decode("utf-8", errors="surrogateescape").split("\0")
    entries, i = {}, 0
    prefix = exclude_rel.rstrip("/") + "/" if exclude_rel else None
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if len(tok) < 4:
            continue
        xy, path = tok[:2], tok[3:]
        if xy[0] in "RC":
            i += 1  # skip the rename/copy source path
        if prefix and (path + "/").startswith(prefix):
            continue
        full = Path(repo) / path
        entries[path] = (xy, _sha1(full) if full.is_file() else None)
    roadmap = Path(repo) / ".roadmap"
    if roadmap.is_dir():
        for dirpath, dirnames, filenames in os.walk(roadmap):
            rel_dir = Path(dirpath).relative_to(repo).as_posix()
            dirnames[:] = sorted(d for d in dirnames
                                 if not (prefix and (f"{rel_dir}/{d}/").startswith(prefix)))
            for name in filenames:
                rel = f"{rel_dir}/{name}"
                if prefix and (rel + "/").startswith(prefix):
                    continue
                full = Path(dirpath) / name
                if full.is_file():
                    xy = entries.get(rel, ("", None))[0]
                    entries[rel] = (xy, _sha1(full))
    return entries


def guard_diff(before, after):
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    roadmap = [p for p in changed if p == ".roadmap" or p.startswith(".roadmap/")]
    return changed, roadmap


# --- targets ---------------------------------------------------------------------------

def _cap(text):
    data = text.encode("utf-8", errors="replace")
    if len(data) <= MAX_CONTEXT_BYTES:
        return text
    cut = data[:MAX_CONTEXT_BYTES].decode("utf-8", errors="ignore")
    return cut + f"\n\n[... context truncated at {MAX_CONTEXT_BYTES} bytes; " \
                 "read the remaining files directly from the repo ...]\n"


def _plan_files(repo):
    plans = Path(repo) / ".roadmap" / "plans"
    return sorted(plans.glob("*.md")) if plans.is_dir() else []


def _frontmatter_value(text, key):
    head = text.split("\n---", 2)[0] if text.startswith("---") else ""
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", head, re.MULTILINE)
    return m.group(1).strip().strip("'\"") if m else ""


def build_target(repo, target, base=None):
    """Return (description, slug, context) for a target spec. Raises ValueError."""
    repo = Path(repo)
    kind, _, arg = target.partition(":")
    if kind == "diff":
        if base or arg:
            return build_target(repo, f"branch:{base or arg}")
        diff = _git(repo, "diff", "HEAD").decode(errors="replace")
        untracked = _git(repo, "ls-files", "--others", "--exclude-standard").decode(errors="replace")
        if not diff.strip() and not untracked.strip():
            raise ValueError("working tree is clean vs HEAD — nothing to review "
                             "(use branch:<base>, version:<v>, plan:<id> or repo)")
        ctx = f"## git diff HEAD\n```diff\n{diff}```\n"
        if untracked.strip():
            ctx += f"\n## Untracked files (read them directly)\n{untracked}"
        return "working tree diff vs HEAD", "diff", _cap(ctx)
    if kind == "branch":
        if not arg:
            raise ValueError("branch target needs a base: branch:<base>")
        log = _git(repo, "log", "--oneline", f"{arg}..HEAD").decode(errors="replace")
        diff = _git(repo, "diff", f"{arg}...HEAD").decode(errors="replace")
        if not diff.strip():
            raise ValueError(f"no changes between {arg} and HEAD")
        ctx = f"## Commits {arg}..HEAD\n{log}\n## git diff {arg}...HEAD\n```diff\n{diff}```\n"
        return f"branch diff {arg}...HEAD", f"branch-{arg}", _cap(ctx)
    if kind == "version":
        if not arg:
            raise ValueError("version target needs a version: version:<v>")
        want = arg.lstrip("v")
        files = [p for p in _plan_files(repo)
                 if _frontmatter_value(p.read_text(errors="replace"), "version").lstrip("v") == want]
        if not files:
            raise ValueError(f"no plan files in .roadmap/plans/ target version {arg}")
        ctx = "".join(f"## {p.relative_to(repo)}\n{p.read_text(errors='replace')}\n" for p in files)
        ctx += "\nVerify every checklist step and ✅ Acceptance line above against the code.\n"
        return f"roadmap version {want} ({len(files)} plan(s))", f"version-{want}", _cap(ctx)
    if kind == "plan":
        if not arg.isdigit():
            raise ValueError("plan target needs a numeric id: plan:<id>")
        files = [p for p in _plan_files(repo) if p.name.startswith(f"{int(arg):03d}-")]
        if not files:
            raise ValueError(f"no plan file for id {arg} in .roadmap/plans/")
        p = files[0]
        ctx = f"## {p.relative_to(repo)}\n{p.read_text(errors='replace')}\n" \
              "\nVerify every checklist step and ✅ Acceptance line above against the code.\n"
        return f"plan {int(arg)} ({p.name})", f"plan-{int(arg)}", _cap(ctx)
    if kind == "repo":
        files = _git(repo, "ls-files").decode(errors="replace")
        ctx = "## Tracked files\n" + files
        roadmap = repo / "ROADMAP.md"
        if roadmap.is_file():
            ctx += f"\n## ROADMAP.md\n{roadmap.read_text(errors='replace')}\n"
        versions = [repo / f for f in files.splitlines()
                    if f == "VERSION" or f.endswith("/VERSION")][:20]
        if versions:
            ctx += "\n## VERSION files\n" + "".join(
                f"- {v.relative_to(repo)}: {v.read_text(errors='replace').strip()}\n"
                for v in versions if v.is_file())
        plans = _plan_files(repo)
        if plans:
            ctx += "\n## Plan files (.roadmap/plans/)\n" + "".join(f"- {p.name}\n" for p in plans)
        return "whole repo incl. roadmap state", "repo", _cap(ctx)
    raise ValueError(f"unknown target {target!r} (diff, branch:<base>, version:<v>, plan:<id>, repo)")


def slugify(text):
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-.")[:60] or "target"


def render_prompt(description, context):
    template = PROMPT_FILE.read_text()
    return template.replace("{{TARGET}}", description).replace("{{CONTEXT}}", context)


# --- triage ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity: str
    location: str        # "" when missing
    title: str
    evidence: list       # [(member, evidence)]
    members: set
    evidenced: bool
    note: str = ""
    id: str = ""
    refutations: list = field(default_factory=list)   # [(member, path:line, evidence)]


STOPWORDS = frozenset("a an the in on of to is are by for and or with at from as it this "
                      "that be not no".split())
PIPE_SPLIT_RE = re.compile(r"(?<!\\)\|")


def normalize_title(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _title_words(title):
    return {w for w in normalize_title(title).split() if w not in STOPWORDS}


def similar_titles(a, b):
    """True when two titles share most of their words (same-location merge rule):
    at least 60% of the shorter title's words, and at least two words unless the
    shorter title has fewer than two."""
    wa, wb = _title_words(a), _title_words(b)
    if not wa or not wb:
        return normalize_title(a) == normalize_title(b)
    shared = len(wa & wb)
    smaller = min(len(wa), len(wb))
    return shared / smaller >= 0.6 and shared >= min(2, smaller)


def _fields(body, count):
    r"""Split on unescaped `|` into at most `count` fields; `\|` is a literal pipe.
    The last field keeps any further (unescaped) pipes."""
    parts = PIPE_SPLIT_RE.split(body, maxsplit=count - 1)
    parts += [""] * (count - len(parts))
    return [p.replace("\\|", "|") for p in parts]


def _clean(field_text, unwrap=False):
    text = field_text.strip()
    if unwrap and len(text) > 1 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    return text


_LINE_COUNTS = {}


def _line_count(path):
    key = (str(path), path.stat().st_mtime_ns)
    if key not in _LINE_COUNTS:
        with open(path, "rb") as fh:
            data = fh.read()
        _LINE_COUNTS[key] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return _LINE_COUNTS[key]


def check_location(loc, repo):
    """(normalized location, valid, note). Valid means: path:line form, a relative path
    that stays inside the repo (no absolute path, no `..` escape), an existing file,
    and line number(s) within that file."""
    if loc.startswith("./"):
        loc = loc[2:]
    if not loc:
        return "", False, ""
    m = LOCATION_RE.match(loc)
    if not m:
        return loc, False, "location is not path:line"
    if repo is None:
        return loc, True, ""
    rel = m.group("path")
    if Path(rel).is_absolute() or rel.startswith("~"):
        return loc, False, "absolute path rejected"
    root = Path(repo).resolve()
    full = (root / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        return loc, False, "path escapes the repo"
    if not full.is_file():
        return loc, False, "path not found in repo"
    start = int(m.group("line"))
    end_m = re.search(r"-(\d+)$", loc)
    end = int(end_m.group(1)) if end_m else start
    n = _line_count(full)
    if start < 1 or end < start or end > n:
        return loc, False, f"line {start if start > n or start < 1 else end} not in file " \
                           f"({n} lines)"
    return loc, True, ""


def evidence_ok(evidence):
    return len(re.sub(r"\s", "", evidence)) >= MIN_EVIDENCE_CHARS


def parse_findings(member, text, repo=None):
    """Parse FINDING|sev|path:line|title|evidence lines from one member's reply."""
    out = []
    for line in text.splitlines():
        if not FINDING_RE.match(line):
            continue
        body = line[line.index("FINDING|") + len("FINDING|"):].rstrip().rstrip("`")
        sev, loc, title, evidence = _fields(body, 4)
        sev, loc = _clean(sev, True).lower(), _clean(loc, True)
        title, evidence = _clean(title, True), _clean(evidence)
        note = ""
        if sev not in SEVERITY_RANK:
            note = f"unknown severity {sev!r} treated as low"
            sev = "low"
        if not title or normalize_title(title) == "no findings":
            continue
        if loc.upper() in ("NONE", "N/A", "-"):
            loc = ""
        if evidence.upper() in ("NONE", "N/A", "-"):
            evidence = ""
        loc, loc_ok, loc_note = check_location(loc, repo)
        ev_ok = evidence_ok(evidence)
        if loc_note:
            note = loc_note
        elif loc and evidence and not ev_ok:
            note = f"evidence under {MIN_EVIDENCE_CHARS} characters"
        out.append(Finding(sev, loc, title, [(member, evidence)] if evidence else [],
                           {member}, bool(loc_ok and ev_ok), note))
    return out


def _rank_key(f):
    return (not f.evidenced, SEVERITY_RANK[f.severity], -len(f.members), f.location, f.title)


def _merge_target(merged, f):
    exact = merged.get((f.location, normalize_title(f.title)))
    if exact is not None or not f.location:
        return exact
    for cur in merged.values():
        if cur.location == f.location and similar_titles(cur.title, f.title):
            return cur
    return None


def triage(results, repo=None):
    """Dedupe by exact (location, normalized title), then merge same-location findings
    whose titles share most words. Rank evidenced first, then severity, then number of
    agreeing members. Findings without a valid path:line + evidence are kept but never
    ranked above an evidenced one. Evidenced findings get ids F1..Fn."""
    merged = {}
    for res in results:
        if not res.ran:
            continue
        for f in parse_findings(res.name, res.output, repo):
            cur = _merge_target(merged, f)
            if cur is None:
                merged[(f.location, normalize_title(f.title))] = f
                continue
            cur.members |= f.members
            cur.evidence += [e for e in f.evidence if e not in cur.evidence]
            if SEVERITY_RANK[f.severity] < SEVERITY_RANK[cur.severity]:
                cur.severity = f.severity
            if f.evidenced and not cur.evidenced:
                cur.evidenced, cur.note = True, ""
    ranked = sorted(merged.values(), key=_rank_key)
    for i, f in enumerate(x for x in ranked if x.evidenced):
        f.id = f"F{i + 1}"
    return ranked


# --- refutation round -----------------------------------------------------------------

DATA_BEGIN = "<<<BEGIN UNTRUSTED FINDINGS DATA>>>"
DATA_END = "<<<END UNTRUSTED FINDINGS DATA>>>"


def findings_to_refute(findings, member_name):
    """Evidenced findings this member did not report itself."""
    return [f for f in findings if f.evidenced and member_name not in f.members]


def _quote_data(text):
    """Member text as inert data: one line, no delimiter look-alikes."""
    text = " ".join(str(text).split())
    return text.replace("<<<", "‹‹‹").replace(">>>", "›››")


def render_refute_prompt(description, findings):
    lines = [DATA_BEGIN]
    for f in findings:
        ev = "; ".join(e for _, e in f.evidence)
        lines.append(f"> {f.id} | {f.severity} | {_quote_data(f.location)} | "
                     f"{_quote_data(f.title)} | claimed evidence: {_quote_data(ev)}")
    lines.append(DATA_END)
    template = REFUTE_PROMPT_FILE.read_text()
    return template.replace("{{TARGET}}", description).replace("{{FINDINGS}}", "\n".join(lines))


def parse_refutations(member, text, by_id, repo=None):
    """REFUTE|<id>|<path:line>|<evidence> lines. A refutation counts only when it passes
    the same evidence check as a finding: a path:line inside the repo whose line exists,
    and at least MIN_EVIDENCE_CHARS characters of evidence."""
    out = []
    for line in text.splitlines():
        if not REFUTE_RE.match(line):
            continue
        body = line[line.index("REFUTE|") + len("REFUTE|"):].rstrip().rstrip("`")
        fid, loc, evidence = _fields(body, 3)
        fid, loc, evidence = _clean(fid, True).upper(), _clean(loc, True), _clean(evidence)
        loc, loc_ok, _ = check_location(loc, repo)
        if fid in by_id and loc_ok and evidence_ok(evidence):
            out.append((fid, loc, evidence))
    return out


def run_refute_round(members, round1, findings, description, repo, timeout):
    """Fresh process per member, its own `timeout` budget; {member name: MemberResult}."""
    by_name = {r.name: r for r in round1}
    by_id = {f.id: f for f in findings if f.id}
    jobs = {}
    skipped = {}
    for m in members:
        r1 = by_name.get(m.name)
        if r1 is None or not r1.ran:
            continue
        todo = findings_to_refute(findings, m.name)
        if not todo:
            skipped[m.name] = MemberResult(m.name, "skipped: nothing to refute",
                                           "every evidenced finding is its own")
            continue
        jobs[m.name] = (m, render_refute_prompt(description, todo))
    results = dict(skipped)
    with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as pool:
        futs = {name: pool.submit(run_member, m, prompt, repo, timeout, False)
                for name, (m, prompt) in jobs.items()}
        for name, fut in futs.items():
            results[name] = fut.result()
    for name, res in results.items():
        if not res.ran:
            continue
        for fid, loc, evidence in parse_refutations(name, res.output, by_id, repo):
            f = by_id[fid]
            if name not in f.members and all(r[0] != name for r in f.refutations):
                f.refutations.append((name, loc, evidence))
    return results


# --- output ---------------------------------------------------------------------------

def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _attempt_lines(title, attempts):
    lines = []
    for n, att in enumerate(attempts, 1):
        lines += ["", f"## {title} {n}" + (f" (model {att.model})" if att.model else ""), "",
                  f"- command: `{' '.join(att.argv)}`",
                  f"- exit: {att.returncode if att.returncode is not None else 'timeout'}",
                  f"- seconds: {att.seconds:.1f}", f"- status: {att.status}", "",
                  "```text", att.output.rstrip(), "```"]
    return lines


def write_member_file(out_dir, res, refute=None):
    lines = [f"# {res.name}", "", f"- status: {res.status}"]
    if res.reason:
        lines.append(f"- reason: {res.reason}")
    if res.version:
        lines.append(f"- version: {res.version}")
    lines += _attempt_lines("Attempt", res.attempts)
    if refute is not None:
        lines += ["", f"# Refutation round: {refute.status}"]
        if refute.reason:
            lines.append(f"- reason: {refute.reason}")
        lines += _attempt_lines("Refutation attempt", refute.attempts)
    (out_dir / f"{res.name}.md").write_text("\n".join(lines) + "\n")


def write_summary(out_dir, meta, results, findings, guard, refute_results=None):
    changed, roadmap_changed = guard
    lines = [f"# Adversarial review: {meta['description']}", ""]
    if changed:
        lines += ["**RUN FAILED: read-only guard.** The working tree changed during the "
                  "review; treat every member result as untrusted.", ""]
    lines += [f"- date: {meta['date']}", f"- repo: {meta['repo']}",
              f"- target: `{meta['target']}`", f"- timeout per member: {meta['timeout']}s",
              f"- refutation round: {'on' if refute_results is not None else 'off'}",
              "- read-only guard (repo): " + (
                  "FAIL — changed: " + ", ".join(f"`{p}`" for p in changed) if changed
                  else "PASS (git status unchanged)"),
              "- read-only guard (.roadmap/): " + (
                  "FAIL — changed: " + ", ".join(f"`{p}`" for p in roadmap_changed)
                  if roadmap_changed else "PASS (unchanged)"),
              "", "## Members", "", "| member | status | reason |", "|---|---|---|"]
    for res in results:
        lines.append(f"| {_cell(res.name)} | {_cell(res.status)} | {_cell(res.reason)} |")
    if refute_results is not None:
        lines += ["", "## Refutation round", "", "| member | status | reason |", "|---|---|---|"]
        for name in sorted(refute_results):
            r = refute_results[name]
            lines.append(f"| {_cell(name)} | {_cell(r.status)} | {_cell(r.reason)} |")

    ranked = [f for f in findings if f.evidenced and not f.refutations]
    refuted = [f for f in findings if f.evidenced and f.refutations]
    unconfirmed = [f for f in findings if not f.evidenced]
    lines += ["", "## Findings (ranked: severity, then members agreeing)", ""]
    if not ranked:
        lines.append("_No evidenced findings._")
    else:
        lines += ["| # | id | severity | agree | location | title | members |",
                  "|---|---|---|---|---|---|---|"]
        for i, f in enumerate(ranked, 1):
            lines.append(f"| {i} | {f.id} | {f.severity} | {len(f.members)} | "
                         f"`{_cell(f.location)}` | {_cell(f.title)} | "
                         f"{_cell(', '.join(sorted(f.members)))} |")
        lines.append("")
        for i, f in enumerate(ranked, 1):
            lines.append(f"{i}. **{f.title}** (`{f.location}`, {f.id})")
            for member, ev in f.evidence:
                lines.append(f"   - {member}: {ev}")
    if refute_results is not None:
        lines += ["", "## Refuted (disproved with cited evidence in the refutation round)", ""]
        if not refuted:
            lines.append("_None._")
        for f in refuted:
            lines.append(f"- {f.id} [{f.severity}] **{f.title}** (`{f.location}`; reported by "
                         f"{', '.join(sorted(f.members))})")
            for member, ev in f.evidence:
                lines.append(f"  - claimed by {member}: {ev}")
            for member, loc, ev in f.refutations:
                lines.append(f"  - refuted by {member} at `{loc}`: {ev}")
    lines += ["", "## Unconfirmed (no path:line or no evidence — not ranked as confirmed)", ""]
    if not unconfirmed:
        lines.append("_None._")
    for f in unconfirmed:
        why = f.note or ("no path:line" if not f.location else "no evidence")
        lines.append(f"- [{f.severity}] {f.title} — {f.location or 'NONE'} "
                     f"({', '.join(sorted(f.members))}; {why})")
    lines += ["", "## Next", "",
              "Claude triages: open each `path:line`, mark every finding confirmed / refuted / "
              "needs-info, and report. This script never fixes anything."]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def pick_out_dir(repo, explicit, slug, date):
    if explicit:
        out = Path(explicit)
        if not out.is_absolute():
            out = Path(repo) / out
    else:
        base = Path(repo) / ".roadmap" / "notes" / f"review-{date}-{slug}"
        out, n = base, 2
        while out.exists():
            out = base.with_name(f"{base.name}-{n}")
            n += 1
    out.mkdir(parents=True, exist_ok=True)
    return out


# --- CLI ------------------------------------------------------------------------------

def _names(csv):
    return [n.strip() for n in (csv or "").split(",") if n.strip()]


def select_members(members_csv=None, exclude_csv=None):
    """Return (members to run, [(name, status, reason)] for members not run)."""
    known = {m.name: m for m in MEMBERS}
    every = list(known) + list(EXCLUDED)
    wanted, dropped = _names(members_csv), _names(exclude_csv)
    unknown = [n for n in wanted + dropped if n not in every]
    if unknown:
        raise ValueError(f"unknown member(s): {', '.join(unknown)} (known: {', '.join(every)})")
    pool = wanted or every
    run, not_run = [], []
    for name in pool:
        if name in dropped:
            not_run.append((name, "skipped: excluded by user", "--exclude"))
        elif name in EXCLUDED:
            not_run.append((name, "skipped: excluded", EXCLUDED[name]))
        else:
            run.append(known[name])
    return run, not_run


def list_members():
    for m in MEMBERS:
        path = shutil.which(m.binary)
        print(f"{m.name:13} {'installed' if path else 'not installed':14} {m.proof}")
    for name, why in EXCLUDED.items():
        print(f"{name:13} {'excluded':14} {why}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target", nargs="?", default="diff")
    ap.add_argument("--base", help="base ref for a diff target (git diff <base>...HEAD)")
    ap.add_argument("--members", help="comma-separated subset of members to run")
    ap.add_argument("--exclude", action="append", default=[],
                    help="member(s) to leave out, comma-separated or repeated "
                         "(e.g. --exclude claude for a cross-vendor review of a Claude diff)")
    ap.add_argument("--refute", action="store_true",
                    help="second round: members try to disprove each other's findings")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--repo", default=None, help="repo root (default: git toplevel of CWD)")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--list", action="store_true", help="show members and exit")
    args = ap.parse_args(argv)

    if args.list:
        list_members()
        return 0
    try:
        repo = Path(_git(args.repo or os.getcwd(), "rev-parse", "--show-toplevel")
                    .decode().strip())
    except (RuntimeError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: not a git repository: {exc}", file=sys.stderr)
        return 1
    try:
        members, not_run = select_members(args.members, ",".join(args.exclude))
        description, slug, context = build_target(repo, args.target, args.base)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    date = _dt.date.today().isoformat()
    out_dir = pick_out_dir(repo, args.out_dir, slugify(slug), date)
    try:
        out_rel = str(out_dir.resolve().relative_to(repo.resolve()))
    except ValueError:
        out_rel = None
    prompt = render_prompt(description, context)

    before = snapshot(repo, out_rel)
    with ThreadPoolExecutor(max_workers=max(1, len(members))) as pool:
        futures = [pool.submit(run_member, m, prompt, str(repo), args.timeout) for m in members]
        results = [f.result() for f in futures]
    findings = triage(results, repo)
    refute_results = None
    if args.refute:
        refute_results = run_refute_round(members, results, findings, description,
                                          str(repo), args.timeout)
    after = snapshot(repo, out_rel)
    changed, roadmap_changed = guard_diff(before, after)

    results += [MemberResult(name, status, reason) for name, status, reason in not_run]
    for res in results:
        write_member_file(out_dir, res, (refute_results or {}).get(res.name))
    meta = {"description": description, "date": date, "repo": str(repo),
            "target": args.target if not args.base else f"{args.target} --base {args.base}",
            "timeout": args.timeout}
    write_summary(out_dir, meta, results, findings, (changed, roadmap_changed), refute_results)

    print(f"summary: {out_dir / 'summary.md'}")
    for res in results:
        print(f"  {res.name:13} {res.status}" + (f" — {res.reason}" if res.reason else ""))
    n_ref = sum(1 for f in findings if f.refutations)
    print(f"findings: {sum(f.evidenced and not f.refutations for f in findings)} ranked, "
          f"{n_ref} refuted, {sum(not f.evidenced for f in findings)} unconfirmed")
    if changed:
        print("RUN FAILED: read-only guard — changed: " + ", ".join(changed), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
