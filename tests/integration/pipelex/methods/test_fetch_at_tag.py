"""Integration tests for fetch-at-tag against a real local git repository.

Builds a git repository in tmp_path with a library-repo layout, tags it, moves the default
branch past the tag, and fetches through `fetch_method_package` with a `file://` clone URL —
exercising the real `clone_default_branch` / `clone_at_version` machinery and the commit-SHA
resolution, without any network.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

import pytest

from pipelex.methods.fetching import fetch_method_package
from pipelex.methods.method_ref import parse_method_ref

if TYPE_CHECKING:
    from pathlib import Path

MANIFEST_V1 = """\
[package]
name = "documents"
address = "github.com/Pipelex/methods"
version = "0.1.0"
description = "A test package."
main_pipe = "extract"

[exports.documents]
pipes = ["extract"]
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
    package_dir = repo_dir / "methods" / "documents"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(MANIFEST_V1, encoding="utf-8")
    (package_dir / "documents.mthds").write_text("# v1 placeholder", encoding="utf-8")

    _git(repo_dir, "init", "--initial-branch=main")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "v1")
    _git(repo_dir, "tag", "v0.1.0")
    tagged_sha = _git(repo_dir, "rev-parse", "HEAD")

    (package_dir / "documents.mthds").write_text("# v2 placeholder", encoding="utf-8")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "v2")
    head_sha = _git(repo_dir, "rev-parse", "HEAD")

    return repo_dir, tagged_sha, head_sha


class TestFetchAtTag:
    """Real-git integration: tag clone vs default-branch clone, with the SHA recorded."""

    def test_fetch_at_tag_records_the_tagged_commit(self, seed_repo: tuple[Path, str, str], tmp_path: Path) -> None:
        """Fetching `@v0.1.0` clones the tagged state and records the tagged commit SHA."""
        repo_dir, tagged_sha, head_sha = seed_repo

        fetched = fetch_method_package(
            ref=parse_method_ref("github.com/Pipelex/methods/documents@v0.1.0"),
            dest_dir=tmp_path / "clone-at-tag",
            clone_url=f"file://{repo_dir}",
        )

        assert fetched.commit_sha == tagged_sha
        assert fetched.commit_sha != head_sha
        assert fetched.provenance.tag == "v0.1.0"
        assert (fetched.package_dir / "documents.mthds").read_text(encoding="utf-8") == "# v1 placeholder"

    def test_fetch_bare_address_records_the_head_commit(self, seed_repo: tuple[Path, str, str], tmp_path: Path) -> None:
        """Fetching the bare address clones the default branch at HEAD and records that SHA."""
        repo_dir, tagged_sha, head_sha = seed_repo

        fetched = fetch_method_package(
            ref=parse_method_ref("github.com/Pipelex/methods/documents"),
            dest_dir=tmp_path / "clone-default",
            clone_url=f"file://{repo_dir}",
        )

        assert fetched.commit_sha == head_sha
        assert fetched.commit_sha != tagged_sha
        assert fetched.provenance.tag is None
        assert (fetched.package_dir / "documents.mthds").read_text(encoding="utf-8") == "# v2 placeholder"
