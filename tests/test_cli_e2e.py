import subprocess, sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"


def run(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=repo, capture_output=True, text=True)


def fill_feature_plan(repo, plan="001-*.md"):
    """Fill the required sections of a freshly generated feature plan so `check`
    accepts it (the template gate refuses while they are still template text)."""
    path = next((repo / ".roadmap/plans").glob(plan))
    text = path.read_text().replace("- **Core objective:**", "- **Core objective:** ship")
    text = text.replace("<observable behavior a reviewer can verify without reading the diff>",
                        "the flow works").replace("<test/command that must be green>",
                                                  "pytest").replace(
        "<regression or out-of-scope change that blocks sign-off>", "anything regresses")
    path.write_text(text)


def test_full_flow(repo):
    assert run(repo, "init", "--name", "E2E").returncode == 0
    out = run(repo, "new", "--type", "feature", "--title", "Login",
              "--note", "Sign in with email", "--audience", "public")
    assert out.returncode == 0
    # a plan whose required sections are still template text cannot be checked
    refused = run(repo, "check", "--plan", "1", "--step", "1")
    assert refused.returncode == 1
    assert "Core objective, Acceptance" in refused.stderr and "001-login.md" in refused.stderr
    fill_feature_plan(repo)
    assert run(repo, "check", "--plan", "1", "--step", "1").returncode == 0
    st = run(repo, "status")
    assert "Login" in st.stdout
    # release is guarded: an incomplete version is refused...
    assert run(repo, "release", "--version", "0.0.2").returncode == 1
    # ...complete the item, then release succeeds and writes a changelog.
    assert run(repo, "check", "--plan", "1", "--all-done").returncode == 0
    assert run(repo, "release", "--version", "0.0.2").returncode == 0
    rm = (repo / "ROADMAP.md").read_text()
    # shipped v0.0.1 collapses to a summary line; its items live in the changelogs
    assert "v0.0.2" in rm and "v0.0.1 — 100% · 1 item" in rm and "#1 Login" not in rm
    cl = (repo / "CHANGELOG.md").read_text()
    assert "✨ New" in cl and "Sign in with email" in cl
    assert "Login" not in cl                 # public changelog never uses raw titles


def test_note_cli_blocks_status_dump_then_force(repo):
    assert run(repo, "init", "--name", "E2E").returncode == 0
    assert run(repo, "new", "--type", "feature", "--title", "Watch").returncode == 0
    assert run(repo, "audience", "--plan", "1", "--to", "public").returncode == 0
    bad = run(repo, "note", "--plan", "1",
              "--text", "Step 9: glance DONE, complication DEFERRED (see specs/a/b.md)")
    assert bad.returncode == 1 and "status/progress dump" in bad.stderr
    assert run(repo, "note", "--plan", "1",
               "--text", "Log rides straight from your wrist.").returncode == 0
    forced = run(repo, "note", "--plan", "1", "--text", "Step 9 DONE", "--force")
    assert forced.returncode == 0


def test_summary_cli_roundtrip(repo):
    assert run(repo, "init", "--name", "E2E").returncode == 0
    assert run(repo, "new", "--type", "feature", "--title", "Trips",
               "--note", "Share trips with friends", "--audience", "public").returncode == 0
    assert run(repo, "check", "--plan", "1", "--all-done", "--force").returncode == 0
    bad = run(repo, "summary", "--version", "0.0.1", "--text", "Step 3 DONE")
    assert bad.returncode == 1 and "status/progress dump" in bad.stderr
    ok = run(repo, "summary", "--version", "0.0.1",
             "--text", "This release includes minor bug fixes and improvements.")
    assert ok.returncode == 0
    cl = (repo / "CHANGELOG.md").read_text()
    assert "minor bug fixes" in cl and "Share trips" not in cl


def test_status_worktrees_cli(repo, tmp_path_factory):
    """`status --worktrees` lists linked worktrees, marks the merged-clean one
    safe, prints its removal command, and removes nothing (plan 36)."""
    git = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, check=True,
                                              capture_output=True, text=True)
    git("symbolic-ref", "HEAD", "refs/heads/main")
    assert run(repo, "init", "--name", "E2E").returncode == 0
    git("add", "-A")
    git("commit", "-qm", "init")
    base = tmp_path_factory.mktemp("e2e-wt")
    done, wip = base / "done", base / "wip"
    git("worktree", "add", "-q", "-b", "roadmap/1", str(done))
    git("worktree", "add", "-q", "-b", "roadmap/2", str(wip))
    git("commit", "--allow-empty", "-qm", "wip (plan 2)", cwd=wip)
    out = run(repo, "status", "--worktrees")
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines()[0] == "worktrees: 2 linked · 1 safe to remove"
    assert f"git worktree remove {done.resolve()}" in out.stdout
    assert done.is_dir() and wip.is_dir()
    assert "roadmap/1" in git("branch", "--list").stdout
