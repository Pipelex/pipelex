# ruff: noqa: S404, S603, S607 — test fixture uses subprocess to build a local bare git repo
"""Fixtures for VCS integration tests.

Creates bare git repositories with tagged versions, accessible via file:// protocol.
"""

import subprocess
from pathlib import Path

import pytest

from tests.integration.pipelex.core.packages.test_vcs_data import DependentFixtureData, VCSFixtureData


@pytest.fixture(scope="class")
def bare_git_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a bare git repo with two tagged versions (v1.0.0, v1.1.0).

    The repo contains METHODS.toml and a .mthds bundle file at each version.
    Returns the ``file://`` URL suitable for git operations.
    """
    base = tmp_path_factory.mktemp("vcs_fixture")
    bare_path = base / "repo.git"
    work_path = base / "work"

    # Create bare repo
    subprocess.run(["git", "init", "--bare", str(bare_path)], check=True, capture_output=True)

    # Create working clone
    subprocess.run(["git", "clone", str(bare_path), str(work_path)], check=True, capture_output=True)

    # Configure git user for commits
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work_path, check=True, capture_output=True)

    # --- v1.0.0 ---
    (work_path / "METHODS.toml").write_text(VCSFixtureData.METHODS_TOML)
    mthds_dir = work_path / ".mthds"
    mthds_dir.mkdir(exist_ok=True)
    (mthds_dir / "main.mthds").write_text(VCSFixtureData.BUNDLE_CONTENT)

    subprocess.run(["git", "add", "-A"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1.0.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD", "--tags"], cwd=work_path, check=True, capture_output=True)

    # --- v1.1.0 ---
    (work_path / "METHODS.toml").write_text(VCSFixtureData.METHODS_TOML_V110)
    (mthds_dir / "main.mthds").write_text(VCSFixtureData.BUNDLE_CONTENT_V110)

    subprocess.run(["git", "add", "-A"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1.1.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v1.1.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD", "--tags"], cwd=work_path, check=True, capture_output=True)

    return bare_path


@pytest.fixture(scope="class")
def bare_git_repo_url(bare_git_repo: Path) -> str:
    """Return the file:// URL for the bare git repo fixture."""
    return f"file://{bare_git_repo}"


@pytest.fixture(scope="class")
def bare_git_repo_dependent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a bare git repo for dependent-pkg with v1.0.0.

    This package declares a dependency on vcs-fixture.
    """
    base = tmp_path_factory.mktemp("dependent_fixture")
    bare_path = base / "dependent.git"
    work_path = base / "work"

    subprocess.run(["git", "init", "--bare", str(bare_path)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(bare_path), str(work_path)], check=True, capture_output=True)

    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work_path, check=True, capture_output=True)

    # --- v1.0.0 ---
    (work_path / "METHODS.toml").write_text(DependentFixtureData.METHODS_TOML)
    mthds_dir = work_path / ".mthds"
    mthds_dir.mkdir(exist_ok=True)
    (mthds_dir / "main.mthds").write_text(DependentFixtureData.BUNDLE_CONTENT)

    subprocess.run(["git", "add", "-A"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1.0.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=work_path, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD", "--tags"], cwd=work_path, check=True, capture_output=True)

    return bare_path


@pytest.fixture(scope="class")
def bare_git_repo_dependent_url(bare_git_repo_dependent: Path) -> str:
    """Return the file:// URL for the dependent bare git repo."""
    return f"file://{bare_git_repo_dependent}"


@pytest.fixture(scope="class")
def transitive_url_overrides(bare_git_repo_url: str, bare_git_repo_dependent_url: str) -> dict[str, str]:
    """URL override map for both fixture repos."""
    return {
        "github.com/mthds-test/vcs-fixture": bare_git_repo_url,
        "github.com/mthds-test/dependent-pkg": bare_git_repo_dependent_url,
    }
