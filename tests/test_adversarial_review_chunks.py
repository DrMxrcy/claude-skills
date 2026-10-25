"""Chunked whole-repo review (plan 54): model.md baseline, chunk planner, per-chunk calls,
openusage budgeting, optional CodeGraph context, and secret redaction.

Every member CLI, `openusage` and `codegraph` is a fake executable on a private PATH
(the fake bin dir, a dir holding only a `git` symlink, /usr/bin and /bin), so no real
model, usage reader or indexer can run. --help output comes from fixtures below, trimmed
from the real CLIs' help text.
"""
import datetime as _dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills/adversarial-review/scripts"
SCRIPT = SCRIPTS / "run_review.py"
PROBE = SCRIPTS / "probe_models.py"

spec = importlib.util.spec_from_file_location("run_review_chunks", SCRIPT)
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)
cp = rr.chunk_plan
pm = rr.probe_models

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}

# --help fixtures, trimmed from each real CLI's own help text.
CODEX_HELP = """Usage: codex exec [OPTIONS] [PROMPT]
  -c, --config <key=value>
          Override a configuration value
  -m, --model <MODEL>
          Model the agent should use
  -s, --sandbox <SANDBOX_MODE>
"""
CLAUDE_HELP = """Usage: claude [options] [command] [prompt]
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --fallback-model <model>              Enable automatic fallback
  --model <model>                       Model for the current session.
"""
AGY_HELP = """Usage of agy:
  --effort                        Reasoning effort for the current CLI session (low|medium|high|xhigh|max)
  --mode                          Set the agent execution mode for this session (accept-edits, auto, plan)
  --model                         Model for the current CLI session
  -p                              Short alias for --print
"""
CURSOR_HELP = """Usage: agent [options] [command] [prompt...]
  --model <model>              Model to use (e.g., gpt-5, sonnet-4-thinking).
  --list-models                List available models and exit (default: false)
"""
OPENCODE_HELP = """opencode run [message..]
  --model, -m string      Model to use in the format provider/model#variant
  --agent string          Agent to use
"""
NO_MODEL_HELP = """Usage: agent [options]
  --mode <mode>   execution mode
  --print         print mode
"""
HELP = {"codex": CODEX_HELP, "claude": CLAUDE_HELP, "agy": AGY_HELP,
        "cursor-agent": CURSOR_HELP, "opencode": OPENCODE_HELP}

# A fake member: --version, --help (fixture), else logs the chunk id, the argv (minus
# the prompt) and the prompt, then runs BEHAVIOUR. `n` = this member's call count.
FAKE = r'''#!{python}
import os, re, sys, json
args = sys.argv[1:]
LOG = {log_dir!r}
if args == ["--version"]:
    print("{name} 9.9.9"); sys.exit(0)
if args and args[-1] == "--help":
    open(os.path.join(LOG, "{name}.help"), "a").write(" ".join(args) + "\n")
    sys.stdout.write({help!r}); sys.exit(0)
stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
prompt = stdin or (args[-1] if args else "")
m = re.search(r"This is chunk (c\d+)", prompt)
chunk = m.group(1) if m else "-"
open(os.path.join(LOG, "{name}.calls"), "a").write(chunk + "\n")
open(os.path.join(LOG, "{name}.argv"), "a").write(
    json.dumps([a for a in args if a != prompt]) + "\n")
open(os.path.join(LOG, "{name}." + chunk + ".prompt"), "w").write(prompt)
n = len(open(os.path.join(LOG, "{name}.calls")).read().split())
{behaviour}
'''


def _fake(bin_dir, name, behaviour="", help_text=None):
    path = bin_dir / name
    path.write_text(FAKE.format(python=sys.executable, name=name, log_dir=str(bin_dir),
                                help=HELP.get(name, "") if help_text is None else help_text,
                                behaviour=textwrap.dedent(behaviour)))
    path.chmod(0o755)
    return path


def _script(bin_dir, name, body):
    path = bin_dir / name
    path.write_text(f"#!{sys.executable}\nimport os, sys, json\nLOG = {str(bin_dir)!r}\n"
                    + textwrap.dedent(body))
    path.chmod(0o755)
    return path


def _reply(text, code=0, codex=False):
    if codex:
        return f"open(args[args.index('-o') + 1], 'w').write({text!r})\nsys.exit({code})"
    return f"print({text!r})\nsys.exit({code})"


OK = "NO_FINDINGS\nNOT_CHECKED|nothing skipped"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, env={**os.environ, **GIT_ENV},
                   capture_output=True)


def _calls(bin_dir, name):
    path = bin_dir / f"{name}.calls"
    return path.read_text().split() if path.is_file() else []


FILES = {
    "app.py": "def f(x):\n    return x / 0\n",
    "auth/login.py": "def login(user, password):\n    return user == 'admin'\n",
    "api/handler.py": "def handle(req):\n    return req.body\n",
    "lib/util.py": "def add(a, b):\n    return a - b\n",
    "docs/guide.md": "# Guide\nRun the thing.\n",
}
# Risk order: changed (app.py at root), then security paths (api, auth), then the rest.
ORDER = ["(root)", "api", "auth", "docs", "lib"]


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "init")
    (repo / "app.py").write_text("def f(x):\n    return x / 0  # changed\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_bin = tmp_path / "gitbin"            # only git: no real member CLI can be found
    git_bin.mkdir()
    (git_bin / "git").symlink_to(shutil.which("git"))
    home = tmp_path / "home"
    home.mkdir()
    run_env = {**os.environ, "HOME": str(home),
               "PATH": os.pathsep.join([str(bin_dir), str(git_bin), "/usr/bin", "/bin"])}

    def run(*args, script=SCRIPT, repo_arg=True):
        extra = ["--repo", str(repo)] if repo_arg else []
        return subprocess.run([sys.executable, str(script), *args, *extra], cwd=repo,
                              env=run_env, capture_output=True, text=True)

    return repo, bin_dir, run


def _run_dir(repo):
    found = sorted(repo.glob(".roadmap/notes/review-*-repo*/summary.md"))
    assert found, "no summary.md written"
    return found[-1].parent


def _summary(repo):
    d = _run_dir(repo)
    return (d / "summary.md").read_text(), d


# --- step 1: model.md baseline --------------------------------------------------------

def test_help_flag_parsing_on_real_help_fixtures():
    assert pm.flag_in_help(CODEX_HELP, "-m") and pm.flag_in_help(CODEX_HELP, "--model")
    assert not pm.flag_in_help(CODEX_HELP, "--effort")
    assert pm.flag_in_help(CLAUDE_HELP, "--model") and pm.flag_in_help(CLAUDE_HELP, "--effort")
    assert pm.flag_in_help(AGY_HELP, "--effort") and pm.flag_in_help(AGY_HELP, "--model")
    assert pm.flag_in_help(OPENCODE_HELP, "-m")
    assert not pm.flag_in_help(CURSOR_HELP, "-m")            # not inside --model/--mode
    assert not pm.flag_in_help(NO_MODEL_HELP, "--model")    # --mode is not --model
    assert pm.SPECS["codex"].help_args == ("exec", "--help")
    assert pm.SPECS["opencode"].help_args == ("run", "--help")


def test_probe_models_writes_model_md_without_calling_a_model(env, tmp_path):
    repo, bin_dir, run = env
    for name in ("codex", "claude", "agy", "opencode"):
        _fake(bin_dir, name, _reply(OK))
    out = tmp_path / "model.md"
    res = run("--out", str(out), "--members", "codex,claude,agy,opencode,cursor-agent",
              script=PROBE, repo_arg=False)
    assert res.returncode == 0, res.stderr
    entries, refused = pm.read_model_md(out)
    today = _dt.date.today().isoformat()
    assert set(entries) == {"codex", "claude", "agy", "opencode"}
    for e in entries.values():
        assert e["version"].endswith("9.9.9") and e["probed"] == today
    assert (entries["codex"]["model_flag"], entries["codex"]["effort_flag"]) == ("-m", "none")
    assert (entries["claude"]["model_flag"], entries["claude"]["effort_flag"]) == \
        ("--model", "--effort")
    assert entries["opencode"]["model"] == rr.OPENCODE_PRIMARY_MODEL
    assert entries["opencode"]["fallback"] == rr.OPENCODE_FALLBACK_MODEL
    assert refused["cursor-agent"].startswith("not installed")
    assert (bin_dir / "codex.help").read_text() == "exec --help\n"
    assert (bin_dir / "opencode.help").read_text() == "run --help\n"
    assert not list(bin_dir.glob("*.calls")), "a probe must never call a model"


def test_model_md_digest_rejects_hand_edit(tmp_path):
    entry = {"member": "agy", "model_flag": "--model", "model": "cli-default", "fallback": "-",
             "effort_flag": "--effort", "effort": "cli-default", "version": "agy 1",
             "probed": "2026-10-25", "note": ""}
    text = pm.render_model_md({"agy": entry}, {"kimi": "not installed"}, "2026-10-25")
    entries, refused = pm.parse_model_md(text)
    assert entries["agy"]["effort_flag"] == "--effort" and "kimi" in refused
    with pytest.raises(ValueError, match="hand-edited"):
        pm.parse_model_md(text.replace("cli-default", "gpt-guess", 1))
    with pytest.raises(ValueError, match="no digest"):
        pm.parse_model_md(text.split(pm.DIGEST_PREFIX)[0])


def test_pinned_effort_needs_its_flag_in_help(env):
    repo, bin_dir, _ = env
    _fake(bin_dir, "cursor-agent", _reply(OK))
    spec_ = pm.specs_for(["cursor-agent"], pins={("cursor-agent", "effort"): "high"})[0]
    entry, why = pm.probe_member(spec_, env={"PATH": str(bin_dir)})
    assert entry is None and "no effort flag" in why


def test_missing_model_md_entry_is_refused_not_run(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(OK))
    _fake(bin_dir, "cursor-agent", _reply(OK), help_text=NO_MODEL_HELP)
    res = run("repo", "--members", "agy,cursor-agent", "--no-preflight")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    row = [ln for ln in summary.splitlines() if ln.startswith("| cursor-agent |")][0]
    assert "skipped: no model.md entry" in row and "no model flag" in row
    assert _calls(bin_dir, "cursor-agent") == [], "refused member must never be called"
    entries, refused = pm.read_model_md(run_dir / "model.md")
    assert "agy" in entries and "cursor-agent" in refused
    assert "## Model baseline (model.md)" in summary and "cursor-agent: no entry, refused" in summary


def test_hand_edited_model_md_stops_the_run(env, tmp_path):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(OK))
    out = tmp_path / "model.md"
    assert run("--out", str(out), "--members", "agy", script=PROBE,
               repo_arg=False).returncode == 0
    out.write_text(out.read_text().replace("cli-default", "guessed-model", 1))
    res = run("repo", "--members", "agy", "--model-md", str(out), "--no-preflight")
    assert res.returncode == 1 and "hand-edited" in res.stderr
    assert _calls(bin_dir, "agy") == []


def test_pinned_model_and_effort_come_from_model_md(env, tmp_path):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(OK))
    out = tmp_path / "model.md"
    res = run("--out", str(out), "--members", "agy", "--pin", "agy:model=gemini-pro-x",
              "--pin", "agy:effort=high", script=PROBE, repo_arg=False)
    assert res.returncode == 0, res.stderr
    res = run("repo", "--members", "agy", "--model-md", str(out), "--no-preflight")
    assert res.returncode == 0, res.stderr
    argvs = [json.loads(ln) for ln in (bin_dir / "agy.argv").read_text().splitlines()]
    assert len(argvs) == len(ORDER)
    for argv in argvs:
        assert argv[:2] == ["--mode", "plan"] and argv[-1] == "-p"
        assert "--model" in argv and argv[argv.index("--model") + 1] == "gemini-pro-x"
        assert argv[argv.index("--effort") + 1] == "high"


# --- step 2: chunk planner ---------------------------------------------------------------

def test_plan_chunks_budget_split_and_oversize():
    sizes = {"src/a/x.py": 400, "src/a/y.py": 400, "src/b/z.py": 400, "big/huge.py": 4000,
             "README.md": 40, "setup.py": 40}
    chunks = cp.plan_chunks(sizes, budget=250)
    by_label = {c["label"]: c for c in chunks}
    assert by_label["(root)"]["files"] == ["README.md", "setup.py"]
    assert by_label["big"]["oversized"] and by_label["big"]["tokens"] == 1000
    src = [c for c in chunks if c["module"] == "src"]
    assert [c["files"] for c in src] == [["src/a/x.py", "src/a/y.py"], ["src/b/z.py"]]
    assert all(c["tokens"] <= 250 for c in src)
    assert all(c["label"].startswith("src (part ") for c in src)
    assert [c["id"] for c in chunks] == [f"c{i:02d}" for i in range(1, len(chunks) + 1)]
    assert cp.estimate_tokens(9) == 3 and cp.estimate_tokens(0) == 1
    with pytest.raises(ValueError):
        cp.plan_chunks(sizes, budget=0)


def test_risk_order_changed_then_security_then_rest():
    sizes = {"zeta/a.py": 10, "lib/payments/charge.py": 10, "web/middleware.py": 10,
             "core/x.py": 10, "docs/rapid.md": 10, "server/webhooks.py": 10}
    chunks = cp.plan_chunks(sizes, 1000, changed={"zeta/a.py"})
    assert [c["module"] for c in chunks] == ["zeta", "lib", "server", "web", "core", "docs"]
    assert [c["risk"] for c in chunks] == ["changed", "security", "security", "security",
                                           "normal", "normal"]
    assert not cp.is_security_path("docs/rapid.md")          # "api" only as a token prefix
    assert cp.is_security_path("src/AuthService.ts") and cp.is_security_path("api/v1.py")


def test_plannable_files_skip_denied_binary_and_codegraph(tmp_path):
    (tmp_path / ".codegraph").mkdir()
    (tmp_path / ".codegraph/db.sqlite").write_bytes(b"x")
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0\0")
    (tmp_path / "ok.py").write_text("x = 1\n")
    sizes, skipped = cp.plannable_files(tmp_path, [".codegraph/db.sqlite", ".env", "logo.png",
                                                   "ok.py", "gone.py"],
                                        rr.is_denied, rr.DEFAULT_DENY, 10_000)
    assert sizes == {"ok.py": 6}
    assert dict(skipped) == {".env": "deny list (.env*)", "logo.png": "binary"}


def test_coverage_roundtrip_mark_and_todo(tmp_path):
    chunks = cp.plan_chunks({"a/x.py": 10, "b/y.py": 10}, 100)
    cov = cp.new_coverage(chunks, 100, [("logo.png", "binary")], created="2026-10-25")
    cp.mark(cov, "c01", "agy", "ran")
    cp.mark(cov, "c02", "agy", "skipped: usage limit")
    cp.save_coverage(tmp_path, cov)
    back = cp.load_coverage(tmp_path)
    assert back["chunks"][0]["members_done"] == ["agy"]
    assert back["chunks"][1]["status"] == {"agy": "skipped: usage limit"}
    assert [c["id"] for c in cp.todo_for(back, "agy")] == ["c02"]
    assert [c["id"] for c in cp.todo_for(back, "claude")] == ["c01", "c02"]
    assert cp.reviewed_count(back, "agy") == 1
    (tmp_path / "coverage.json").write_text("{}")
    with pytest.raises(ValueError):
        cp.load_coverage(tmp_path)
    with pytest.raises(ValueError):
        cp.load_coverage(tmp_path / "missing")


# --- step 3: per-chunk member calls --------------------------------------------------

F_LIB = ("FINDING|high|Confirmed|lib/util.py:2|add subtracts|def add(a, b): return a - b|"
         "every caller of add gets the wrong sum")


def test_repo_run_one_call_per_chunk_with_results_and_coverage(env):
    repo, bin_dir, run = env
    found = ("import re\nif 'lib/util.py' in prompt and 'chunk c05' in prompt:\n"
             f"    print({F_LIB!r})\nprint({OK!r})\nsys.exit(0)")
    _fake(bin_dir, "agy", found)
    _fake(bin_dir, "claude", _reply(OK))
    res = run("repo", "--members", "agy,claude", "--no-preflight", "--chunk-budget", "1000")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    cov = json.loads((run_dir / "coverage.json").read_text())
    assert [c["module"] for c in cov["chunks"]] == ORDER
    ids = [c["id"] for c in cov["chunks"]]
    for name in ("agy", "claude"):
        assert _calls(bin_dir, name) == ids, name         # one call per chunk, risk order
        for cid in ids:
            rec = json.loads((run_dir / "chunks" / cid / f"{name}.json").read_text())
            assert rec["status"] == "ran" and (run_dir / "chunks" / cid / f"{name}.md").is_file()
        assert f"- {name}: chunks reviewed 5/5" in summary
    assert all(sorted(c["members_done"]) == ["agy", "claude"] for c in cov["chunks"])
    assert "`lib/util.py:2` | add subtracts | agy" in summary
    prompt = (bin_dir / "agy.c05.prompt").read_text()
    assert "This is chunk c05 of 5 (`lib`" in prompt and "return a - b" in prompt
    assert "def login" not in prompt, "a chunk prompt holds only its own files"
    assert "## Chunk scope" in rr.PROMPT_FILE.read_text().replace("{{CHUNK}}", rr.chunk_block(
        cov["chunks"][0], 5))


def test_rate_limit_on_third_chunk_then_resume_skips_finished(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", "if n == 3:\n    print('Error: rate limit exceeded, retry later')\n"
                          "    sys.exit(1)\n" + _reply(OK))
    res = run("repo", "--members", "agy", "--no-preflight")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    ids = [c["id"] for c in json.loads((run_dir / "coverage.json").read_text())["chunks"]]
    assert _calls(bin_dir, "agy") == ids[:3]
    assert "- agy: chunks reviewed 2/5" in summary and f"usage limit on {ids[2]}" in summary
    assert "ran (partial: 2/5 chunks)" in summary and "--resume" in summary
    cov = json.loads((run_dir / "coverage.json").read_text())
    assert [c["members_done"] for c in cov["chunks"]] == [["agy"], ["agy"], [], [], []]
    assert cov["chunks"][2]["status"]["agy"] == "skipped: usage limit"

    res = run("--resume", str(run_dir), "--members", "agy", "--no-preflight")
    assert res.returncode == 0, res.stderr
    assert _calls(bin_dir, "agy") == ids[:3] + ids[2:], "finished chunks must not be re-sent"
    summary = (run_dir / "summary.md").read_text()
    assert "- agy: chunks reviewed 5/5" in summary
    assert "| agy | ran |" in summary
    assert "coverage incomplete" not in summary
    assert len(list((run_dir / "chunks").glob("*/agy.json"))) == 5


def test_resume_without_coverage_is_an_error(env, tmp_path):
    repo, bin_dir, run = env
    res = run("--resume", str(tmp_path), "--members", "agy", "--no-preflight")
    assert res.returncode == 1 and "coverage.json" in res.stderr
    res = run("plan:7", "--resume", str(tmp_path))
    assert res.returncode == 1


def test_chunk_runs_keep_the_live_guard(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", f"open({str(repo / 'pwned.txt')!r}, 'w').write('x')\n" + _reply(OK))
    res = run("repo", "--members", "agy", "--no-preflight")
    assert res.returncode == 2
    summary, _ = _summary(repo)
    assert "**Verdict: BLOCK**" in summary and "`pwned.txt`" in summary


# --- step 4: openusage budgeting ---------------------------------------------------------

def _openusage(bin_dir, remaining_expr):
    """Fake openusage: codex session window from a Python expression over `reads`."""
    _script(bin_dir, "openusage", f"""
        p = os.path.join(LOG, "openusage.reads")
        reads = int(open(p).read()) if os.path.exists(p) else 0
        open(p, "w").write(str(reads + 1))
        print(json.dumps({{"account": "someone@example.com", "providers": {{"codex": {{
            "email": "someone@example.com", "resources": {{
                "session": {{"remaining": {remaining_expr}, "resetsAt": "2026-10-26T00:00Z"}},
                "weekly": {{"remaining": 80, "resetsAt": "2026-11-01T00:00Z"}}}}}}}}}}))
    """)


def test_openusage_low_window_plans_fewer_calls_and_records_floor(env):
    repo, bin_dir, run = env
    _openusage(bin_dir, "15")
    _fake(bin_dir, "codex", _reply(OK, codex=True))
    _fake(bin_dir, "agy", _reply(OK))                     # no openusage mapping: all chunks
    res = run("repo", "--members", "codex,agy", "--usage-floor", "10", "--chunk-cost", "2")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    assert len(_calls(bin_dir, "codex")) == 2 and len(_calls(bin_dir, "agy")) == 5
    assert "floor 10%" in summary and "planned 2 of 5 call(s)" in summary
    assert "- codex: chunks reviewed 2/5; planned 2 call(s) (openusage)" in summary
    assert "usage floor 10%" in summary
    assert "- agy: chunks reviewed 5/5" in summary and "planned from --chunk-budget" in summary
    assert "@example.com" not in summary and "someone" not in summary
    cov = json.loads((run_dir / "coverage.json").read_text())
    assert cov["members"]["codex"]["planned"] == 2
    assert "usage floor" in cov["members"]["codex"]["stopped"]


def test_openusage_live_reading_stops_member_at_floor(env):
    repo, bin_dir, run = env
    _openusage(bin_dir, "30 if reads == 0 else 12")     # one call costs 18% here
    _fake(bin_dir, "codex", _reply(OK, codex=True))
    res = run("repo", "--members", "codex", "--usage-floor", "10", "--chunk-cost", "2")
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert len(_calls(bin_dir, "codex")) == 1
    assert "openusage shows 12% remaining after 1 call(s)" in summary
    assert "- codex: chunks reviewed 1/5" in summary


def test_without_openusage_plans_from_chunk_budget_and_says_so(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "codex", _reply(OK, codex=True))
    res = run("repo", "--members", "codex", "--chunk-budget", "5000")
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert len(_calls(bin_dir, "codex")) == 5
    assert "openusage not installed" in summary
    assert "chunk calls planned from --chunk-budget alone (5 chunk(s) of up to 5000 tokens" \
        in summary


def test_plan_calls_and_usage_remaining_units():
    assert cp.plan_calls(None, 10, 2, 7) == 7
    assert cp.plan_calls(15, 10, 2, 7) == 2 and cp.plan_calls(9, 10, 2, 7) == 0
    assert cp.plan_calls(100, 10, 2, 7) == 7
    data = {"providers": {"antigravity": {"resources": {
        "geminiSession": {"remaining": 40}, "nonGeminiSession": {"remaining": 5},
        "geminiWeekly": {"remaining": 20}, "nonGeminiWeekly": {"remaining": 70}}},
        "claude-a": {"resources": {"weekly": {"remaining": 3}}},
        "claude-b": {"resources": {"weekly": {"remaining": 60}}},
        "codex": {"stale": True, "resources": {"session": {"remaining": 50}}}}}
    assert rr.usage_remaining("agy", data)[0] == 40       # best of each group, tightest group
    assert rr.usage_remaining("claude", data) == (60, "claude-b.weekly")
    assert rr.usage_remaining("codex", data)[0] is None
    assert rr.usage_remaining("opencode", data)[0] is None


# --- step 5: optional CodeGraph context -------------------------------------------------

AWS = "AKIAQWERTYUIOPASDFGH"


def _codegraph(bin_dir, code=0, extra=""):
    _script(bin_dir, "codegraph", f"""
        open(os.path.join(LOG, "codegraph.calls"), "a").write(json.dumps(sys.argv[1:]) + "\\n")
        print("CODEGRAPH-CONTEXT symbols and call paths for " + " ".join(sys.argv[6:]))
        print("aws_key = '{AWS}'{extra}")
        sys.exit({code})
    """)


def _cg_calls(bin_dir):
    path = bin_dir / "codegraph.calls"
    return [json.loads(ln) for ln in path.read_text().splitlines()] if path.is_file() else []


def test_codegraph_context_when_index_exists_and_init_never_runs(env):
    repo, bin_dir, run = env
    (repo / ".codegraph").mkdir()
    (repo / ".codegraph/graph.db").write_bytes(b"\0index")
    _codegraph(bin_dir)
    _fake(bin_dir, "agy", _reply(OK))
    _fake(bin_dir, "claude", _reply(OK))
    res = run("repo", "--members", "agy,claude", "--no-preflight")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    calls = _cg_calls(bin_dir)
    assert len(calls) == 5, "one codegraph explore per chunk, shared by members"
    for argv in calls:
        assert argv[0] == "explore" and argv[1:3] == ["-p", str(repo)]
        assert "init" not in argv and "index" not in argv
    cov = json.loads((run_dir / "coverage.json").read_text())
    assert {c["context"] for c in cov["chunks"]} == {"codegraph explore"}
    assert ".codegraph" not in {c["module"] for c in cov["chunks"]}
    prompt = (bin_dir / "agy.c03.prompt").read_text()
    assert "CODEGRAPH-CONTEXT" in prompt and "codegraph explore, secret-redacted" in prompt
    assert AWS not in prompt and "[REDACTED:" in prompt
    assert "- context: codegraph explore" in summary
    assert "`codegraph output` (" in summary


def test_raw_files_without_index_and_codegraph_not_called(env):
    repo, bin_dir, run = env
    _codegraph(bin_dir)
    _fake(bin_dir, "agy", _reply(OK))
    res = run("repo", "--members", "agy", "--no-preflight")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    assert _cg_calls(bin_dir) == []
    cov = json.loads((run_dir / "coverage.json").read_text())
    assert {c["context"] for c in cov["chunks"]} == {"raw files (no .codegraph/ index)"}
    assert "Chunk files (raw, secret-redacted)" in (bin_dir / "agy.c01.prompt").read_text()
    assert "- context: raw files (no .codegraph/ index)" in summary


def test_codegraph_failure_or_denied_path_falls_back_to_raw(env):
    repo, bin_dir, run = env
    (repo / ".codegraph").mkdir()
    _codegraph(bin_dir, code=1)
    note = cp.codegraph_context(repo, ["app.py"], env={"PATH": str(bin_dir)})[1]
    assert note == "raw files (codegraph explore exit 1)"
    _codegraph(bin_dir, extra="\\nsee config/prod.pem and .env.local")
    text, note = cp.codegraph_context(repo, ["app.py"], env={"PATH": str(bin_dir)},
                                      is_denied=rr.is_denied, deny=rr.DEFAULT_DENY)
    assert text is None and "deny-listed" in note and "config/prod.pem" in note
    assert all("init" not in argv for argv in _cg_calls(bin_dir))
    assert cp.codegraph_argv("cg", repo, ["a.py"])[1] == "explore"


# --- step 6: privacy redaction ------------------------------------------------------------

GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
PEM = ("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAzQ7Hn3x9fakefakefake\n"
       "q9w8e7r6t5y4u3i2o1p0\n-----END RSA PRIVATE KEY-----")
GENERIC = "Zx9qL2mP8vR4tY7wK3nB6cH1"
SECRETS = (AWS, GH, "MIIEowIBAAKCAQEAzQ7Hn3x9fakefakefake", GENERIC)
PLANTED = (f"AWS_ACCESS_KEY_ID = '{AWS}'\nGITHUB = '{GH}'\nPEM = '''{PEM}'''\n"
           f"API_SECRET = \"{GENERIC}\"\ndef keep():\n    return 'visible-marker'\n")


def test_redact_text_patterns_and_negatives():
    out, counts = rr.redact_text(PLANTED)
    for s in SECRETS:
        assert s not in out, s
    assert counts == {"aws-access-key": 1, "github-token": 1, "private-key-block": 1,
                      "secret-assignment": 1}
    assert "API_SECRET = \"[REDACTED:secret-assignment]\"" in out and "visible-marker" in out
    for benign in ("token = get_token_from_header(request)",
                   "password_field = 'confirm_password_input'", "API_KEY=sk-fake-123",
                   "AUTH_HEADER = 'X-Authorization-Header'", "monkey = 12345"):
        assert rr.redact_text(benign) == (benign, {}), benign


def test_planted_secret_redacted_from_every_chunk_and_file_lists_in_summary(env):
    repo, bin_dir, run = env
    (repo / "lib/config.py").write_text(PLANTED)
    git(repo, "add", "lib/config.py")
    git(repo, "commit", "-qm", "config")
    dump = ("for root, _, names in os.walk('.'):\n"
            "    for nm in names:\n"
            "        open(os.path.join(LOG, 'agy.snapshot'), 'a').write(\n"
            "            open(os.path.join(root, nm), errors='replace').read())\n")
    _fake(bin_dir, "agy", dump + _reply(OK))
    res = run("repo", "--members", "agy", "--no-preflight")
    assert res.returncode == 0, res.stderr
    summary, run_dir = _summary(repo)
    sent = "".join(p.read_text() for p in bin_dir.glob("agy.*.prompt"))
    sent += (bin_dir / "agy.snapshot").read_text()
    assert "visible-marker" in sent and "[REDACTED:aws-access-key]" in sent
    stored = summary + "".join(p.read_text() for p in run_dir.rglob("*") if p.is_file())
    for s in SECRETS:
        assert s not in sent, s
        assert s not in stored, s
    assert "## Chunks (egress: the files each chunk sends)" in summary
    assert "- files: `lib/config.py`, `lib/util.py`" in summary
    assert "- files: `auth/login.py`" in summary
    assert ("- redacted: `lib/config.py` (aws-access-key ×1, github-token ×1, "
            "private-key-block ×1, secret-assignment ×1)") in summary


def test_redaction_applies_to_diff_target_too(env):
    repo, bin_dir, run = env
    (repo / "lib/util.py").write_text(f"TOKEN = '{GH}'\ndef add(a, b):\n    return a + b\n")
    dump = ("open(os.path.join(LOG, 'agy.snapshot'), 'w').write("
            "open('lib/util.py').read())\n")
    _fake(bin_dir, "agy", dump + _reply(OK))
    res = run("diff", "--members", "agy", "--no-preflight")
    assert res.returncode == 0, res.stderr
    found = sorted(repo.glob(".roadmap/notes/review-*-diff/summary.md"))
    summary = found[-1].read_text()
    prompt = (bin_dir / "agy.-.prompt").read_text()
    assert "return a + b" in prompt and GH not in prompt and "[REDACTED:github-token]" in prompt
    assert GH not in (bin_dir / "agy.snapshot").read_text()
    assert "secrets redacted before sending: `prompt context` (github-token ×1)" in summary
    assert "`lib/util.py` (github-token ×1)" in summary
    assert "## Egress (files in the member snapshot)" in summary and "- `lib/util.py`" in summary
    assert GH not in summary


def test_refute_round_runs_over_reviewed_chunks(env):
    repo, bin_dir, run = env
    found = (f"if 'chunk c05' in prompt:\n    print({F_LIB!r})\n"
             "if 'This is chunk' not in prompt:\n    print('UPHOLD|F1|cannot disprove it')\n"
             f"print({OK!r})\nsys.exit(0)")
    _fake(bin_dir, "agy", found)
    _fake(bin_dir, "claude", "if 'This is chunk' not in prompt:\n"
                             "    print('UPHOLD|F1|looks real to me')\n" + _reply(OK))
    res = run("repo", "--members", "agy,claude", "--no-preflight", "--refute")
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert "## Refutation round" in summary and "`lib/util.py:2` | add subtracts" in summary
    assert _calls(bin_dir, "claude").count("-") == 1          # one refute call, fresh process
    assert "-" not in _calls(bin_dir, "agy"), "agy has nothing to refute"
