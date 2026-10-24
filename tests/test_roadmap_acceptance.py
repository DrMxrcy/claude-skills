"""Acceptance ledger (plan 43): `roadmap.py accept` marks ✅ Acceptance bullets met
or failed with evidence; settings.requireAcceptance gates the check that would
complete an item; status/dashboard report per-bullet state."""
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"

TODAY = datetime.date.today().isoformat()

ACCEPTANCE = """## ✅ Acceptance
- **Passes when:** the widget renders
- **Passes when:** `pytest -q` is green
  with a wrapped continuation line
- **Fails if:** the old API breaks
"""


def _plan(repo, n=1):
    return next((repo / ".roadmap/plans").glob(f"{n:03d}-*.md"))


def _fill(repo, n=1, acceptance=ACCEPTANCE):
    """Replace the template Acceptance section with real bullets."""
    p = _plan(repo, n)
    text = p.read_text(encoding="utf-8")
    start = text.index("## ✅ Acceptance")
    end = text.index("\n## ", start + 1) + 1
    p.write_text(text[:start] + acceptance + "\n" + text[end:], encoding="utf-8")
    return p


@pytest.fixture
def proj(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.new_item(repo, "feature", "Widget")
    _fill(repo)
    return repo


def _require(roadmap, repo, on=True):
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {})["requireAcceptance"] = on
    roadmap.write_config(repo, cfg)


# ---- parsing + accept --------------------------------------------------------

def test_list_bullets_numbers_all_and_marks_guards(roadmap, proj):
    bullets = roadmap.list_acceptance(proj, 1)
    assert [(b["n"], b["kind"], b["label"]) for b in bullets] == [
        (1, "criterion", "Passes when"), (2, "criterion", "Passes when"),
        (3, "guard", "Fails if")]
    assert bullets[1]["text"] == "`pytest -q` is green"
    assert all(b["state"] is None for b in bullets)


def test_accept_writes_marker_under_bullet_after_continuation(roadmap, proj):
    b = roadmap.accept(proj, 1, 2, "pytest   green")
    assert b == {"n": 2, "kind": "criterion", "label": "Passes when",
                 "text": "`pytest -q` is green", "state": "met", "date": TODAY,
                 "evidence": "pytest green"}
    text = _plan(proj).read_text(encoding="utf-8")
    assert ("  with a wrapped continuation line\n"
            f"  > accepted: {TODAY} pytest green\n- **Fails if:**") in text
    assert roadmap.list_acceptance(proj, 1)[0]["state"] is None
    # the marker is never read as a checklist step
    assert roadmap.count_progress(_plan(proj)) == (0, len(roadmap.parse_plan(
        _plan(proj))["steps"]))


def test_accept_fail_then_pass_replaces_marker(roadmap, proj):
    assert roadmap.accept(proj, 1, 1, "broken on 375px", fail=True)["state"] == "failed"
    assert roadmap.accept(proj, 1, 1, "fixed, renders")["state"] == "met"
    text = _plan(proj).read_text(encoding="utf-8")
    assert text.count("> failed:") == 0 and text.count("> accepted:") == 1
    assert roadmap.list_acceptance(proj, 1)[0]["evidence"] == "fixed, renders"


def test_accept_refuses_guard_range_and_empty_evidence(roadmap, proj):
    with pytest.raises(ValueError, match="guard"):
        roadmap.accept(proj, 1, 3, "n/a")
    with pytest.raises(ValueError, match="out of range"):
        roadmap.accept(proj, 1, 4, "x")
    with pytest.raises(ValueError, match="--evidence"):
        roadmap.accept(proj, 1, 1, "   ")


def test_accept_without_acceptance_section(roadmap, proj):
    p = _plan(proj)
    text = p.read_text(encoding="utf-8")
    start = text.index("## ✅ Acceptance")
    p.write_text(text[:start] + text[text.index("\n## ", start + 1) + 1:],
                 encoding="utf-8")
    assert roadmap.list_acceptance(proj, 1) == []
    with pytest.raises(ValueError, match="no ✅ Acceptance"):
        roadmap.accept(proj, 1, 1, "x")


def test_acceptance_parsing_skips_fences_and_comments(roadmap, proj):
    _fill(proj, acceptance="## ✅ Acceptance\n<!-- - **Passes when:** hidden -->\n"
          "```\n- **Passes when:** fenced\n```\n- **Passes when:** real one\n"
          "  - nested detail is not a bullet\n")
    bullets = roadmap.list_acceptance(proj, 1)
    assert [b["text"] for b in bullets] == ["real one"]
    roadmap.accept(proj, 1, 1, "ok")
    assert "  - nested detail is not a bullet\n  > accepted:" in \
        _plan(proj).read_text(encoding="utf-8")


def test_unlabeled_bullet_is_a_criterion(roadmap, proj):
    _fill(proj, acceptance="## ✅ Acceptance\n- the build is green\n"
          "- **Fails when:** docs drift\n")
    kinds = [(b["kind"], b["label"]) for b in roadmap.list_acceptance(proj, 1)]
    assert kinds == [("criterion", None), ("guard", "Fails when")]


def test_cli_accept_list_and_mark(proj):
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], cwd=proj,
                                    capture_output=True, text=True)
    r = run("accept", "1", "--line", "2", "--evidence", "pytest green")
    assert r.returncode == 0 and "met — pytest green" in r.stdout
    r = run("accept", "1")
    assert r.returncode == 0
    assert " 1. [open] Passes when: the widget renders" in r.stdout
    assert " 2. [met] Passes when: `pytest -q` is green" in r.stdout
    assert f"{TODAY} pytest green" in r.stdout
    assert " 3. [guard] Fails if: the old API breaks" in r.stdout
    data = json.loads(run("accept", "1", "--json").stdout)
    assert [b["state"] for b in data] == [None, "met", None]
    r = run("accept", "1", "--evidence", "x")
    assert r.returncode != 0 and "need --line" in r.stderr
    r = run("accept", "1", "--line", "3", "--evidence", "x")
    assert r.returncode != 0 and "guard" in (r.stderr + r.stdout)

