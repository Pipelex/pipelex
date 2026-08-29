"""Integration tests for fetch-on-miss against a real local git repository.

Builds a git repository in tmp_path with a library-repo layout, tags it, moves the default
branch past the tag, and resolves an address-based reference through
`resolve_address_based_method` — exercising the real clone machinery (with the clone URL
redirected to a `file://` fixture), the tag pin, the install into the (redirected) global
methods directory, and the provenance sidecar. No network.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.installed_methods import PROVENANCE_FILENAME
from pipelex.methods.fetch_on_miss import resolve_address_based_method
from pipelex.methods.fetching import FetchedMethodPackage, MethodProvenance, fetch_method_package

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from pipelex.methods.method_ref import MethodRef

FULL_ADDRESS = "github.com/pipelex-tests/fom-git-methods/scoring"

MANIFEST_V1 = """\
[package]
name = "scoring"
address = "github.com/pipelex-tests/fom-git-methods"
version = "0.1.0"
description = "A test package."
main_pipe = "compute"

[exports.scoring]
pipes = ["compute"]
"""


def _git(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        ["git", "-C", str(repo_dir), *args],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


@pytest.fixture(name="seed_repo")
def seed_repo_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    """A local git repo with one package, a v0.1.0 tag, and a later commit on the default branch.

    Returns (repo_dir, tagged_commit_sha, head_commit_sha).
    """
    repo_dir = tmp_path / "seed-repo"
    package_dir = repo_dir / "methods" / "scoring"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(MANIFEST_V1, encoding="utf-8")
    (package_dir / "scoring.mthds").write_text("# v1 placeholder", encoding="utf-8")

    _git(repo_dir, "init", "--initial-branch=main")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "v1")
    _git(repo_dir, "tag", "-a", "v0.1.0", "-m", "release v0.1.0")
    tagged_sha = _git(repo_dir, "rev-parse", "HEAD")

    (package_dir / "scoring.mthds").write_text("# v2 placeholder", encoding="utf-8")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "v2")
    head_sha = _git(repo_dir, "rev-parse", "HEAD")

    return repo_dir, tagged_sha, head_sha


class TestFetchOnMissWithRealGit:
    def test_miss_fetches_at_tag_installs_and_reuses(self, seed_repo: tuple[Path, str, str], tmp_path: Path, mocker: MockerFixture) -> None:
        """A tag-pinned miss clones the tagged state, installs it with SHA provenance, and later resolves reuse the install."""
        repo_dir, tagged_sha, head_sha = seed_repo
        global_dir = tmp_path / "global-methods"
        mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", global_dir)
        mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
        mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=True)

        def fetch_via_fixture(*, ref: MethodRef, dest_dir: Path, refuse_structures: bool = False) -> FetchedMethodPackage:
            return fetch_method_package(ref=ref, dest_dir=dest_dir, clone_url=f"file://{repo_dir}", refuse_structures=refuse_structures)

        fetch_spy = mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=fetch_via_fixture)

        resolved = resolve_address_based_method(full_address=f"{FULL_ADDRESS}@v0.1.0")

        assert resolved.path == (global_dir / "scoring").resolve()
        assert (resolved.path / "scoring.mthds").read_text(encoding="utf-8") == "# v1 placeholder"
        assert not (resolved.path / ".git").exists()
        provenance = MethodProvenance.model_validate_json((resolved.path / PROVENANCE_FILENAME).read_text(encoding="utf-8"))
        assert provenance.commit_sha == tagged_sha
        assert provenance.commit_sha != head_sha
        assert provenance.tag == "v0.1.0"
        assert provenance.address == FULL_ADDRESS
        assert fetch_spy.call_count == 1

        # A later resolve — tagless this time — hits the install and never fetches again.
        resolved_again = resolve_address_based_method(full_address=FULL_ADDRESS)
        assert resolved_again.path == resolved.path
        assert fetch_spy.call_count == 1
