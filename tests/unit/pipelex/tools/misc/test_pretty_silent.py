"""Tests for PrettyPrintMode.SILENT -- no console output, rendering unaffected."""

from __future__ import annotations

import pytest
from pytest import CaptureFixture
from rich.text import Text

from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode, pretty_print


class TestPrettySilent:
    @pytest.fixture(autouse=True)
    def _silent_mode(self):
        """Activate SILENT mode for every test and restore afterwards."""
        original_mode = PrettyPrinter.mode
        PrettyPrinter.mode = PrettyPrintMode.SILENT
        yield
        PrettyPrinter.mode = original_mode

    def test_silent_mode_produces_no_stdout(self, capsys: CaptureFixture[str]) -> None:
        """pretty_print should produce zero output when mode is SILENT."""
        pretty_print(content="Hello world", title="Greeting", width=60, console_width=80)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_silent_mode_produces_no_stdout_for_dict(self, capsys: CaptureFixture[str]) -> None:
        """Dicts should also be suppressed."""
        pretty_print(content={"key": "value"}, title="Dict", width=60, console_width=80)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_pretty_text_still_works_in_silent_mode(self) -> None:
        """Rendering to string via pretty_text should be unaffected by SILENT mode."""
        renderable = Text("Hello from silent")
        result = PrettyPrinter.pretty_text(renderable)
        assert "Hello from silent" in result

    def test_pretty_html_still_works_in_silent_mode(self) -> None:
        """Rendering to HTML string should be unaffected by SILENT mode."""
        renderable = Text("Hello HTML")
        result = PrettyPrinter.pretty_html(renderable)
        assert "Hello HTML" in result
