"""Bug routing (plan 47): `roadmap.py bug` fixes in-flight plans in place or files a
linked bug item; `idea` refuses bug reports; tidy/promote recognise them."""
import datetime
import json
import subprocess

import pytest

TODAY = datetime.date.today().isoformat()


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def proj(roadmap, repo, monkeypatch):
    """Six feature items; #6 done (all steps ticked)."""
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    for t in "ABCDEF":
        roadmap.new_item(repo, "feature", f"Item {t}")
    roadmap.check_step(repo, 6, None, all_done=True)
    return repo


def _plan(repo, n):
    return next((repo / ".roadmap/plans").glob(f"{n:03d}-*.md"))


# ---- in-flight origin: a Fix step on its own plan, no new item ----------------

def test_bug_in_flight_appends_fix_step_and_sets_fixing(roadmap, proj, capsys):
    roadmap.set_claim(proj, 5, stage="review", verdict="PARTIAL", note="pass 1")
    before = roadmap.read_config(proj)
    assert roadmap.main(["bug", "Menu clips", "--found-in", "5",
                         "--observed", "last button cut at 375 px"]) == 0
    out = capsys.readouterr().out
    assert "Step 3" in out and "no new item" in out and "fixing" in out
    after = roadmap.read_config(proj)
    assert after["nextId"] == before["nextId"] and after["items"] == before["items"]
    plan = _plan(proj, 5)
    lines = plan.read_text().splitlines()
    assert "- [ ] Step 3: Fix: Menu clips -> target: TBD" in lines
    assert roadmap.count_progress(plan) == (0, 3)
    c = roadmap.read_claim(plan)
    assert (c["stage"], c["verdict"], c["note"]) == ("fixing", "PARTIAL", "pass 1")
    found = roadmap.parse_plan(plan)["foundDuringBuild"]
    assert found == [f"Step 3: Menu clips ({TODAY}) — observed: last button cut at 375 px"]
    st = {i["id"]: i for i in roadmap.status(proj)["items"]}
    assert st[5]["lane"] == "fixing"


def test_bug_fix_step_lands_after_last_step_and_its_evidence(roadmap, proj):
    roadmap.check_step(proj, 5, 1, evidence="pytest: ok")
    roadmap.file_bug(proj, "Crash on save", found_in=5, target="app/save.py")
    lines = _plan(proj, 5).read_text().splitlines()
    i = lines.index("- [ ] Step 2:  -> target:")
    assert lines[i + 1] == "- [ ] Step 3: Fix: Crash on save -> target: app/save.py"
    ev = [n for n, ln in enumerate(lines) if ln.strip().startswith("> evidence:")]
    assert ev and ev[0] < i
    # second bug: Step 4 directly after Step 3, one more bullet in the same section
    roadmap.file_bug(proj, "Wrong total", found_in=5)
    text = _plan(proj, 5).read_text()
    lines = text.splitlines()
    assert lines[lines.index("- [ ] Step 3: Fix: Crash on save -> target: app/save.py")
                 + 1] == "- [ ] Step 4: Fix: Wrong total -> target: TBD"
    assert text.count("## 🐞 Found during build") == 1
    assert [f.split(" (")[0] for f in roadmap.parse_plan(_plan(proj, 5))[
        "foundDuringBuild"]] == ["Step 3: Crash on save", "Step 4: Wrong total"]


def test_bug_trunk_active_origin_is_fixed_in_place(roadmap, proj):
    roadmap.check_step(proj, 4, 1)          # active on trunk: no branch, no claim
    res = roadmap.file_bug(proj, "Export empty", found_in=4)
    assert res["route"] == "fix-step" and res["claim"] == "fixing"
    assert roadmap.read_claim(_plan(proj, 4))["stage"] == "fixing"


def test_bug_in_flight_by_branch_gets_a_new_fixing_claim(roadmap, proj, branches):
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "init")
    _git(proj, "checkout", "-qb", "roadmap/3")
    _git(proj, "commit", "--allow-empty", "-qm", "work (plan 3)")
    res = roadmap.file_bug(proj, "Menu clips", found_in=3)
    assert res["route"] == "fix-step"
    assert roadmap.read_claim(_plan(proj, 3))["stage"] == "fixing"


@pytest.fixture
def branches(roadmap):
    import importlib
    mod = importlib.import_module("rmlib.branches")
    for cache in (mod._CACHE, mod._WT_LIST, mod._DIRTY, mod._UNMERGED):
        cache.clear()
    return mod


def test_bug_not_started_origin_gets_step_without_claim(roadmap, proj):
    res = roadmap.file_bug(proj, "Menu clips", found_in=2)
    assert res == {**res, "route": "fix-step", "claim": None}
    assert roadmap.read_claim(_plan(proj, 2)) is None
    assert roadmap.count_progress(_plan(proj, 2)) == (0, 3)


def test_bug_fix_step_does_not_trip_the_template_gate(roadmap, proj, template_gate):
    plan = _plan(proj, 5)
    text = plan.read_text().replace("- **Core objective:**",
                                    "- **Core objective:** ship E")
    text = text.replace("<observable behavior a reviewer can verify without reading "
                        "the diff>", "E renders")
    text = text.replace("<test/command that must be green>", "pytest")
    text = text.replace("<regression or out-of-scope change that blocks sign-off>",
                        "the export suite goes red")
    plan.write_text(text)
    from rmlib.parse import required_sections, template_stubs
    names = required_sections(roadmap.read_config(proj), "feature")
    assert template_stubs(plan, *names) == []
    roadmap.set_claim(proj, 5, stage="review")
    roadmap.file_bug(proj, "Menu clips", found_in=5, observed="clipped")
    assert template_stubs(plan, *names) == []
    roadmap.check_step(proj, 5, 3)          # the gate lets the Fix step be checked
    assert roadmap.parse_plan(plan)["steps"][2] == (True, "Step 3: Fix: Menu clips "
                                                    "-> target: TBD")


def test_bug_fix_step_ignores_fenced_checkboxes(roadmap, proj):
    plan = _plan(proj, 5)
    plan.write_text(plan.read_text() + "\n```\n- [ ] not a step\n```\n")
    roadmap.set_claim(proj, 5, stage="review")
    res = roadmap.file_bug(proj, "Menu clips", found_in=5)
    assert res["step"] == 3 and roadmap.count_progress(plan) == (0, 3)
    lines = plan.read_text().splitlines()
    assert lines.index("- [ ] Step 3: Fix: Menu clips -> target: TBD") \
        < lines.index("- [ ] not a step")


# ---- shipped origin / no origin: a new bug item through new_item ---------------

def test_bug_shipped_origin_files_linked_bug_item(roadmap, proj, capsys):
    assert roadmap.main(["bug", "Export empty", "--found-in", "6",
                         "--observed", "CSV has headers only"]) == 0
    out = capsys.readouterr().out
    assert "#7: new bug item" in out and "foundIn #6" in out
    cfg = roadmap.read_config(proj)
    item = cfg["items"][-1]
    assert (item["id"], item["type"], item["title"]) == (7, "bug", "Export empty")
    assert cfg["nextId"] == 8
    plan = proj / ".roadmap" / item["file"]
    text = plan.read_text()
    assert "# 🐛 Plan 7: Export empty" in text                 # bug template
    assert "- **Observed:** CSV has headers only" in text
    assert roadmap.parse_plan(plan)["meta"]["foundIn"] == "6"
    assert roadmap.parse_plan(_plan(proj, 6))["meta"]["bugsFound"] == "7"
    assert "Export empty" in (proj / "ROADMAP.md").read_text()  # ROADMAP.md row
    assert roadmap.count_progress(_plan(proj, 6)) == (2, 2)    # origin stays done
    # a second bug from the same origin extends the back-link
    roadmap.file_bug(proj, "Export slow", found_in=6)
    assert roadmap.parse_plan(_plan(proj, 6))["meta"]["bugsFound"] == "7, 8"


def test_bug_without_origin_is_a_plain_bug_item(roadmap, proj):
    res = roadmap.file_bug(proj, "Loose bug", version="0.2.0")
    assert res["route"] == "new-item" and res["foundIn"] is None
    item = roadmap.read_config(proj)["items"][-1]
    assert (item["type"], item["version"]) == ("bug", "0.2.0")
    meta = roadmap.parse_plan(res["path"])["meta"]
    assert "foundIn" not in meta
    assert "- **Observed:**\n" in res["path"].read_text()       # nothing pre-filled


def test_bug_cli_errors(roadmap, proj, capsys):
    assert roadmap.main(["bug", "X", "--found-in", "99"]) == 1
    assert "99" in capsys.readouterr().err
    assert roadmap.main(["bug", "   "]) == 1
    assert "empty" in capsys.readouterr().err
    assert len(roadmap.read_config(proj)["items"]) == 6


def test_bug_version_ignored_for_fix_step(roadmap, proj, capsys):
    roadmap.set_claim(proj, 5, stage="review")
    assert roadmap.main(["bug", "Menu clips", "--found-in", "FEAT-5",
                         "--version", "9.9.9"]) == 0
    assert "ignored" in capsys.readouterr().err
    assert len(roadmap.read_config(proj)["items"]) == 6


# ---- incubator refuses bugs (step 2) ---------------------------------------------

# Real Idea Incubator bullets (statewide-app, 2026-10-23), real feature titles that
# use bug words as nouns, and imperative near misses — ideas, not bug reports.
# None may be refused (plan 47: zero false refusals).
REAL_IDEAS = [
    "Apex redirect service off the origin: bare community domains 301 to their www host",
    "Rank structure page: alternative layouts to the sheet grid",
    "Starter pack adds a Department of Justice judicial department",
    "Fire and EMS head ranks review patient care reports automatically through a "
    "rank to role link",
    "Symptom-organised Discord sync troubleshooting page for the docs site",
    "Announcement and audit channels for hires, promotions and certifications",
    "Nickname pattern builder with rank, callsign, department code and prefix tokens",
    "Remove a Discord role when its certification expires",
    "Application risk flags: duplicate submission, copy-paste, fast submission",
    "Apply-time Discord requirements: account age, 2FA, verified email, server membership",
    "Moving an application back a stage undoes the roles that stage added",
    "Rank change removes the previous rank role before adding the new one",
    "Starter pack copy pass: plain wording for seeded templates, descriptions and messages",
    "Sentence-case button sweep across the remaining Title Case buttons, dialogs and "
    "empty states",
    "Public map tile slicer CLI so communities can turn their own minimap textures or "
    "atlas into a tile folder",
    "Signed HTTPS operator webhooks (Standard Webhooks) to a Statewide backend",
    "Tone board extras: read-out text, stacked tones, targeted tones",
    "Custom lookup fields such as phone or permit number",
    "Injury body diagram on patient care reports",
    "Records API for speed cameras and automatic tickets",
    "Print a call",
    "Area of patrol shown in the MDT header and in game",
    "Stream overlay of calls and unit status",
    "Bulletin board on the MDT home for roll-call notices",
    # real feature item titles that use bug words as nouns, then near misses
    "Statewide voice pack: pre-generated alert, ALPR, tone-out and dispatcher voice "
    "clips on the CDN",
    "Branded error pages: app 404, error and offline pages in the shell look",
    "Reliability console: error inbox, queue lag alerts, deploy history, status page",
    "Native areas list from game zones and missing native streets",
    "Community voice clips: upload your own clip for a 10-code, nature or status",
    "Typed human-readable ID prefixes (TSK-42, BUG-7) as display layer over int ids",
    "Auto-collapse shipped versions in ROADMAP.md instead of a length warning on every "
    "call",
    "Retry failed webhooks",
    "Detect broken links in the docs",
    "Regression test suite for exports",
    "Crash reporting for the mobile app",
    "Handle missing avatars gracefully",
    "Show an error when the upload is too large",
]

BUG_REPORTS = [
    "Login page crashes on submit",
    "Menu clips on small screens",
    "Export is broken",
    "CSV export doesn't work",
    "Save fails with 500",
    "Wrong total on invoice",
    "Avatar missing from profile header",
    "Exception when saving draft",
    "Settings page throws an error on load",
    "Search returns 500 for quoted terms",
    "Dispatch board crashes after closing the docked call",
]


@pytest.mark.parametrize("title", REAL_IDEAS)
def test_real_incubator_ideas_are_never_refused(roadmap, title):
    assert roadmap.bug_tells(title) == []


@pytest.mark.parametrize("title", BUG_REPORTS)
def test_bug_reports_are_recognised(roadmap, title):
    assert roadmap.bug_tells(title)


def test_bug_tells_ignore_trailing_notes_link(roadmap):
    assert roadmap.bug_tells("Print a call ([notes](.roadmap/notes/x.md))") == []
    assert roadmap.bug_tells("Login crashes ([notes](.roadmap/notes/x.md))") == ["crash"]


def test_idea_refuses_bug_report_and_force_parks_it(roadmap, proj, capsys):
    assert roadmap.main(["idea", "--title", "Login page crashes on submit"]) == 1
    err = capsys.readouterr().err
    assert "reads like a bug report" in err and 'roadmap.py bug "Login page crashes' in err
    assert all("Login" not in b["title"] for b in roadmap.list_incubator_bullets(proj))
    assert roadmap.main(["idea", "--title", "Login page crashes on submit",
                         "--force"]) == 0
    assert [b["title"] for b in roadmap.list_incubator_bullets(proj)] == \
        ["Login page crashes on submit"]
    roadmap.add_idea(proj, "Dark mode toggle")            # ideas still park
    rep = roadmap.tidy_report(proj)
    flagged = [b for b in rep["bullets"] if "bug" in b["flags"]]
    assert [(b["title"], b["bugTells"]) for b in flagged] == \
        [("Login page crashes on submit", ["crash"])]
    text = roadmap.format_tidy(rep)
    assert "reads like a bug (crash)" in text and "Dark mode toggle" not in text


def test_promote_defaults_to_bug_for_bug_like_bullets(roadmap, proj):
    roadmap.add_idea(proj, "Login page crashes on submit", force=True)
    roadmap.add_idea(proj, "Dark mode toggle")
    roadmap.promote_idea(proj, match="Login")
    roadmap.promote_idea(proj, match="Dark")
    items = {i["title"]: i["type"] for i in roadmap.read_config(proj)["items"]}
    assert items["Login page crashes on submit"] == "bug"
    assert items["Dark mode toggle"] == "feature"
    roadmap.add_idea(proj, "Export is broken", force=True)
    assert roadmap.main(["promote", "--match", "Export", "--type", "feature"]) == 0
    assert roadmap.read_config(proj)["items"][-1]["type"] == "feature"   # explicit wins


# ---- payload and dashboard (step 4) -----------------------------------------------

def test_status_payload_carries_bug_links_and_found_fixes(roadmap, proj, dashboard):
    roadmap.set_claim(proj, 5, stage="review")
    roadmap.file_bug(proj, "Menu clips", found_in=5, observed="cut at 375 px")
    roadmap.file_bug(proj, "Export empty", found_in=6)
    st = {i["id"]: i for i in roadmap.status(proj)["items"]}
    assert st[5]["foundDuringBuild"] == [
        f"Step 3: Menu clips ({TODAY}) — observed: cut at 375 px"]
    assert (st[7]["foundIn"], st[7]["bugsFound"]) == (6, [])
    assert (st[6]["foundIn"], st[6]["bugsFound"]) == (None, [7])
    assert (st[1]["foundIn"], st[1]["bugsFound"], st[1]["foundDuringBuild"]) == \
        (None, [], [])
    json.dumps(st)                                   # payload stays JSON-clean
    d = dashboard._item_detail(roadmap, proj, 7)
    assert d["foundIn"] == 6
    d = dashboard._item_detail(roadmap, proj, 5)
    assert d["foundDuringBuild"] == st[5]["foundDuringBuild"]


def test_dashboard_html_shows_found_fixes_and_origin_links(dashboard):
    body = dashboard._dashboard_html()
    # plan 57: origin links live in the plan page details; the "found during
    # build" section renders from the plan body itself.
    for hook in ('"found in"', '"bugs found"', "row.foundIn", "row.bugsFound"):
        assert hook in body, hook
    assert ".innerHTML" not in body and "insertAdjacentHTML" not in body


def test_upgrade_writes_the_bug_rules_line(roadmap, repo, monkeypatch):
    monkeypatch.chdir(repo)
    roadmap.init_project(repo, "P", claude_md=False)
    (repo / "CLAUDE.md").write_text("# Notes\n")
    roadmap.upgrade(repo)
    text = (repo / "CLAUDE.md").read_text()
    assert "**Bugs never go in the incubator:**" in text
    assert 'roadmap.py bug "<title>" --found-in <id>' in text


# ---- claim hold (bug 51): refuse BEFORE writing the Fix step -------------------

def test_bug_refused_by_held_claim_writes_nothing_and_take_overrides(
        roadmap, proj, monkeypatch, capsys):
    roadmap.set_claim(proj, 5, stage="review", owner="alice")
    plan = _plan(proj, 5)
    before = plan.read_bytes()
    monkeypatch.setenv("ROADMAP_OWNER", "bob")
    assert roadmap.main(["bug", "Menu clips", "--found-in", "5"]) != 0
    assert "alice" in capsys.readouterr().err
    assert plan.read_bytes() == before
    assert roadmap.main(["bug", "Menu clips", "--found-in", "5", "--take"]) == 0
    assert "Fix: Menu clips" in plan.read_text()
    c = roadmap.read_claim(plan)
    assert (c["stage"], c["owner"]) == ("fixing", "bob")
