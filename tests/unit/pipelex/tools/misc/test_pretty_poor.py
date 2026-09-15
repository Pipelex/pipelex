"""Tests for PrettyPrintMode.POOR -- plain text on stderr, whatever the title and the terminal width."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from pytest import CaptureFixture
from rich.table import Table

from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode, pretty_print

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# The title an operator pipe prints its output under (`pipe_operator.py`): its markup alone is wider than
# an 80-column terminal, which is the width a headless host reports.
OPERATOR_TITLE = "Output of pipe [red]summarize_the_text[/red] [yellow]→[/yellow] [bold green]Text[/bold green] [3 items]"
HEADLESS_TERMINAL_WIDTH = 80


def remove_ansi_escape_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


class TestPrettyPoor:
    @pytest.fixture(autouse=True)
    def _poor_mode(self):
        """Activate POOR mode for every test and restore afterwards."""
        original_mode = PrettyPrinter.mode
        PrettyPrinter.mode = PrettyPrintMode.POOR
        yield
        PrettyPrinter.mode = original_mode

    def test_a_title_wider_than_the_terminal_does_not_hang(self, capsys: CaptureFixture[str]) -> None:
        """The content width used to be the terminal width minus the title's length: a long title drove it
        to zero or below, and the wrapping loop never shortened a line again. The content must come out whole.
        """
        pretty_print("x" * 300, title="T" * 120, console_width=HEADLESS_TERMINAL_WIDTH)

        output = remove_ansi_escape_codes(capsys.readouterr().err)
        content_rows = [row.strip("│ ") for row in output.splitlines() if "x" in row]
        assert "".join(content_rows) == "x" * 300
        # Every row but the last fills the frame: the title's length takes nothing from the content's width.
        assert {len(row) for row in content_rows[:-1]} == {HEADLESS_TERMINAL_WIDTH - 8}

    def test_an_operator_title_prints_as_the_text_it_renders_to(self, capsys: CaptureFixture[str]) -> None:
        pretty_print("Hello", title=OPERATOR_TITLE, console_width=HEADLESS_TERMINAL_WIDTH)

        output = remove_ansi_escape_codes(capsys.readouterr().err)
        assert "Output of pipe summarize_the_text → Text [3 items]:" in output
        assert "[red]" not in output

    def test_stuff_content_prints_its_plain_rendering_without_building_a_renderable(self, mocker: MockerFixture, capsys: CaptureFixture[str]) -> None:
        rendered_pretty_mock = mocker.patch.object(TextContent, "rendered_pretty")

        TextContent(text="Hello **world**").pretty_print_content(title="Text")

        rendered_pretty_mock.assert_not_called()
        output = remove_ansi_escape_codes(capsys.readouterr().err)
        assert "Hello **world**" in output
        assert "object at 0x" not in output

    def test_structured_stuff_content_prints_text_not_a_repr(self, capsys: CaptureFixture[str]) -> None:
        NumberContent(number=3).pretty_print_content(title="Number")

        output = remove_ansi_escape_codes(capsys.readouterr().err)
        assert "3" in output
        assert "object at 0x" not in output

    def test_a_rich_renderable_prints_as_its_text(self, capsys: CaptureFixture[str]) -> None:
        table = Table("Pipe")
        table.add_row("summarize_the_text")

        pretty_print(table, title="Pipes", console_width=HEADLESS_TERMINAL_WIDTH)

        output = remove_ansi_escape_codes(capsys.readouterr().err)
        assert "summarize_the_text" in output
        assert "object at 0x" not in output
