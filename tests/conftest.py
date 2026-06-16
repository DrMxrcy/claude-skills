import importlib.util
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
def repo(tmp_path):
    """A hermetic temp git repo (no commit/tag signing, so tests don't touch the
    user's GPG/SSH signing agent)."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for key, val in (("user.email", "t@t.t"), ("user.name", "t"),
                     ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        subprocess.run(["git", "config", key, val], cwd=tmp_path, check=True)
    return tmp_path
