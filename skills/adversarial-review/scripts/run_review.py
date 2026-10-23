#!/usr/bin/env python3
"""Adversarial review across installed agent CLIs, read-only, with deterministic triage.

Fans one adversarial prompt out to every installed member CLI in parallel, each in a
verified read-only mode, under a wall-time cap. Writes one <member>.md per member and a
summary.md (status table + ranked findings) to .roadmap/notes/review-<date>-<slug>/.
Claude does the final judgement on that summary; this script only collects and ranks.

Usage:
  run_review.py [TARGET] [--base REF] [--members a,b] [--exclude a,b] [--refute]
                [--security] [--decided TEXT|@FILE] [--timeout 300] [--repo PATH]
                [--out-dir DIR] [--list]

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
import bisect
import datetime as _dt
import fnmatch
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
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPT_FILE = SKILL_DIR / "prompts" / "adversarial.md"
REFUTE_PROMPT_FILE = SKILL_DIR / "prompts" / "refute.md"
SECURITY_SYNC_SCRIPT = SKILL_DIR / "scripts" / "sync-security-refs.py"

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
SECURITY_DIR = SKILL_DIR / "references" / "security"


def opencode_readonly_config():
    """Deny every action, then allow read/glob/grep. No external_directory rule: the
    security checklists are copied into the review snapshot, so nothing outside the
    member's working directory is ever needed."""
    return json.dumps({"agents": {"plan": {"permissions": [
        {"action": "*", "resource": "*", "effect": "deny"},
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "glob", "resource": "*", "effect": "allow"},
        {"action": "grep", "resource": "*", "effect": "allow"},
    ]}}}, separators=(",", ":"))


OPENCODE_READONLY_CONFIG = opencode_readonly_config()

# (3) Environment allowlist. A member process gets only these variables, any LC_*, and
# its own CLI's auth variables (MEMBER_AUTH_ENV); nothing else from the caller's env.
# HOME/USER/LOGNAME/SHELL and XDG_* are needed for the CLIs to find their own login and
# config; proxy and CA variables are needed to reach the model APIs on some networks.
BASE_ENV_ALLOW = frozenset({
    "PATH", "LANG", "TERM", "TMPDIR", "HOME", "USER", "LOGNAME", "SHELL",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"})
BASE_ENV_PREFIXES = ("LC_",)
MEMBER_AUTH_ENV = {
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_HOME"),
    "cursor-agent": ("CURSOR_API_KEY", "CURSOR_API_ENDPOINT"),
    "agy": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT"),
    "claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"),
    "opencode": ("OPENCODE_API_KEY",),
}


def member_env(member, environ=None):
    """The complete environment for one member process (allowlist only)."""
    environ = os.environ if environ is None else environ
    auth = set(MEMBER_AUTH_ENV.get(member.name, ()))
    env = {k: v for k, v in environ.items()
           if k in BASE_ENV_ALLOW or k in auth or k.startswith(BASE_ENV_PREFIXES)}
    env["NO_COLOR"] = "1"
    env.update(member.env)          # set by this script (e.g. opencode's read-only config)
    return env


# (1) Sanitized snapshot: members never run in the live tree.
DEFAULT_DENY = (".env*", "*.pem", "*.key", "id_*", ".npmrc", ".netrc", ".git",
                "node_modules", "*.p12", "*.pfx", ".pypirc", ".ssh", ".aws")
SNAPSHOT_SECURITY = ".adversarial-review/security"
MAX_SNAPSHOT_FILE = 5_000_000
MAX_SCAN_FILE = 2_000_000
QUOTE_WINDOW = 3               # a quote must appear within this many lines of path:line
REFUTE_QUORUM = 2              # distinct members whose verified refutations drop a finding

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
LABELS = {"confirmed": "Confirmed", "needs verification": "Needs verification"}
LENSES = ("production breakage", "security", "maintainability")
LENS_TEXT = {
    "production breakage": "**Production breakage.** What fails, crashes, corrupts data, "
                           "or regresses for users or callers once this ships?",
    "security": "**Security.** What can an attacker or an untrusted input reach? Use the "
                "security checklists listed below.",
    "maintainability": "**Maintainability.** What will the next change break? Look for "
                       "hidden coupling, contracts that drift from their docs, untested "
                       "behaviour, and duplicated logic that will diverge.",
}
PROJECT_DOCS = ("RULES.md", "DESIGN.md", "ARCHITECTURE.md")
NOT_CHECKED_RE = re.compile(r"^\s*[`>*-]*\s*NOT_CHECKED\|(.*)$", re.MULTILINE)
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
    lens: str = ""
    dropped: list = field(default_factory=list)       # [(title, reason)] — evidence rule
    not_checked: list = field(default_factory=list)   # NOT_CHECKED| lines

    @property
    def output(self):
        return self.attempts[-1].output if self.attempts else ""

    @property
    def ran(self):
        return self.status.startswith("ran")


# --- subprocess helpers -------------------------------------------------------------

def _run_capped(argv, cwd, timeout, stdin_text=None, env=None):
    """Run argv in its own process group; kill the whole group on timeout.

    Returns (returncode or None on timeout, stdout, stderr, seconds).
    """
    start = time.monotonic()
    proc = subprocess.Popen(
        argv, cwd=cwd, text=True,
        stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
        env=env if env is not None else {**os.environ, "NO_COLOR": "1"},
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
                env=member_env(member))
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


def probe_version(binary_path, repo, cap=VERSION_PROBE_TIMEOUT, env=None):
    try:
        rc, out, err, _ = _run_capped([binary_path, "--version"], repo, cap, env=env)
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
        ok, version = probe_version(path, repo, min(VERSION_PROBE_TIMEOUT, timeout),
                                    env=member_env(member))
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

@dataclass
class Target:
    description: str
    slug: str
    context: str
    kind: str              # diff | branch | version | plan | repo
    files: list            # files under review (changed files, or plan files)


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


def _lines(raw):
    return [ln for ln in raw.decode(errors="replace").splitlines() if ln.strip()]


def build_target(repo, target, base=None):
    """Return a Target for a target spec. Raises ValueError."""
    repo = Path(repo)
    kind, _, arg = target.partition(":")
    if kind == "diff":
        if base or arg:
            return build_target(repo, f"branch:{base or arg}")
        diff = _git(repo, "diff", "HEAD").decode(errors="replace")
        untracked = _lines(_git(repo, "ls-files", "--others", "--exclude-standard"))
        if not diff.strip() and not untracked:
            raise ValueError("working tree is clean vs HEAD — nothing to review "
                             "(use branch:<base>, version:<v>, plan:<id> or repo)")
        files = _lines(_git(repo, "diff", "--name-only", "HEAD")) + untracked
        ctx = f"## git diff HEAD\n```diff\n{diff}```\n"
        if untracked:
            ctx += "\n## Untracked files (read them directly)\n" + "\n".join(untracked) + "\n"
        return Target("working tree diff vs HEAD", "diff", _cap(ctx), "diff", files)
    if kind == "branch":
        if not arg:
            raise ValueError("branch target needs a base: branch:<base>")
        log = _git(repo, "log", "--oneline", f"{arg}..HEAD").decode(errors="replace")
        diff = _git(repo, "diff", f"{arg}...HEAD").decode(errors="replace")
        if not diff.strip():
            raise ValueError(f"no changes between {arg} and HEAD")
        files = _lines(_git(repo, "diff", "--name-only", f"{arg}...HEAD"))
        ctx = f"## Commits {arg}..HEAD\n{log}\n## git diff {arg}...HEAD\n```diff\n{diff}```\n"
        return Target(f"branch diff {arg}...HEAD", f"branch-{arg}", _cap(ctx), "branch", files)
    if kind == "version":
        if not arg:
            raise ValueError("version target needs a version: version:<v>")
        want = arg.lstrip("v")
        plans = [p for p in _plan_files(repo)
                 if _frontmatter_value(p.read_text(errors="replace"), "version").lstrip("v") == want]
        if not plans:
            raise ValueError(f"no plan files in .roadmap/plans/ target version {arg}")
        ctx = "".join(f"## {p.relative_to(repo)}\n{p.read_text(errors='replace')}\n" for p in plans)
        ctx += "\nVerify every checklist step and ✅ Acceptance line above against the code.\n"
        return Target(f"roadmap version {want} ({len(plans)} plan(s))", f"version-{want}",
                      _cap(ctx), "version", [p.relative_to(repo).as_posix() for p in plans])
    if kind == "plan":
        if not arg.isdigit():
            raise ValueError("plan target needs a numeric id: plan:<id>")
        plans = [p for p in _plan_files(repo) if p.name.startswith(f"{int(arg):03d}-")]
        if not plans:
            raise ValueError(f"no plan file for id {arg} in .roadmap/plans/")
        p = plans[0]
        ctx = f"## {p.relative_to(repo)}\n{p.read_text(errors='replace')}\n" \
              "\nVerify every checklist step and ✅ Acceptance line above against the code.\n"
        return Target(f"plan {int(arg)} ({p.name})", f"plan-{int(arg)}", _cap(ctx), "plan",
                      [p.relative_to(repo).as_posix()])
    if kind == "repo":
        tracked = _git(repo, "ls-files").decode(errors="replace")
        ctx = "## Tracked files\n" + tracked
        roadmap = repo / "ROADMAP.md"
        if roadmap.is_file():
            ctx += f"\n## ROADMAP.md\n{roadmap.read_text(errors='replace')}\n"
        versions = [repo / f for f in tracked.splitlines()
                    if f == "VERSION" or f.endswith("/VERSION")][:20]
        if versions:
            ctx += "\n## VERSION files\n" + "".join(
                f"- {v.relative_to(repo)}: {v.read_text(errors='replace').strip()}\n"
                for v in versions if v.is_file())
        plans = _plan_files(repo)
        if plans:
            ctx += "\n## Plan files (.roadmap/plans/)\n" + "".join(f"- {p.name}\n" for p in plans)
        return Target("whole repo incl. roadmap state", "repo", _cap(ctx), "repo", [])
    raise ValueError(f"unknown target {target!r} (diff, branch:<base>, version:<v>, plan:<id>, repo)")


def slugify(text):
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-.")[:60] or "target"


# --- sanitized snapshot -----------------------------------------------------------------

@dataclass
class Snapshot:
    root: Path
    copied: list            # repo-relative files copied
    excluded: list          # [(rel, pattern)] removed by the deny list
    skipped: list           # [(rel, reason)] symlinks, oversized, unreadable
    deny: tuple

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def is_denied(rel, deny):
    """Pattern that excludes `rel`, or None. A pattern with `/` matches the whole path
    (or a directory prefix of it); others match any single path component."""
    low = rel.lower()
    parts = low.split("/")
    for pat in deny:
        p = pat.lower().strip("/")
        if "/" in p:
            if fnmatch.fnmatchcase(low, p) or low.startswith(p + "/"):
                return pat
        elif any(fnmatch.fnmatchcase(part, p) for part in parts):
            return pat
    return None


def _universe(repo):
    """Tracked + untracked-but-not-ignored files: gitignored files never enter."""
    raw = _git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({f for f in raw.decode("utf-8", errors="surrogateescape").split("\0") if f})


def snapshot_files(repo, target, out_rel=None):
    """Files a snapshot should hold. diff/branch: the changed files, every file in the
    same directories (non-recursive), project/instruction docs, ROADMAP.md and plan
    files. repo/plan/version: the whole tree."""
    universe = _universe(repo)
    skip_prefixes = [p for p in ((out_rel or "").rstrip("/") + "/", ".roadmap/notes/review-",
                                 ".adversarial-review/") if p and p != "/"]
    universe = [f for f in universe if not any(f.startswith(p) for p in skip_prefixes)]
    if target.kind not in ("diff", "branch"):
        return universe
    have = set(universe)
    dirs = {os.path.dirname(f) for f in target.files}
    wanted = {f for f in target.files if f in have}
    wanted |= {f for f in universe if os.path.dirname(f) in dirs}
    docs = set(PROJECT_DOCS) | {"ROADMAP.md", "README.md"} | set(INSTRUCTION_FILES)
    wanted |= {f for f in universe if f in docs or
               (f.startswith(".roadmap/plans/") and f.endswith(".md"))}
    return sorted(wanted)


def build_snapshot(repo, target, deny=DEFAULT_DENY, out_rel=None,
                   security_dir=SECURITY_DIR):
    root = Path(tempfile.mkdtemp(prefix="advrev-snap-"))
    copied, excluded, skipped = [], [], []
    for rel in snapshot_files(repo, target, out_rel):
        pat = is_denied(rel, deny)
        if pat:
            excluded.append((rel, pat))
            continue
        src = Path(repo) / rel
        if src.is_symlink():
            skipped.append((rel, "symlink"))
            continue
        if not src.is_file():
            continue                      # deleted in the working tree
        try:
            if src.stat().st_size > MAX_SNAPSHOT_FILE:
                skipped.append((rel, f"over {MAX_SNAPSHOT_FILE // 1_000_000} MB"))
                continue
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        except OSError as exc:
            skipped.append((rel, f"unreadable: {exc.strerror or exc}"))
            continue
        copied.append(rel)
    sec = root / SNAPSHOT_SECURITY
    sec.mkdir(parents=True, exist_ok=True)
    for item in Path(security_dir).glob("*"):
        if item.is_file() and not item.is_symlink():
            shutil.copyfile(item, sec / item.name)
    return Snapshot(root, copied, excluded, skipped, tuple(deny))


def tree_hashes(root):
    """{rel: sha1} of every file under root (to notice member writes in the snapshot)."""
    out = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            full = Path(dirpath) / name
            out[full.relative_to(root).as_posix()] = _sha1(full)
    return out


# --- prompt blocks ----------------------------------------------------------------------

def project_docs_block(repo):
    """(e) Name the project docs that exist; members read them (never pasted)."""
    present = [d for d in PROJECT_DOCS if (Path(repo) / d).is_file()]
    if not present:
        return "None of RULES.md, DESIGN.md or ARCHITECTURE.md exists in this repo."
    return "Read these before judging anything:\n" + "".join(f"- `{d}`\n" for d in present)


def decided_block(decided):
    """(f) Items decided on purpose, from --decided (text, or @file for one per line)."""
    items = []
    for entry in decided or []:
        if entry.startswith("@"):
            path = Path(entry[1:]).expanduser()
            items += [ln.strip(" -*\t") for ln in path.read_text().splitlines() if ln.strip()]
        elif entry.strip():
            items.append(entry.strip())
    return "".join(f"- {i}\n" for i in items) if items else "- (none recorded for this run)\n"


def omissions_block(kind):
    """(i) Diff targets are judged by what the change omits, too."""
    if kind not in ("diff", "branch"):
        return ""
    return ("## Omissions count\n\n"
            "Judge the change by the guards that should surround it, not only the added "
            "lines. Read the changed files plus their immediate context: the enclosing "
            "handler, the imports, and the called functions. A missing guard that the "
            "change should have added (an auth check, input validation, an error path, a "
            "test) is a finding because the diff omits it. When the verdict truly needs "
            "whole-app context that the diff cannot provide, label it **Needs "
            "verification**, and say what would confirm it.\n")


# (h) changed file -> secaudit domain checklists. First match per rule; several rules
# may match one file. Domains missing from the vendored set are skipped.
SECURITY_ROUTES = [
    (r"(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|"
     r"requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|uv\.lock|"
     r"go\.(mod|sum)|Cargo\.(toml|lock)|Gemfile(\.lock)?|composer\.(json|lock))$",
     ("supply-chain", "framework-versions")),
    (r"(^|/)\.github/workflows/|(^|/)\.gitlab-ci\.yml$|(^|/)\.circleci/", ("ci-cd-security",)),
    (r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$", ("docker-security",)),
    (r"(^|/)(k8s|kubernetes|helm|charts)/", ("kubernetes-security",)),
    (r"(^|/)wrangler\.(toml|jsonc?)$", ("cloudflare-workers-security",)),
    (r"(^|/)(routes?|api|server|handlers?|controllers?|endpoints?|middleware)(/|\.)|"
     r"(^|/)pages/api/|(^|/)app/.*/route\.[jt]sx?$",
     ("auth", "privilege-escalation", "web-vulns", "api-surface", "data-access")),
    (r"auth|login|session|signin|signup|password|jwt|clerk", ("auth",)),
    (r"oauth|oidc|openid", ("oauth-oidc-security",)),
    (r"admin|role|permission|rbac|acl", ("privilege-escalation",)),
    (r"(^|/)\.env|secret|credential|config\.|settings\.", ("secrets",)),
    (r"migration|schema\.prisma|\.sql$|(^|/)db/|database|drizzle|supabase", ("data-access",
                                                                            "database")),
    (r"prisma", ("prisma-security",)),
    (r"postgres|(^|/)rls", ("postgres-security",)),
    (r"webhook", ("webhook-security",)),
    (r"stripe|payment|billing|checkout|subscription", ("payments",)),
    (r"revenuecat", ("revenuecat-security",)),
    (r"upload|storage|bucket|(^|/)s3|(^|/)r2", ("object-storage-security",)),
    (r"crypto|hash|encrypt|token", ("cryptography",)),
    (r"rate.?limit|throttle", ("rate-limiting",)),
    (r"log(ger|ging)?\.|monitor|sentry", ("logging-monitoring",)),
    (r"(^|/)mcp|agent|llm|openai|anthropic|prompt", ("ai-integration", "mcp-agent-security")),
    (r"tenant|(^|/)orgs?/|organization", ("multi-tenant-isolation",)),
    (r"proxy|forwarded", ("proxy-trust",)),
    (r"websocket|socket|realtime|(^|/)ws/", ("realtime-security",)),
    (r"markdown|sanitiz|richtext|rich-text|editor|wysiwyg", ("rich-text-security",)),
    (r"next\.config|vercel\.json|netlify\.toml|headers|cors", ("deployment",)),
    (r"(^|/)convex/", ("convex-security",)),
    (r"better-auth", ("better-auth-security",)),
    (r"(^|/)app\.json$|expo", ("expo-security",)),
    (r"react-native|(^|/)(ios|android)/", ("react-native-security",)),
    (r"discord", ("discord-bot-security",)),
    (r"fxmanifest\.lua$|\.lua$", ("fivem-security",)),
    (r"\.py$", ("python-web-security",)),
]


def vendored_domains(security_dir=SECURITY_DIR):
    return {p.stem for p in Path(security_dir).glob("*.md") if p.name != "README.md"}


def route_security(files, security_dir=SECURITY_DIR):
    """{file: [domain, ...]} for each changed file that matches a route."""
    have = vendored_domains(security_dir)
    out = {}
    for f in files:
        low = f.lower()
        domains = []
        for pattern, doms in SECURITY_ROUTES:
            if re.search(pattern, low):
                domains += [d for d in doms if d in have and d not in domains]
        if domains:
            out[f] = domains
    return out


def security_block(lens, kind, files, security_dir=SECURITY_DIR):
    """(h) Security lens: route each changed file to its vendored checklist(s)."""
    if lens != "security":
        return ""
    sdir = Path(security_dir).resolve()
    have = sorted(vendored_domains(sdir))
    if not have:
        return "## Security checklists\n\nNo vendored checklists found; use your own.\n"
    lines = ["## Security checklists (vendored secaudit, read by path)", "",
             f"Directory: `{sdir}`. Each checklist is `{sdir}/<domain>.md`."]
    routed = route_security(files, sdir) if kind in ("diff", "branch") else {}
    if routed:
        lines += ["", "Read the checklist(s) routed to each changed file, then judge that "
                      "file against them:", ""]
        for f, doms in routed.items():
            lines.append(f"- `{f}` → " + ", ".join(f"`{sdir}/{d}.md`" for d in doms))
    unrouted = [f for f in files if f not in routed] if kind in ("diff", "branch") else []
    if unrouted:
        lines += ["", "No route matched these files. Pick a checklist yourself if they touch "
                      "security: " + ", ".join(f"`{f}`" for f in unrouted[:30])]
    lines += ["", "Available domains: " + ", ".join(have) + "."]
    return "\n".join(lines) + "\n"


def lens_for(index, security_only=False):
    return "security" if security_only else LENSES[index % len(LENSES)]


def render_prompt(target, repo, lens="production breakage", decided=None,
                  security_dir=SECURITY_DIR):
    template = PROMPT_FILE.read_text()
    blocks = {
        "{{TARGET}}": target.description,
        "{{LENS}}": LENS_TEXT[lens],
        "{{PROJECT_DOCS}}": project_docs_block(repo),
        "{{DECIDED}}": decided_block(decided),
        "{{OMISSIONS}}": omissions_block(target.kind),
        "{{SECURITY}}": security_block(lens, target.kind, target.files, security_dir),
    }
    for key, value in blocks.items():
        template = template.replace(key, value)
    return template.replace("{{CONTEXT}}", target.context)   # last: repo data, unexpanded


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
    label: str = "Needs verification"                 # Confirmed | Needs verification
    impact: list = field(default_factory=list)        # [(member, impact path)]


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
    if rel.startswith(".adversarial-review/"):
        return loc, False, "cites the review's own checklist copy, not the repo"
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


def _norm_ws(text):
    return " ".join(text.split())


def quote_near(root, loc, quote, window=QUOTE_WINDOW):
    """True when `quote` (whitespace-normalised, at least MIN_EVIDENCE_CHARS non-space
    characters, surrounding backticks/quotes stripped) appears in the cited file within
    `window` lines of the cited line or range."""
    q = quote.strip()
    while len(q) > 1 and q[0] == q[-1] and q[0] in "`'\"":
        q = q[1:-1].strip()
    if not evidence_ok(q):
        return False
    m = LOCATION_RE.match(loc)
    if not m:
        return False
    start = int(m.group("line"))
    end_m = re.search(r"-(\d+)$", loc)
    end = int(end_m.group(1)) if end_m else start
    try:
        lines = (Path(root) / m.group("path")).read_text(errors="replace").splitlines()
    except OSError:
        return False
    chunk = lines[max(0, start - 1 - window):end + window]
    return _norm_ws(q) in _norm_ws(" ".join(chunk))


def evidence_ok(evidence):
    return len(re.sub(r"\s", "", evidence)) >= MIN_EVIDENCE_CHARS


def parse_findings(member, text, repo=None):
    """Parse one member's reply. Returns (kept, dropped).

    Line format: FINDING|severity|label|path:line|title|evidence|impact path
    Evidence rule (j): a finding is kept only with a valid in-repo path:line whose line
    exists, evidence and an impact path of at least MIN_EVIDENCE_CHARS each, and a
    Confirmed / Needs verification label. Anything else is dropped (title, reason) —
    never kept at a lower rank.
    """
    kept, dropped = [], []
    for line in text.splitlines():
        if not FINDING_RE.match(line):
            continue
        body = line[line.index("FINDING|") + len("FINDING|"):].rstrip().rstrip("`")
        sev, label, loc, title, evidence, impact = _fields(body, 6)
        sev, loc = _clean(sev, True).lower(), _clean(loc, True)
        label = LABELS.get(_clean(label, True).lower().strip("[]"))
        title, evidence, impact = _clean(title, True), _clean(evidence), _clean(impact)
        shown = title or "(untitled)"
        if not title:
            dropped.append((shown, "no title"))
            continue
        if label is None:
            dropped.append((" ".join(line.split())[:100], "malformed: expected FINDING|severity|label|path:line|"
                                   "title|evidence|impact"))
            continue
        note = ""
        if sev not in SEVERITY_RANK:
            note, sev = f"unknown severity {sev!r} treated as low", "low"
        if loc.upper() in ("NONE", "N/A", "-"):
            loc = ""
        loc, loc_ok, loc_note = check_location(loc, repo)
        if not loc:
            dropped.append((shown, "no path:line"))
            continue
        if not loc_ok:
            dropped.append((shown, f"{loc}: {loc_note}"))
            continue
        if not evidence_ok(evidence):
            dropped.append((shown, f"evidence under {MIN_EVIDENCE_CHARS} characters"))
            continue
        if not evidence_ok(impact):
            dropped.append((shown, f"no impact path (under {MIN_EVIDENCE_CHARS} characters)"))
            continue
        kept.append(Finding(sev, loc, title, [(member, evidence)], {member}, True, note,
                            label=label, impact=[(member, impact)]))
    return kept, dropped


def parse_not_checked(text):
    return [m.group(1).strip() for m in NOT_CHECKED_RE.finditer(text) if m.group(1).strip()]


# (k) Repo text that tries to steer a reviewer. Deterministic, case-insensitive; matched
# lines become findings from the pseudo-member "injection-scan".
INJECTION_SCAN = "injection-scan"
INJECTION_RE = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions|prompts?|rules)"
    r"|(do\s+not|don'?t|never)\s+(report|flag|mention|list|raise)\s+(this|these|any|the)?\s*"
    r"(findings?|issues?|vulnerabilit\w*|bugs?|problems?)"
    r"|(reviewers?|auditors?|ai|llms?|agents?|models?)\b[^\n]{0,40}\b(should|must|are to)\s+"
    r"(skip|ignore|not\s+(review|report|flag|check))"
    r"|(mark|treat|report|consider)\s+(this|the)\s+(code|file|change|diff|pr)\s+as\s+"
    r"(safe|clean|secure|approved)"
    r"|verdict\s*(is|=|:|should\s+be|must\s+be)\s*\**\s*(clean|approve)",
    re.IGNORECASE)
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md", "AGENTS.override.md", "GEMINI.md",
                     ".cursorrules", ".github/copilot-instructions.md")
INSTRUCTION_GLOBS = (".claude/agents/*.md", ".agents/agents/*.md", ".cursor/rules/*")


def injection_candidates(repo, target_files):
    repo = Path(repo)
    names = list(dict.fromkeys(
        list(target_files) + [f for f in INSTRUCTION_FILES if (repo / f).is_file()]
        + sorted(p.relative_to(repo).as_posix() for g in INSTRUCTION_GLOBS
                 for p in repo.glob(g) if p.is_file())))
    return [n for n in names if (repo / n).is_file()]


def scan_injection(repo, files):
    """Findings for repo lines that try to steer reviewers (k). Labelled Needs
    verification: the line is real, but intent needs a human look."""
    out = []
    for rel in files:
        path = Path(repo) / rel
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            m = INJECTION_RE.search(line)
            if m:
                snippet = " ".join(line.strip().split())[:160]
                out.append(Finding(
                    "high", f"{rel}:{n}", "Repo text tries to steer reviewers",
                    [(INJECTION_SCAN, f"line matches {m.group(0)!r}: {snippet}")],
                    {INJECTION_SCAN}, True, label="Needs verification",
                    impact=[(INJECTION_SCAN, "an AI reviewer that obeys repo text could "
                                             "skip or suppress real findings")]))
    return out


def _rank_key(f):
    return (SEVERITY_RANK[f.severity], -len(f.members), f.label != "Confirmed",
            f.location, f.title)


def _merge_target(merged, f):
    exact = merged.get((f.location, normalize_title(f.title)))
    if exact is not None or not f.location:
        return exact
    for cur in merged.values():
        if cur.location == f.location and similar_titles(cur.title, f.title):
            return cur
    return None


def triage(results, repo=None, extra=()):
    """Dedupe by exact (location, normalized title), then merge same-location findings
    whose titles share most words. Rank by severity, then members agreeing, then
    Confirmed before Needs verification. Only findings that passed the evidence rule
    exist here (the rest are recorded per member in res.dropped). `extra` adds
    deterministic findings (the injection scan). Findings get ids F1..Fn."""
    merged = {}

    def add(f):
        cur = _merge_target(merged, f)
        if cur is None:
            merged[(f.location, normalize_title(f.title))] = f
            return
        cur.members |= f.members
        cur.evidence += [e for e in f.evidence if e not in cur.evidence]
        cur.impact += [i for i in f.impact if i not in cur.impact]
        if SEVERITY_RANK[f.severity] < SEVERITY_RANK[cur.severity]:
            cur.severity = f.severity
        if f.label == "Confirmed":
            cur.label = "Confirmed"

    for res in results:
        if not res.ran:
            continue
        kept, res.dropped = parse_findings(res.name, res.output, repo)
        res.not_checked = parse_not_checked(res.output)
        for f in kept:
            add(f)
    for f in extra:
        add(f)
    ranked = sorted(merged.values(), key=_rank_key)
    for i, f in enumerate(ranked):
        f.id = f"F{i + 1}"
    return ranked


VERDICT_RULES = ("BLOCK: the read-only guard failed, or a surviving finding is critical, "
                 "or high and Confirmed. CONCERNS: any other surviving finding, or no "
                 "member completed the review. CLEAN: at least one member ran, the guard "
                 "passed, and no finding survived.")


def verdict(findings, results, guard_changed):
    """(g) Deterministic BLOCK / CONCERNS / CLEAN over surviving (unrefuted) findings."""
    live = [f for f in findings if not f.refutations]
    if guard_changed:
        return "BLOCK", "read-only guard failed; results untrusted"
    blockers = [f for f in live if f.severity == "critical"
                or (f.severity == "high" and f.label == "Confirmed")]
    if blockers:
        return "BLOCK", (f"{len(blockers)} blocking finding(s): "
                         + ", ".join(f.id for f in blockers))
    if live:
        return "CONCERNS", f"{len(live)} finding(s), none blocking"
    if not any(r.ran for r in results):
        return "CONCERNS", "no member completed the review"
    return "CLEAN", "no surviving findings"


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
    if res.lens:
        lines.append(f"- lens: {res.lens}")
    if res.not_checked:
        lines.append("- not checked: " + "; ".join(res.not_checked))
    if res.dropped:
        lines += ["", "## Dropped by the evidence rule", ""]
        lines += [f"- {title} — {why}" for title, why in res.dropped]
    lines += _attempt_lines("Attempt", res.attempts)
    if refute is not None:
        lines += ["", f"# Refutation round: {refute.status}"]
        if refute.reason:
            lines.append(f"- reason: {refute.reason}")
        lines += _attempt_lines("Refutation attempt", refute.attempts)
    (out_dir / f"{res.name}.md").write_text("\n".join(lines) + "\n")


def write_summary(out_dir, meta, results, findings, guard, refute_results=None):
    changed, roadmap_changed = guard
    verdict_word, verdict_why = meta.get("verdict", ("CONCERNS", ""))
    lines = [f"# Adversarial review: {meta['description']}", "",
             f"**Verdict: {verdict_word}** — {verdict_why}", ""]
    if changed:
        lines += ["**RUN FAILED: read-only guard.** The working tree changed during the "
                  "review; treat every member result as untrusted.", ""]
    lines += [f"- date: {meta['date']}", f"- repo: {meta['repo']}",
              f"- target: `{meta['target']}`", f"- timeout per member: {meta['timeout']}s",
              f"- refutation round: {'on' if refute_results is not None else 'off'}",
              f"- injection scan: {meta.get('injection_scanned', 0)} file(s) scanned, "
              f"{meta.get('injection_hits', 0)} hit(s)",
              *([f"- security refs: STALE — {meta['security_refs']}"]
                if meta.get("security_refs") else []),
              "- read-only guard (repo): " + (
                  "FAIL — changed: " + ", ".join(f"`{p}`" for p in changed) if changed
                  else "PASS (git status unchanged)"),
              "- read-only guard (.roadmap/): " + (
                  "FAIL — changed: " + ", ".join(f"`{p}`" for p in roadmap_changed)
                  if roadmap_changed else "PASS (unchanged)"),
              f"- verdict rule: {VERDICT_RULES}",
              "", "## Members", "", "| member | status | reason | lens |", "|---|---|---|---|"]
    for res in results:
        lines.append(f"| {_cell(res.name)} | {_cell(res.status)} | {_cell(res.reason)} | "
                     f"{_cell(res.lens or '-')} |")
    if refute_results is not None:
        lines += ["", "## Refutation round", "", "| member | status | reason |", "|---|---|---|"]
        for name in sorted(refute_results):
            r = refute_results[name]
            lines.append(f"| {_cell(name)} | {_cell(r.status)} | {_cell(r.reason)} |")

    ranked = [f for f in findings if not f.refutations]
    refuted = [f for f in findings if f.refutations]
    lines += ["", "## Findings (ranked: severity, then members agreeing, then Confirmed)", ""]
    if not ranked:
        lines.append("_No findings survived._")
    else:
        lines += ["| # | id | severity | label | agree | location | title | members |",
                  "|---|---|---|---|---|---|---|---|"]
        for i, f in enumerate(ranked, 1):
            lines.append(f"| {i} | {f.id} | {f.severity} | {f.label} | {len(f.members)} | "
                         f"`{_cell(f.location)}` | {_cell(f.title)} | "
                         f"{_cell(', '.join(sorted(f.members)))} |")
        lines.append("")
        for i, f in enumerate(ranked, 1):
            lines.append(f"{i}. **[{f.label}] {f.title}** (`{f.location}`, {f.id})")
            for member, ev in f.evidence:
                lines.append(f"   - {member}: {ev}")
            for member, imp in f.impact:
                lines.append(f"   - impact ({member}): {imp}")
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
    dropped = [(r.name, t, why) for r in results for t, why in r.dropped]
    lines += ["", "## Dropped by the evidence rule (not findings)", ""]
    if not dropped:
        lines.append("_None._")
    else:
        counts = {}
        for name, _, _ in dropped:
            counts[name] = counts.get(name, 0) + 1
        lines.append("Dropped: no in-repo `path:line` whose line exists, no evidence or "
                     "impact path, or a malformed line. Per member: "
                     + ", ".join(f"{n} {c}" for n, c in sorted(counts.items()))
                     + ". Details are in each `<member>.md`.")
    lines += ["", "## Not checked (per member)", ""]
    ran = [r for r in results if r.ran]
    if not ran:
        lines.append("_No member ran._")
    for r in ran:
        lines.append(f"- {r.name}: " + ("; ".join(r.not_checked) if r.not_checked
                                         else "(member did not say)"))
    lines += ["", "## Next", "",
              "Claude triages: open each `path:line`, mark every finding confirmed / refuted / "
              "needs-info, and report. This script never fixes anything."]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def security_refs_warning():
    """One-line staleness warning when `sync-security-refs.py --check` would fail, else
    None. Never raises: the review runs with or without the secaudit plugin."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_security_refs",
                                                      SECURITY_SYNC_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        code, msg = mod.check()
        return msg if code else None
    except Exception:  # noqa: BLE001 — advisory only
        return None


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
    ap.add_argument("--security", action="store_true",
                    help="security-focused run: every member gets the security lens")
    ap.add_argument("--decided", action="append", default=[],
                    help="decided item not to re-flag (repeatable; @FILE = one per line)")
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
        target = build_target(repo, args.target, args.base)
        decided_block(args.decided)          # validate @files before anything runs
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    date = _dt.date.today().isoformat()
    out_dir = pick_out_dir(repo, args.out_dir, slugify(target.slug), date)
    try:
        out_rel = str(out_dir.resolve().relative_to(repo.resolve()))
    except ValueError:
        out_rel = None
    lenses = {m.name: lens_for(i, args.security) for i, m in enumerate(members)}
    prompts = {m.name: render_prompt(target, repo, lenses[m.name], args.decided)
               for m in members}

    before = snapshot(repo, out_rel)
    with ThreadPoolExecutor(max_workers=max(1, len(members))) as pool:
        futures = [pool.submit(run_member, m, prompts[m.name], str(repo), args.timeout)
                   for m in members]
        results = [f.result() for f in futures]
    for res in results:
        res.lens = lenses[res.name]
    scanned = injection_candidates(repo, target.files)
    injected = scan_injection(repo, scanned)
    findings = triage(results, repo, injected)
    refute_results = None
    if args.refute:
        refute_results = run_refute_round(members, results, findings, target.description,
                                          str(repo), args.timeout)
    after = snapshot(repo, out_rel)
    changed, roadmap_changed = guard_diff(before, after)

    results += [MemberResult(name, status, reason) for name, status, reason in not_run]
    for res in results:
        write_member_file(out_dir, res, (refute_results or {}).get(res.name))
    meta = {"description": target.description, "date": date, "repo": str(repo),
            "verdict": verdict(findings, results, changed),
            "injection_scanned": len(scanned), "injection_hits": len(injected),
            "target": args.target if not args.base else f"{args.target} --base {args.base}",
            "timeout": args.timeout, "security_refs": security_refs_warning()}
    write_summary(out_dir, meta, results, findings, (changed, roadmap_changed), refute_results)

    print(f"summary: {out_dir / 'summary.md'}")
    for res in results:
        print(f"  {res.name:13} {res.status}" + (f" — {res.reason}" if res.reason else ""))
    n_ref = sum(1 for f in findings if f.refutations)
    print(f"findings: {len(findings) - n_ref} ranked, {n_ref} refuted, "
          f"{sum(len(r.dropped) for r in results)} dropped by the evidence rule")
    print(f"verdict: {meta['verdict'][0]} — {meta['verdict'][1]}")
    if changed:
        print("RUN FAILED: read-only guard — changed: " + ", ".join(changed), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
