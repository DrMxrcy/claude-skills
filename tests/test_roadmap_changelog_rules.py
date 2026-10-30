"""Plan 62: per-project changelog lint rules (settings.internalTerms / internalPatterns /
publicTerms), settings.changelogStyle "summary+bullets", and the extra disclosure/version
tells ported from statewide-app."""
import json

import pytest


def _settings(roadmap, repo, **kv):
    cfg = roadmap.read_config(repo)
    cfg.setdefault("settings", {}).update(kv)
    roadmap.write_config(repo, cfg)


def _shipped_public(roadmap, repo, note="Share trips with friends."):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips", note=note, audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)


def _render_all(roadmap, repo):
    md, warns = roadmap.render_public_changelog(repo)
    return (md, warns, roadmap.render_internal_changelog(repo),
            json.dumps(roadmap.changelog_json(repo), sort_keys=True),
            roadmap.audit_public_notes(repo))


def test_changelog_rules_default_empty(roadmap):
    assert roadmap.changelog_rules({}) == {"extra_terms": [], "extra_patterns": [],
                                           "allow": []}
    assert roadmap.changelog_rules({"settings": {"autoCommit": True}})["allow"] == []


def test_absent_keys_render_identically_to_explicit_defaults(roadmap, repo):
    """No new keys == today's output: the default style and empty rule lists are no-ops."""
    _shipped_public(roadmap, repo)
    roadmap.new_item(repo, "bug", "Crash on start", note="Opening the app no longer crashes.",
                     audience="public")
    roadmap.set_release_summary(repo, "0.0.1", "A smoother ride all around.")
    before = _render_all(roadmap, repo)
    _settings(roadmap, repo, changelogStyle="summary", internalTerms=[],
              internalPatterns=[], publicTerms=[])
    assert _render_all(roadmap, repo) == before


def test_internal_terms_flag_public_note(roadmap, repo):
    _shipped_public(roadmap, repo, note="Trips now sync with Acmecorp calendars.")
    assert not any("#1 note" in m for m in roadmap.audit_public_notes(repo))
    _settings(roadmap, repo, internalTerms=["acmecorp"])
    msgs = roadmap.audit_public_notes(repo)
    assert any("#1 note reads internal (acmecorp)" in m for m in msgs)


def test_internal_patterns_flag_public_note(roadmap, repo):
    _shipped_public(roadmap, repo, note="Trips load faster, per TKT-42.")
    assert not any("#1 note" in m for m in roadmap.audit_public_notes(repo))
    _settings(roadmap, repo, internalPatterns=[r"\btkt-\d+\b"])   # case-insensitive
    msgs = roadmap.audit_public_notes(repo)
    assert any("#1 note reads internal (TKT-42)" in m for m in msgs)
    assert roadmap.lint_note("see tkt-7", extra_patterns=[r"\bTKT-\d+\b"]) == ["tkt-7"]


def test_internal_terms_warn_on_set_note(roadmap, repo, capsys):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Trips", audience="public")
    _settings(roadmap, repo, internalTerms=["acmecorp"])
    roadmap.set_note(repo, 1, "Trips now sync with Acmecorp calendars.")
    assert "note reads internal (acmecorp)" in capsys.readouterr().err


def test_public_terms_keep_a_line_public(roadmap, repo):
    """`staff` is an operator tell by default; a product where staff are users allows it."""
    roadmap.init_project(repo, "P")
    note = "Staff can now pin announcements for the whole community."
    with pytest.raises(ValueError, match="wrong-audience"):
        roadmap.new_item(repo, "feature", "Pins", note=note, audience="public")
    _settings(roadmap, repo, publicTerms=["staff"])
    roadmap.new_item(repo, "feature", "Pins", note=note, audience="public")
    roadmap.check_step(repo, 1, None, all_done=True)
    assert note in (repo / "CHANGELOG.md").read_text()
    assert not any("#1" in m for m in roadmap.audit_public_notes(repo))


def test_public_terms_allow_audience_public(roadmap, repo):
    roadmap.init_project(repo, "P")
    roadmap.new_item(repo, "feature", "Admin roles", note="Pick who helps run your group.",
                     audience="internal")
    with pytest.raises(ValueError, match="public audience refused"):
        roadmap.set_audience(repo, 1, "public")
    _settings(roadmap, repo, publicTerms=["admin"])
    roadmap.set_audience(repo, 1, "public")
    assert roadmap.read_config(repo)["items"][0]["audience"] == "public"


def test_summary_plus_bullets_renders_blurb_and_public_bullets(roadmap, repo):
    _shipped_public(roadmap, repo)
    roadmap.new_item(repo, "feature", "Infra", note="Moved the queue.", audience="internal")
    roadmap.check_step(repo, 2, None, all_done=True)
    roadmap.set_release_summary(repo, "0.0.1", "A smoother ride all around.")
    cl = (repo / "CHANGELOG.md").read_text()
    assert "A smoother ride all around." in cl
    assert "Share trips with friends." not in cl          # default: blurb only
    _settings(roadmap, repo, changelogStyle="summary+bullets")
    roadmap.sync(repo, quiet=True)
    cl = (repo / "CHANGELOG.md").read_text()
    assert "A smoother ride all around." in cl
    assert "Share trips with friends." in cl
    assert cl.index("A smoother ride all around.") < cl.index("Share trips with friends.")
    assert "Moved the queue." not in cl                     # internal stays out
    (entry,) = roadmap.changelog_json(repo)
    assert entry["notes"] == "A smoother ride all around."
    assert any("Share trips with friends." in str(v) for v in entry["sections"].values())
    assert entry["rollup"] is False


def test_summary_plus_bullets_audit_lints_notes_under_a_blurb(roadmap, repo):
    _shipped_public(roadmap, repo, note="Trips now sync with Acmecorp calendars.")
    _settings(roadmap, repo, internalTerms=["acmecorp"])
    roadmap.set_release_summary(repo, "0.0.1", "A smoother ride all around.")
    assert not any("#1 note" in m for m in roadmap.audit_public_notes(repo))  # blurb hides it
    _settings(roadmap, repo, changelogStyle="summary+bullets")
    assert any("#1 note reads internal" in m for m in roadmap.audit_public_notes(repo))


@pytest.mark.parametrize("text, hit", [
    ("Fixed a leak in the sharing link.", "leak"),
    ("Closes a ReDoS in search.", "redos"),
    ("Only the owner can open drafts now.", "Only the owner can open"),
    ("Strangers can no longer read your list.", "Strangers can no longer"),
    ("The app no longer exposes your email.", "no longer exposes"),
])
def test_new_disclosure_tells(roadmap, text, hit):
    assert hit in roadmap.demote_tells(text)


def test_bare_version_is_a_status_tell(roadmap):
    assert "1.0.2" in roadmap.status_tells("Ships in 1.0.2 for everyone.")
    assert roadmap.status_tells("Works with 1.0.2.3 builds.") == []   # not a semver token
