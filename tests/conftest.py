import importlib.util
import sys
import subprocess
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "skills/roadmap/scripts/roadmap.py"


@pytest.fixture
def roadmap():
    """Import roadmap.py as a module."""
    spec = importlib.util.spec_from_file_location("roadmap", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dashboard():
    """Import the dashboard module (rmlib package, beside roadmap.py)."""
    path = SCRIPT.parent / "rmlib" / "dashboard.py"
    spec = importlib.util.spec_from_file_location("roadmap_dashboard", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path):
    """A hermetic temp git repo (no commit/tag signing, so tests don't touch the
    user's GPG/SSH signing agent)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for key, val in (("user.email", "t@t.t"), ("user.name", "t"),
                     ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        subprocess.run(["git", "config", key, val], cwd=tmp_path, check=True)
    return tmp_path


# The plan-35 template gate makes `check` refuse while a plan's required sections are
# still template text. Most tests check steps on freshly generated plans, so the gate
# is off by default here; tests that exercise it request `template_gate`. (Subprocess
# CLI tests don't see this patch — they fill the plan or pass --force.)
sys.path.insert(0, str(SCRIPT.parent))
import rmlib.parse as _rmparse  # noqa: E402

_DEFAULT_REQUIRED = dict(_rmparse.DEFAULT_REQUIRED_SECTIONS)


@pytest.fixture(autouse=True)
def _no_template_gate(monkeypatch):
    monkeypatch.setattr(_rmparse, "DEFAULT_REQUIRED_SECTIONS", {})


@pytest.fixture(autouse=True)
def _no_owner_env(monkeypatch):
    """Claim owners (plan 40) default to $ROADMAP_OWNER, then the git user name,
    then an agent named by the environment — clear the env so the identity a test
    sees never depends on the shell (or agent) running the suite."""
    for var in ("ROADMAP_OWNER", "CLAUDECODE", "GEMINI_CLI"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def template_gate(monkeypatch):
    """Re-enable the shipped required-sections defaults for this test."""
    monkeypatch.setattr(_rmparse, "DEFAULT_REQUIRED_SECTIONS", dict(_DEFAULT_REQUIRED))


# The plan-43 acceptance gate is on for projects created by `init`. Most tests
# complete items on freshly initialised projects without marking acceptance, so
# new projects start without it here; tests that exercise it request
# `acceptance_gate` (or set settings.requireAcceptance themselves). Subprocess CLI
# tests don't see this patch — they mark bullets, pass --force, or turn it off.
import rmlib.project as _rmproject  # noqa: E402

_NEW_SETTINGS = dict(_rmproject.NEW_PROJECT_SETTINGS)


@pytest.fixture(autouse=True)
def _no_acceptance_gate(monkeypatch):
    monkeypatch.setattr(_rmproject, "NEW_PROJECT_SETTINGS",
                        {k: v for k, v in _NEW_SETTINGS.items()
                         if k != "requireAcceptance"})


@pytest.fixture
def acceptance_gate(monkeypatch):
    """Restore the shipped new-project settings (requireAcceptance on)."""
    monkeypatch.setattr(_rmproject, "NEW_PROJECT_SETTINGS", dict(_NEW_SETTINGS))
