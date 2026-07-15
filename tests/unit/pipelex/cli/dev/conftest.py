"""Shared fixtures for dev CLI unit tests: a real temporary git repository."""

from __future__ import annotations

import subprocess  # noqa: S404
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class GitRepo:
    """A disposable git repository under tmp_path, with staging/commit helpers."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def git(self, *args: str) -> str:
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        return result.stdout

    def write(self, relative_path: str, *, content: str) -> Path:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def add(self, *paths: str) -> None:
        self.git("add", "--", *paths)

    def add_all(self) -> None:
        self.git("add", "-A")

    def commit(self, message: str = "test commit") -> None:
        self.git("commit", "-q", "--no-verify", "-m", message)

    def write_and_commit(self, relative_path: str, *, content: str) -> Path:
        target = self.write(relative_path, content=content)
        self.add(relative_path)
        self.commit(f"add {relative_path}")
        return target


@pytest.fixture
def drift_console(mocker: MockerFixture) -> Console:
    """A recording console patched into the drift command module (the hub console binds stdout at creation)."""
    recorded_console = Console(width=200, record=True, color_system=None)
    mocker.patch("pipelex.cli.dev_cli.commands.drift.drift_cmd.get_console", return_value=recorded_console)
    return recorded_console


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    """A fresh git repository with local identity configured (independent of the host's config)."""
    root = tmp_path / "repo"
    root.mkdir()
    repo = GitRepo(root)
    repo.git("init", "-q")
    repo.git("config", "user.name", "Test User")
    repo.git("config", "user.email", "test@example.com")
    repo.git("config", "commit.gpgsign", "false")
    return repo
