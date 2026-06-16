import subprocess, sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"


def run(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=repo, capture_output=True, text=True)


def test_full_flow(repo):
    assert run(repo, "init", "--name", "E2E").returncode == 0
    out = run(repo, "new", "--type", "feature", "--title", "Login")
    assert out.returncode == 0
    assert run(repo, "check", "--plan", "1", "--step", "1").returncode == 0
    st = run(repo, "status")
    assert "Login" in st.stdout
    # release is guarded: an incomplete version is refused...
    assert run(repo, "release", "--version", "0.0.2").returncode == 1
    # ...complete the item, then release succeeds and writes a changelog.
    assert run(repo, "check", "--plan", "1", "--all-done").returncode == 0
    assert run(repo, "release", "--version", "0.0.2").returncode == 0
    rm = (repo / "ROADMAP.md").read_text()
    assert "v0.0.2" in rm and "Login" in rm
    cl = (repo / "CHANGELOG.md").read_text()
    assert "✨ New" in cl and "Login" in cl
