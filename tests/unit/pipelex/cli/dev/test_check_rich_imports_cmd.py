from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_rich_imports_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_rich_imports_cmd import check_rich_imports_cmd
from pipelex.cli.dev_cli.commands.rich_import_guard import REMEDY, RichImportViolation

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

#: Wide enough that no assertion below depends on where Rich decides to wrap.
CONSOLE_WIDTH = 400

VIOLATION = RichImportViolation(relative_path="pipelex/core/stuffs/sample_content.py", lineno=4, detail="imports `rich.json` at module level")


class TestCheckRichImportsCmd:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route every `get_console()` call in the command module to one StringIO-backed console."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    @pytest.mark.parametrize(
        ("quiet", "expected_verdict"),
        [
            (True, "Rich import check: PASSED"),
            (False, "Rich Import Check: PASSED"),
        ],
    )
    def test_a_clean_tree_passes(self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool, expected_verdict: str) -> None:
        """A clean tree returns normally, which is exit 0, and a quiet run says so in one line."""
        mocker.patch.object(cmd_mod, "collect_violations", return_value=[])
        check_rich_imports_cmd(quiet=quiet)
        output = console_buffer.getvalue()
        assert expected_verdict in output
        if quiet:
            assert output.strip().splitlines() == [f"✓ {expected_verdict}"]

    @pytest.mark.parametrize("quiet", [True, False])
    def test_a_violation_exits_1_with_its_site_and_the_remedy(self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool) -> None:
        """The gate: any violation is exit 1, and a quiet CI run still carries the site and the remedy."""
        mocker.patch.object(cmd_mod, "collect_violations", return_value=[VIOLATION])

        with pytest.raises(SystemExit) as exit_info:
            check_rich_imports_cmd(quiet=quiet)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "pipelex/core/stuffs/sample_content.py:4" in output
        assert "imports `rich.json` at module level" in output
        assert REMEDY in output
