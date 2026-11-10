"""Run every test against a throwaway data folder holding a freshly built example project."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

TOOLBOX = Path(__file__).resolve().parent.parent
_HOME = Path(tempfile.mkdtemp(prefix="3d-agent-test-"))
os.environ["THREED_AGENT_HOME"] = str(_HOME)
os.environ.setdefault("TB_CACHE_DIR", str(_HOME / "cache"))
sys.path.insert(0, str(TOOLBOX))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def example_project():
    from tb import cad

    shutil.copytree(TOOLBOX.parent / "examples" / "mif4-cradle", _HOME / "projects" / "mif4-cradle")
    result = cad.cad_build("mif4-cradle", show=False)
    assert result["ok"], result
    yield _HOME
    shutil.rmtree(_HOME, ignore_errors=True)
