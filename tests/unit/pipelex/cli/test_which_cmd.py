"""Unit tests for `pipelex which` pipe-location logic (pipelex/cli/commands/which_cmd.py)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.which_cmd import do_which_pipe

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestWhichCmd:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        recorded_console = Console(width=300, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.which_cmd.get_console", return_value=recorded_console)
        return recorded_console

    def test_pipe_found_with_source(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """A found pipe reports type, domain and source, and returns True."""
        fake_pipe = SimpleNamespace(pipe_type="PipeLLM", domain_code="demo")
        mocker.patch("pipelex.cli.commands.which_cmd.get_optional_pipe", return_value=fake_pipe)
        mocker.patch("pipelex.cli.commands.which_cmd.get_pipe_source", return_value=str(tmp_path / "demo.mthds"))

        found = do_which_pipe(pipe_code="demo.my_pipe", library_dirs=[tmp_path], source_label="--library-dir")

        assert found is True
        output = console.export_text()
        assert "Search path for 'demo.my_pipe':" in output
        assert "✓" in output
        assert "(--library-dir)" in output
        assert "Found: demo.my_pipe" in output
        assert "Type: PipeLLM" in output
        assert "Domain: demo" in output
        assert "Source:" in output
        assert "demo.mthds" in output

    def test_pipe_found_without_source(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """A found pipe with no known source path omits the Source line."""
        fake_pipe = SimpleNamespace(pipe_type="PipeLLM", domain_code="demo")
        mocker.patch("pipelex.cli.commands.which_cmd.get_optional_pipe", return_value=fake_pipe)
        mocker.patch("pipelex.cli.commands.which_cmd.get_pipe_source", return_value=None)

        found = do_which_pipe(pipe_code="demo.my_pipe", library_dirs=[tmp_path], source_label="PIPELEXPATH")

        assert found is True
        assert "Source:" not in console.export_text()

    def test_pipe_not_found(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """A missing pipe returns False and prints the search tip."""
        mocker.patch("pipelex.cli.commands.which_cmd.get_optional_pipe", return_value=None)

        found = do_which_pipe(pipe_code="ghost_pipe", library_dirs=[tmp_path], source_label="PIPELEXPATH")

        assert found is False
        output = console.export_text()
        assert "Not found: ghost_pipe" in output
        assert "PIPELEXPATH or passed via --library-dir" in output

    def test_empty_library_dirs(self, mocker: MockerFixture, console: Console) -> None:
        """An empty search path is reported explicitly."""
        mocker.patch("pipelex.cli.commands.which_cmd.get_optional_pipe", return_value=None)

        found = do_which_pipe(pipe_code="any_pipe", library_dirs=[], source_label="defaults")

        assert found is False
        assert "(no directories configured)" in console.export_text()

    def test_nonexistent_directory_marked(self, mocker: MockerFixture, console: Console, tmp_path: Path) -> None:
        """Directories missing on disk are marked with a red cross but still listed."""
        mocker.patch("pipelex.cli.commands.which_cmd.get_optional_pipe", return_value=None)
        missing_dir = tmp_path / "does-not-exist"

        do_which_pipe(pipe_code="any_pipe", library_dirs=[tmp_path, missing_dir], source_label="defaults")

        output = console.export_text()
        assert "✓" in output
        assert "✗" in output
        assert str(missing_dir) in output
