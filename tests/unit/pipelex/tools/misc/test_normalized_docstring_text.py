"""`normalized_docstring_text`: the authored text as `inspect.getdoc` reads it back once rendered as a class docstring."""

import inspect

import pytest

from pipelex.tools.misc.python_literals import normalized_docstring_text
from tests.unit.pipelex.tools.misc.cases import PythonLiteralsCases


class TestNormalizedDocstringText:
    def test_relative_indentation_after_a_blank_first_line_is_kept(self):
        description = "\n  Intro:\n    - item one\n    - item two"

        assert normalized_docstring_text(description) == "Intro:\n  - item one\n  - item two"
        assert normalized_docstring_text(description) == inspect.cleandoc(description)

    def test_trailing_spaces_and_tabs_are_removed_from_each_line(self):
        assert normalized_docstring_text("Summary  \n  body\t\n") == "Summary\nbody"

    @pytest.mark.parametrize("line_break", ["\r\n", "\r"])
    def test_carriage_return_line_breaks_become_newlines(self, line_break: str):
        assert normalized_docstring_text(f"first{line_break}second") == "first\nsecond"

    @pytest.mark.parametrize("character", PythonLiteralsCases.SPLITLINES_ONLY_BREAKS)
    def test_characters_other_than_newline_do_not_break_lines(self, character: str):
        description = f"before{character}after"

        assert normalized_docstring_text(description) == description
