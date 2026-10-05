"""Fixtures shared by the `PIPELEX_HOME` tests that run in this process.

`decoy_home` sets `HOME` to a directory holding a `.pipelex/` of its own, so that "nothing under the
real home is read" is a claim about a directory the test controls rather than about the developer's
machine.
"""

from pathlib import Path

import pytest

from pipelex.system.environment import PIPELEX_HOME_ENV_KEY


@pytest.fixture
def decoy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory whose `.pipelex/` holds a full configuration that no relocated read may touch."""
    home = tmp_path / "decoy-home"
    decoy_config_dir = home / ".pipelex"
    (decoy_config_dir / "inference").mkdir(parents=True)
    (decoy_config_dir / "pipelex.toml").write_text("[decoy_marker]\nseen = true\n", encoding="utf-8")
    (decoy_config_dir / "inference" / "backends.toml").write_text("[decoy]\n", encoding="utf-8")
    (decoy_config_dir / "inference" / "routing_profiles.toml").write_text("[decoy]\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv(PIPELEX_HOME_ENV_KEY, raising=False)
    return home


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project, the working directory, with a `.pipelex/` that carries no inference files."""
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".pipelex").mkdir()
    monkeypatch.chdir(project)
    return project
