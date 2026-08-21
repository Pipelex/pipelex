"""Unit tests for the drift git adapter: index reads, OID semantics, failure paths."""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.drift.exceptions import DriftGitError
from pipelex.cli.dev_cli.commands.drift.git_adapter import (
    get_git_user_name,
    get_repo_toplevel,
    read_staged_files,
    read_unstaged_modified,
    read_untracked,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests.unit.pipelex.cli.dev.conftest import GitRepo

ADAPTER_MODULE = "pipelex.cli.dev_cli.commands.drift.git_adapter"


class TestDriftGitAdapter:
    def test_read_staged_files_maps_paths_to_blob_oids(self, git_repo: GitRepo) -> None:
        git_repo.write_and_commit("docs/page.md", content="# Page\n")
        git_repo.write("pipelex/mod.py", content="x = 1\n")
        git_repo.add("pipelex/mod.py")
        staged = read_staged_files(git_repo.root)
        assert set(staged) == {"docs/page.md", "pipelex/mod.py"}
        for oid in staged.values():
            assert oid.startswith("blob:")
            assert len(oid) == len("blob:") + 40

    def test_staged_edit_changes_oid_unstaged_does_not(self, git_repo: GitRepo) -> None:
        """Digest source is the index: a staged edit is reflected, an unstaged edit is NOT."""
        git_repo.write_and_commit("pipelex/mod.py", content="x = 1\n")
        oid_initial = read_staged_files(git_repo.root)["pipelex/mod.py"]

        git_repo.write("pipelex/mod.py", content="x = 2\n")
        oid_after_unstaged_edit = read_staged_files(git_repo.root)["pipelex/mod.py"]
        assert oid_after_unstaged_edit == oid_initial

        git_repo.add("pipelex/mod.py")
        oid_after_staging = read_staged_files(git_repo.root)["pipelex/mod.py"]
        assert oid_after_staging != oid_initial

    def test_untracked_files_are_absent_from_index(self, git_repo: GitRepo) -> None:
        git_repo.write_and_commit("tracked.md", content="tracked\n")
        git_repo.write("untracked.md", content="untracked\n")
        staged = read_staged_files(git_repo.root)
        assert "untracked.md" not in staged
        assert read_untracked(git_repo.root) == ["untracked.md"]

    def test_read_unstaged_modified(self, git_repo: GitRepo) -> None:
        git_repo.write_and_commit("a.md", content="one\n")
        git_repo.write_and_commit("b.md", content="two\n")
        git_repo.write("a.md", content="one-edited\n")
        assert read_unstaged_modified(git_repo.root) == ["a.md"]

    def test_get_repo_toplevel(self, git_repo: GitRepo) -> None:
        git_repo.write_and_commit("a.md", content="one\n")
        nested = git_repo.root / "docs"
        nested.mkdir(exist_ok=True)
        assert get_repo_toplevel(cwd=nested).resolve() == git_repo.root.resolve()

    def test_not_a_git_repo_is_actionable_error(self, tmp_path: Path) -> None:
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        with pytest.raises(DriftGitError, match="git"):
            read_staged_files(plain_dir)

    def test_missing_git_binary_is_actionable_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch(f"{ADAPTER_MODULE}.subprocess.run", side_effect=FileNotFoundError("git"))
        with pytest.raises(DriftGitError, match="not found"):
            read_staged_files(tmp_path)

    def test_git_timeout_is_actionable_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch(f"{ADAPTER_MODULE}.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
        with pytest.raises(DriftGitError, match="timed out"):
            read_staged_files(tmp_path)

    def test_malformed_ls_files_output_is_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        completed = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="no-tab-entry\0", stderr="")
        mocker.patch(f"{ADAPTER_MODULE}.subprocess.run", return_value=completed)
        with pytest.raises(DriftGitError, match=r"[Mm]alformed"):
            read_staged_files(tmp_path)

    def test_unmerged_index_entry_is_actionable_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        stdout = "100644 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 1\tconflicted.py\0"
        completed = subprocess.CompletedProcess(args=["git"], returncode=0, stdout=stdout, stderr="")
        mocker.patch(f"{ADAPTER_MODULE}.subprocess.run", return_value=completed)
        with pytest.raises(DriftGitError, match=r"[Uu]nmerged"):
            read_staged_files(tmp_path)

    def test_get_git_user_name_configured(self, git_repo: GitRepo) -> None:
        assert get_git_user_name(git_repo.root) == "Test User"

    def test_get_git_user_name_unset_returns_none(self, git_repo: GitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
        """With local user.name unset and host global/system config masked, the name resolves to None."""
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
        git_repo.git("config", "--unset", "user.name")
        assert get_git_user_name(git_repo.root) is None
