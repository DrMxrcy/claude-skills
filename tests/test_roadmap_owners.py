"""Claim owners and the work-in-progress limit (plan 40)."""
import datetime
import json
import re

import pytest


def _repo(roadmap, repo, monkeypatch, n=1, settings=None):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    for i in range(n):
        roadmap.new_item(repo, "feature", f"Item {i + 1}")
    if settings:
        cfg = roadmap.read_config(repo)
        cfg.setdefault("settings", {}).update(settings)
        roadmap.write_config(repo, cfg)
    return repo


def _plan(repo, plan_id):
    return next((repo / ".roadmap/plans").glob(f"{plan_id:03d}-*.md"))


def _age_claim(repo, plan_id, hours):
    """Rewrite the claim's refresh stamp to `hours` ago (a fixture-level edit)."""
    path = _plan(repo, plan_id)
    when = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = re.sub(r"^claim_refreshed: .*$", f"claim_refreshed: {when}",
                  path.read_text(), flags=re.M)
    path.write_text(text)


def _as(monkeypatch, owner):
    monkeypatch.setenv("ROADMAP_OWNER", owner)


# --- step 1: claim_owner, held check, --take, TTL ---------------------------

def test_held_claim_refuses_other_owner_until_take_or_ttl(roadmap, repo, monkeypatch,
                                                         capsys):
    _repo(roadmap, repo, monkeypatch, n=5)
    assert roadmap.main(["claim", "5", "--owner", "alice", "--stage", "review"]) == 0
    claim = roadmap.read_claim(_plan(repo, 5))
    assert claim["owner"] == "alice" and claim["refreshed"].endswith("Z")
    capsys.readouterr()

    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "5", "--stage", "review"]) == 1
    err = capsys.readouterr().err
    assert "held by alice" in err and "claimed" in err and "--take" in err
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "alice"     # untouched

    assert roadmap.main(["claim", "5", "--stage", "review", "--take"]) == 0
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "bob"

    _age_claim(repo, 5, 13)                                  # past the 12h default
    _as(monkeypatch, "carol")
    assert roadmap.main(["claim", "5", "--stage", "fixing"]) == 0
    assert roadmap.read_claim(_plan(repo, 5))["owner"] == "carol"


def test_claim_ttl_setting_and_zero_disables_holds(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch, settings={"claimTtlHours": 2})
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    _age_claim(repo, 1, 3)
    roadmap.set_claim(repo, 1, stage="fixing", owner="bob")     # 3h > 2h TTL
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "bob"
    cfg = roadmap.read_config(repo)
    cfg["settings"]["claimTtlHours"] = 0
    roadmap.write_config(repo, cfg)
    roadmap.set_claim(repo, 1, stage="gating", owner="carol")   # holds off
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "carol"


def test_same_owner_refreshes_case_insensitively(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="Alice")
    _age_claim(repo, 1, 5)
    before = roadmap.read_claim(_plan(repo, 1))["refreshed"]
    roadmap.set_claim(repo, 1, verdict="CONFIRMED", owner="alice")
    after = roadmap.read_claim(_plan(repo, 1))
    assert after["refreshed"] > before and after["verdict"] == "CONFIRMED"


def test_ownerless_claim_stays_claimable(roadmap, repo, monkeypatch):
    """Fails-if guard: a claim written before plan 40 (no owner) is never held."""
    _repo(roadmap, repo, monkeypatch)
    path = _plan(repo, 1)
    path.write_text(path.read_text().replace(
        "---\n", "---\nclaim_stage: review\nclaim_updated: 2026-10-23\n", 1))
    assert roadmap.read_claim(path)["owner"] is None
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "--stage", "fixing"]) == 0
    assert roadmap.read_claim(path)["owner"] == "bob"


def test_default_owner_is_git_user_name(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review")
    assert roadmap.read_claim(_plan(repo, 1))["owner"] == "t"    # fixture user.name


def test_default_owner_order(repo, monkeypatch):
    from rmlib import owners
    assert owners.default_owner(repo) == "t"
    monkeypatch.setenv("ROADMAP_OWNER", "  ci   bot ")
    assert owners.default_owner(repo) == "ci bot"
    monkeypatch.delenv("ROADMAP_OWNER")

    def no_git(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(owners.subprocess, "run", no_git)
    assert owners.default_owner(repo) is None
    monkeypatch.setenv("CLAUDECODE", "1")
    assert owners.default_owner(repo) == "claude"


def test_owner_only_claim_holds_without_a_stage(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    assert roadmap.main(["claim", "1", "--owner", "alice"]) == 0
    claim = roadmap.read_claim(_plan(repo, 1))
    assert claim["owner"] == "alice" and claim["stage"] is None
    row = roadmap.status(repo)["items"][0]
    assert row["lane"] == "planned" and roadmap.is_in_flight(row)
    capsys.readouterr()
    # Without --owner a new claim still needs a stage.
    roadmap.new_item(repo, "feature", "B")
    assert roadmap.main(["claim", "2", "--verdict", "CONFIRMED"]) == 1
    assert "--stage" in capsys.readouterr().err


def test_clear_refuses_other_owner_until_take(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "--clear"]) == 1
    assert "held by alice" in capsys.readouterr().err
    assert roadmap.read_claim(_plan(repo, 1)) is not None
    assert roadmap.main(["claim", "1", "--clear", "--take"]) == 0
    assert roadmap.read_claim(_plan(repo, 1)) is None
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    assert roadmap.main(["claim", "1", "--clear", "--owner", "alice"]) == 0


def test_multi_id_claim_all_or_nothing_on_hold(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch, n=2)
    roadmap.set_claim(repo, 2, stage="review", owner="alice")
    _as(monkeypatch, "bob")
    assert roadmap.main(["claim", "1", "2", "--stage", "gating"]) == 1
    assert "#2 is held by alice" in capsys.readouterr().err
    assert roadmap.read_claim(_plan(repo, 1)) is None              # nothing written


def test_landed_and_take_flags_are_exclusive(roadmap, repo, monkeypatch):
    _repo(roadmap, repo, monkeypatch)
    for extra in (["--owner", "a"], ["--take"]):
        with pytest.raises(SystemExit):
            roadmap.main(["claim", "--landed", "HEAD", *extra])
    with pytest.raises(SystemExit):
        roadmap.main(["claim", "1", "--clear", "--stage", "review"])


def test_owner_round_trips_in_status_json(roadmap, repo, monkeypatch, capsys):
    _repo(roadmap, repo, monkeypatch)
    roadmap.set_claim(repo, 1, stage="review", owner="alice")
    capsys.readouterr()
    assert roadmap.main(["status", "--json"]) == 0
    item = json.loads(capsys.readouterr().out)["items"][0]
    assert item["claim"]["owner"] == "alice"
