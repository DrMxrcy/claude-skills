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


# ---- completion gate (settings.requireAcceptance) ----------------------------

def _steps(roadmap, repo, n=1):
    return len(roadmap.parse_plan(_plan(repo, n))["steps"])


def test_gate_refuses_final_step_naming_unmarked_bullets(roadmap, proj):
    _require(roadmap, proj)
    total = _steps(roadmap, proj)
    assert total >= 2
    for s in range(1, total):                 # non-final steps are never gated
        roadmap.check_step(proj, 1, s)
    roadmap.accept(proj, 1, 1, "renders")
    before = _plan(proj).read_text(encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        roadmap.check_step(proj, 1, total, evidence="suite green")
    msg = str(exc.value)
    assert "requireAcceptance" in msg and "#2 [unmarked]" in msg
    assert "`pytest -q` is green" in msg and "#1" not in msg and "Fails if" not in msg
    assert _plan(proj).read_text(encoding="utf-8") == before      # nothing written


def test_gate_refuses_all_done_and_failed_bullets(roadmap, proj):
    _require(roadmap, proj)
    roadmap.accept(proj, 1, 1, "ok")
    roadmap.accept(proj, 1, 2, "3 failures", fail=True)
    with pytest.raises(ValueError, match=r"#2 \[failed\]"):
        roadmap.check_step(proj, 1, None, all_done=True)


def test_gate_passes_once_every_criterion_is_met(roadmap, proj):
    _require(roadmap, proj)
    roadmap.accept(proj, 1, 1, "renders")
    roadmap.accept(proj, 1, 2, "pytest green")          # the guard stays unmarked
    roadmap.check_step(proj, 1, None, all_done=True, evidence="suite green")
    assert roadmap.count_progress(_plan(proj)) == (_steps(roadmap, proj),) * 2
    assert "forced past" not in _plan(proj).read_text(encoding="utf-8")


def test_gate_force_succeeds_and_records_override(roadmap, proj):
    _require(roadmap, proj)
    total = _steps(roadmap, proj)
    roadmap.check_step(proj, 1, None, all_done=True, evidence="suite green",
                       force=True)
    text = _plan(proj).read_text(encoding="utf-8")
    assert roadmap.count_progress(_plan(proj)) == (total, total)
    assert text.count(f"> evidence: suite green · forced past unaccepted "
                      f"acceptance (#1, #2) ({TODAY})") == total


def test_gate_force_without_evidence_still_records(roadmap, proj):
    _require(roadmap, proj)
    total = _steps(roadmap, proj)
    for s in range(1, total):
        roadmap.check_step(proj, 1, s)
    roadmap.check_step(proj, 1, total, force=True)
    text = _plan(proj).read_text(encoding="utf-8")
    assert text.count("> evidence: forced past unaccepted acceptance (#1, #2)") == 1
    lines = text.splitlines()
    step_line = [i for i, l in enumerate(lines) if l.startswith("- [x]")][-1]
    assert lines[step_line + 1].startswith("  > evidence: forced past unaccepted")


def test_gate_ignores_undo_and_rechecks_of_done_items(roadmap, proj):
    roadmap.check_step(proj, 1, None, all_done=True)       # done before opting in
    _require(roadmap, proj)
    roadmap.check_step(proj, 1, 1)                          # re-tick: not completing
    roadmap.check_step(proj, 1, 1, undo=True)
    with pytest.raises(ValueError, match="requireAcceptance"):
        roadmap.check_step(proj, 1, 1)                      # completes again: gated


def test_gate_off_behaviour_unchanged(roadmap, proj):
    assert not (roadmap.read_config(proj).get("settings") or {}).get(
        "requireAcceptance")
    roadmap.check_step(proj, 1, None, all_done=True, evidence="suite green")
    text = _plan(proj).read_text(encoding="utf-8")
    assert "forced past" not in text and "> accepted" not in text


def test_init_default_on_for_new_projects_only(roadmap, repo, monkeypatch,
                                               acceptance_gate):
    monkeypatch.chdir(repo)
    cfg = roadmap.init_project(repo, "P", claude_md=False)
    assert cfg["settings"]["requireAcceptance"] is True
    # an existing project (no setting) keeps it off through init and upgrade
    cfg["settings"].pop("requireAcceptance")
    roadmap.write_config(repo, cfg)
    roadmap.init_project(repo, "P", claude_md=False)
    roadmap.upgrade(repo)
    assert "requireAcceptance" not in roadmap.read_config(repo)["settings"]

