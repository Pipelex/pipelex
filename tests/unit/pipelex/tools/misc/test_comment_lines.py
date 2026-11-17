import pytest

from pipelex.tools.misc.python_literals import comment_lines


class TestCommentLines:
    """`comment_lines` splits on every line break Python's `str.splitlines` knows."""

    @pytest.mark.parametrize("line_break", ["\r\n", "\r", "\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "])
    def test_every_line_break_splits_the_comment(self, line_break: str):
        """Each line break ends a line of the comment, so the text after it is a line of its own."""
        assert comment_lines(f"first{line_break}second") == ["first", "second"]

    def test_text_without_a_line_break_is_one_line(self):
        """A text with no line break is a single comment line, and an empty text is one empty line."""
        assert comment_lines("one line  ") == ["one line"]
        assert comment_lines("") == [""]
