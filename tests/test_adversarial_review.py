"""Coverage for skills/adversarial-review/scripts/run_review.py.

Every member CLI is a fake executable on a private PATH, so no real model is called.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills/adversarial-review/scripts/run_review.py"

spec = importlib.util.spec_from_file_location("run_review", SCRIPT)
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}

# A fake CLI: answers --version, records its argv, then behaves per BEHAVIOUR.
FAKE = """#!{python}
import os, sys, time
args = sys.argv[1:]
if args == ["--version"]:
    print("{name} 9.9.9"); sys.exit(0)
log = os.path.join({log_dir!r}, "{name}.calls")
with open(log, "a") as fh:
    fh.write(" ".join(a.replace(chr(10), " ") for a in args) + chr(10))
stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
{behaviour}
"""


def _fake(bin_dir, name, behaviour):
    path = bin_dir / name
    path.write_text(FAKE.format(python=sys.executable, name=name, log_dir=str(bin_dir),
                                behaviour=textwrap.dedent(behaviour)))
    path.chmod(0o755)
    return path


def _reply(text, code=0, codex=False):
    """Behaviour that prints text (or writes it to codex's -o file) and exits."""
    if codex:
        return f"open(args[args.index('-o') + 1], 'w').write({text!r})\nsys.exit({code})"
    return f"print({text!r})\nsys.exit({code})"


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def f(x):\n    return x / 0\n")
    plans = repo / ".roadmap/plans"
    plans.mkdir(parents=True)
    (plans / "007-thing.md").write_text("---\nid: 7\nversion: 1.2.0\n---\n# Plan 7\n- [x] Step 1\n")
    git_env = {**os.environ, **GIT_ENV}
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "init"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, env=git_env)
    (repo / "app.py").write_text("def f(x):\n    return x / 0  # changed\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_dir = os.path.dirname(shutil.which("git"))
    run_env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{git_dir}{os.pathsep}/usr/bin:/bin"}

    def run(*args):
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(repo)],
                              cwd=repo, env=run_env, capture_output=True, text=True)

    return repo, bin_dir, run


def _summary(repo):
    found = sorted(repo.glob(".roadmap/notes/review-*/summary.md"))
    assert found, "no summary.md written"
    return found[-1].read_text(), found[-1].parent


def _row(summary, member):
    rows = [ln for ln in summary.splitlines() if ln.startswith(f"| {member} |")]
    assert rows, f"no status row for {member}:\n{summary}"
    return rows[0]


F_A = "FINDING|high|app.py:2|Division by zero|return x / 0 always raises"


def test_parallel_run_writes_member_files_and_status_table(env):
    repo, bin_dir, run = env
    sleepy = "time.sleep(1)\n"
    _fake(bin_dir, "codex", sleepy + _reply(f"review\n{F_A}", codex=True))
    _fake(bin_dir, "claude", sleepy + _reply(f"review\n{F_A}"))
    _fake(bin_dir, "agy", sleepy + _reply("FINDING|low|NONE|vague worry|NONE"))
    start = time.monotonic()
    res = run("--members", "codex,claude,agy,kimi")
    elapsed = time.monotonic() - start
    assert res.returncode == 0, res.stderr
    assert elapsed < 2.8, f"members did not run in parallel ({elapsed:.1f}s)"
    summary, out_dir = _summary(repo)
    for m in ("codex", "claude", "agy"):
        assert (out_dir / f"{m}.md").is_file()
        assert "| ran |" in _row(summary, m)
    assert "skipped: excluded" in _row(summary, "kimi")
    assert (out_dir / "kimi.md").is_file()
    # claude and codex get the prompt on stdin; read-only flags are on the argv.
    assert "-s read-only" in (bin_dir / "codex.calls").read_text()
    assert "--tools Read,Grep,Glob" in (bin_dir / "claude.calls").read_text()
    assert (bin_dir / "agy.calls").read_text().startswith("--mode plan -p ")
    assert "read-only guard (repo): PASS" in summary
    # without --refute there is exactly one call per member
    for m in ("codex", "claude", "agy"):
        assert len((bin_dir / f"{m}.calls").read_text().splitlines()) == 1
    assert "## Refutation round" not in summary


def test_usage_limit_skips_member_without_aborting_others(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "claude", _reply("Error: You've hit your usage limit. Try again at 5pm.", 1))
    _fake(bin_dir, "agy", _reply(F_A))
    _fake(bin_dir, "cursor-agent", _reply("boom: segfault", 3))
    res = run("--members", "claude,agy,cursor-agent")
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert "| skipped: usage limit |" in _row(summary, "claude")
    assert "| ran |" in _row(summary, "agy")
    assert "| failed: exit 3 |" in _row(summary, "cursor-agent")
    assert "Division by zero" in summary


def test_timeout_marks_member_failed(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "claude", "time.sleep(30)")
    _fake(bin_dir, "agy", _reply(F_A))
    start = time.monotonic()
    res = run("--members", "claude,agy", "--timeout", "1")
    assert time.monotonic() - start < 10
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert "failed: timeout after 1s" in _row(summary, "claude")
    assert "| ran |" in _row(summary, "agy")


def test_read_only_guard_fails_run_when_member_writes(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", "open('pwned.txt', 'w').write('hi')\n" + _reply(F_A))
    _fake(bin_dir, "claude", "open('.roadmap/plans/007-thing.md', 'a').write('x')\n" + _reply(F_A))
    res = run("--members", "agy,claude")
    assert res.returncode == 2
    assert "read-only guard" in res.stderr
    summary, _ = _summary(repo)
    assert "RUN FAILED: read-only guard" in summary
    assert "`pwned.txt`" in summary
    assert "read-only guard (.roadmap/): FAIL" in summary


def test_guard_ignores_its_own_output_dir(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(F_A))
    res = run("--members", "agy")
    assert res.returncode == 0, res.stderr
    summary, _ = _summary(repo)
    assert "read-only guard (repo): PASS" in summary


def test_uninstalled_member_is_skipped(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(F_A))
    res = run("--members", "agy,cursor-agent")
    assert res.returncode == 0, res.stderr
    summary, out_dir = _summary(repo)
    assert "| skipped: not installed |" in _row(summary, "cursor-agent")
    assert (out_dir / "cursor-agent.md").is_file()


def test_opencode_falls_back_once_after_usage_limit(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "opencode", f"""
open(os.path.join(os.path.dirname(log), "oc.env"), "w").write(
    os.environ.get("OPENCODE_CONFIG_CONTENT", ""))
if "{rr.OPENCODE_PRIMARY_MODEL}" in args:
    print("429 Too Many Requests: rate limit reached"); sys.exit(1)
print({F_A!r})
""")
    res = run("--members", "opencode")
    assert res.returncode == 0, res.stderr
    calls = (bin_dir / "opencode.calls").read_text().splitlines()
    assert len(calls) == 2
    assert f"-m {rr.OPENCODE_PRIMARY_MODEL} --agent plan" in calls[0]
    assert f"-m {rr.OPENCODE_FALLBACK_MODEL} --agent plan" in calls[1]
    assert all(c.startswith("run --standalone -m ") for c in calls)
    env_seen = (bin_dir / "oc.env").read_text()
    assert env_seen == rr.OPENCODE_READONLY_CONFIG
    assert '"action":"*","resource":"*","effect":"deny"' in env_seen
    summary, out_dir = _summary(repo)
    assert (f"| ran (fallback: free, after usage limit on {rr.OPENCODE_PRIMARY_MODEL}) |"
            in _row(summary, "opencode"))
    assert "Division by zero" in summary
    assert "## Attempt 2" in (out_dir / "opencode.md").read_text()


def test_opencode_fallback_also_limited_is_skipped_without_cascade(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "opencode", _reply("quota exceeded", 1))
    res = run("--members", "opencode")
    assert res.returncode == 0, res.stderr
    assert len((bin_dir / "opencode.calls").read_text().splitlines()) == 2
    summary, _ = _summary(repo)
    assert "| skipped: usage limit |" in _row(summary, "opencode")


def test_opencode_primary_success_does_not_retry(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "opencode", _reply(F_A))
    assert run("--members", "opencode").returncode == 0
    assert len((bin_dir / "opencode.calls").read_text().splitlines()) == 1


def test_findings_parse_dedupe_and_rank(tmp_path):
    (tmp_path / "a.py").write_text("x\n" * 50)
    (tmp_path / "b.py").write_text("y\n" * 50)
    texts = {
        "m1": "prose\nFINDING|medium|a.py:10|Leaky handle|open() never closed\n"
              "FINDING|critical|b.py:3|Shell injection|shell=True with user input\n"
              "FINDING|critical|NONE|Everything is insecure|NONE\n",
        "m2": "- FINDING|high|./a.py:10|Leaky  handle!|fd leak on error path\n"
              "FINDING|low|missing.py:1|Ghost file|made up\n",
        "m3": "FINDING|medium|a.py:10|leaky handle|same\nFINDING|low|NONE|no findings|NONE\n",
    }
    results = [rr.MemberResult(n, "ran", "", attempts=[rr.Attempt("ran", "", t, 0, 0.1, [])])
               for n, t in texts.items()]
    results.append(rr.MemberResult("m4", "skipped: usage limit", "",
                                   attempts=[rr.Attempt("skipped: usage limit", "",
                                                        "FINDING|critical|a.py:1|x|y", 1, 0, [])]))
    ranked = rr.triage(results, tmp_path)
    titles = [(f.severity, f.location, len(f.members), f.evidenced) for f in ranked]
    assert titles[0] == ("critical", "b.py:3", 1, True)
    # merged across 3 members, severity raised to the max reported (high)
    assert titles[1] == ("high", "a.py:10", 3, True)
    # evidence-free and nonexistent-path findings rank below every evidenced one
    assert [t[3] for t in titles] == [True, True, False, False]
    unconfirmed = {f.title: f for f in ranked if not f.evidenced}
    assert unconfirmed["Everything is insecure"].severity == "critical"
    assert unconfirmed["Ghost file"].note == "path not found in repo"
    assert not any("no findings" in f.title for f in ranked)
    assert not any(f.location == "a.py:1" for f in ranked), "skipped member's output was used"


def test_agreement_breaks_severity_ties(tmp_path):
    (tmp_path / "a.py").write_text("x\n" * 50)
    results = [
        rr.MemberResult("m1", "ran", "", attempts=[rr.Attempt(
            "ran", "", "FINDING|high|a.py:1|Solo|e1\nFINDING|high|a.py:2|Shared|e2", 0, 0, [])]),
        rr.MemberResult("m2", "ran", "", attempts=[rr.Attempt(
            "ran", "", "FINDING|high|a.py:2|shared|e3", 0, 0, [])]),
    ]
    ranked = rr.triage(results, tmp_path)
    assert [f.title for f in ranked] == ["Shared", "Solo"]
    assert len(ranked[0].evidence) == 2


def test_classify_requires_nonzero_exit_for_usage_limit():
    assert rr.classify(0, "rate limit mentioned in a review", 300)[0] == "ran"
    assert rr.classify(1, "HTTP 429", 300)[0] == "skipped: usage limit"
    assert rr.classify(1, "insufficient credits", 300)[0] == "skipped: usage limit"
    assert rr.classify(2, "TypeError", 300)[0] == "failed: exit 2"
    assert rr.classify(None, "", 300)[0] == "failed: timeout after 300s"


def test_targets(env):
    repo, _, _ = env
    desc, slug, ctx = rr.build_target(repo, "diff")
    assert slug == "diff" and "# changed" in ctx
    desc, slug, ctx = rr.build_target(repo, "plan:7")
    assert slug == "plan-7" and "# Plan 7" in ctx
    desc, slug, ctx = rr.build_target(repo, "version:1.2.0")
    assert slug == "version-1.2.0" and "007-thing.md" in ctx
    desc, slug, ctx = rr.build_target(repo, "repo")
    assert "app.py" in ctx and "007-thing.md" in ctx
    with pytest.raises(ValueError):
        rr.build_target(repo, "plan:99")
    with pytest.raises(ValueError):
        rr.build_target(repo, "nonsense")


def test_clean_tree_diff_target_is_an_error(env):
    repo, bin_dir, run = env
    subprocess.run(["git", "checkout", "-q", "app.py"], cwd=repo, check=True)
    res = run("diff", "--members", "agy")
    assert res.returncode == 1
    assert "nothing to review" in res.stderr


def test_prompt_template_has_placeholders_and_finding_format():
    text = rr.PROMPT_FILE.read_text()
    assert "{{TARGET}}" in text and "{{CONTEXT}}" in text
    assert "FINDING|<critical|high|medium|low>|<path:line or NONE>|<short title>|<evidence>" in text


def test_every_member_documented_in_members_md():
    doc = (REPO / "skills/adversarial-review/references/members.md").read_text()
    for m in rr.MEMBERS:
        assert f"## {m.name}" in doc
    for name in rr.EXCLUDED:
        assert name in doc
    assert rr.OPENCODE_PRIMARY_MODEL in doc and rr.OPENCODE_FALLBACK_MODEL in doc


def test_install_only_adversarial_review(tmp_path):
    res = subprocess.run(["bash", str(REPO / "install.sh"), "--project",
                          "--only=adversarial-review"],
                         cwd=tmp_path, env={**os.environ, "PYTHON": "python3.11"},
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    skill = tmp_path / ".claude/skills/adversarial-review"
    for rel in ("SKILL.md", "VERSION", "scripts/run_review.py", "prompts/adversarial.md",
                "references/members.md"):
        assert (skill / rel).is_file(), rel
    assert (tmp_path / ".claude/commands/adversarial-review.md").is_file()
    assert not (tmp_path / ".claude/skills/roadmap").exists()
    assert not list((tmp_path / ".claude/commands").glob("roadmap-*.md"))


# Round-2 fakes: answer the refute prompt (stdin for claude, last argv for agy).
REFUTER = """
prompt = stdin or (args[-1] if args else "")
if "Findings to attack" in prompt:
{round2}
else:
{round1}
"""


def _two_round(round1, round2):
    ind = lambda t: textwrap.indent(textwrap.dedent(t).strip(), "    ")
    return REFUTER.format(round1=ind(round1), round2=ind(round2))


F_B = "FINDING|medium|app.py:1|Missing type check|def f(x) accepts anything"


def test_refute_round_moves_refuted_findings_out_of_ranking(env):
    repo, bin_dir, run = env
    # agy reports F_A (high -> F1); claude reports F_B (medium -> F2).
    # claude refutes F1 with a cited location; agy "refutes" F2 without one (ignored).
    _fake(bin_dir, "agy", _two_round(_reply(F_A),
          _reply("REFUTE|F2|NONE|I just do not believe it")))
    _fake(bin_dir, "claude", _two_round(_reply(F_B),
          _reply("REFUTE|F1|app.py:1|f is never called with a divisor; see app.py:1")))
    res = run("--members", "agy,claude", "--refute")
    assert res.returncode == 0, res.stderr
    assert len((bin_dir / "agy.calls").read_text().splitlines()) == 2
    assert len((bin_dir / "claude.calls").read_text().splitlines()) == 2
    summary, out_dir = _summary(repo)
    ranked = summary.split("## Findings")[1].split("## Refuted")[0]
    refuted = summary.split("## Refuted")[1].split("## Unconfirmed")[0]
    assert "Missing type check" in ranked          # unrefuted survivor stays ranked
    assert "Division by zero" not in ranked
    assert "Division by zero" in refuted
    assert "refuted by claude at `app.py:1`" in refuted
    assert "## Refutation round" in summary
    assert "Refutation round: ran" in (out_dir / "claude.md").read_text()


def test_refute_round_skips_member_with_nothing_to_refute(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _two_round(_reply(F_A), _reply("UPHOLD|F1|fine")))
    res = run("--members", "agy", "--refute")
    assert res.returncode == 0, res.stderr
    assert len((bin_dir / "agy.calls").read_text().splitlines()) == 1
    summary, _ = _summary(repo)
    assert "skipped: nothing to refute" in summary
    assert "Division by zero" in summary.split("## Refuted")[0]


def test_exclude_flag_skips_member(env):
    repo, bin_dir, run = env
    _fake(bin_dir, "agy", _reply(F_A))
    _fake(bin_dir, "claude", _reply(F_A))
    res = run("--members", "agy,claude", "--exclude", "claude")
    assert res.returncode == 0, res.stderr
    assert not (bin_dir / "claude.calls").exists()
    summary, out_dir = _summary(repo)
    assert "| skipped: excluded by user |" in _row(summary, "claude")
    assert (out_dir / "claude.md").is_file()
    assert run("--exclude", "nobody").returncode == 1


def test_member_commands_are_fresh_sessions_and_read_only():
    forbidden = {"--continue", "-c", "--session", "--fork", "--resume", "-r", "resume",
                 "--conversation", "--yolo", "--force", "-f", "--auto",
                 "--dangerously-skip-permissions", "--sandbox"}
    for m in rr.MEMBERS:
        models = m.models or (None,)
        for model in models:
            argv = m.argv("/bin/" + m.binary, "PROMPT", outfile="/tmp/x", model=model)
            assert not rr.session_flags_in(m, argv), (m.name, argv)
            assert not forbidden & set(argv[1:]), (m.name, argv)
            if m.name != "codex":
                assert "-s" not in argv[1:], (m.name, argv)
    assert rr.session_flags_in(rr.MEMBERS[-1], ["opencode", "run", "-s", "x"]) == ["-s"]
    assert rr.session_flags_in(rr.MEMBERS[0], ["codex", "exec", "resume"]) == ["resume"]
