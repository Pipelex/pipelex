"""How authored text is rendered as Python source: string literals and class docstrings.

The class-docstring contract is `inspect.getdoc(cls) == normalized_docstring_text(description)`, and
`normalized_docstring_text` is `inspect.cleandoc` over the text with each line's trailing spaces and tabs
removed. These tests pin both halves against known values, not only against each other.
"""

import ast
import inspect
import random

import pytest

from pipelex.tools.misc.python_literals import class_docstring, escape_py_string, normalized_docstring_text

# Characters `str.splitlines` treats as line breaks although `inspect.cleandoc` does not.
_SPLITLINES_ONLY_BREAKS = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]

# The alphabet the randomized round-trip draws from: quotes, backslashes, control characters, NUL, line
# separators, spaces and tabs for indentation, and ordinary letters.
_RANDOM_ALPHABET = [
    *_SPLITLINES_ONLY_BREAKS,
    "a",
    "b",
    " ",
    " ",
    "  ",
    "\t",
    "\n",
    "\n",
    "\r",
    "\r\n",
    '"',
    "'",
    '"""',
    "'''",
    "\\",
    "\x00",
    "\x07",
    "\x1b",
]


def _class_source(description: str) -> str:
    return f"class Described:\n{class_docstring(description)}\n"


def _rendered_docstring(description: str) -> str | None:
    """Render `description` as the docstring of a class, check the class is the module's only statement, and read it back."""
    source = _class_source(description)
    module = ast.parse(source)
    assert len(module.body) == 1
    class_def = module.body[0]
    assert isinstance(class_def, ast.ClassDef)
    assert len(class_def.body) == 1
    namespace: dict[str, object] = {}
    exec(compile(module, "<rendered>", "exec"), namespace)
    return inspect.getdoc(namespace["Described"])


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

    @pytest.mark.parametrize("character", _SPLITLINES_ONLY_BREAKS)
    def test_characters_other_than_newline_do_not_break_lines(self, character: str):
        description = f"before{character}after"

        assert normalized_docstring_text(description) == description


class TestClassDocstring:
    def test_relative_indentation_after_a_blank_first_line_reads_back(self):
        description = "\n  Intro:\n    - item one\n    - item two"

        assert _rendered_docstring(description) == "Intro:\n  - item one\n  - item two"

    def test_ordinary_multi_line_text_renders_verbatim_with_the_summary_on_the_first_line(self):
        description = "Summary line.\n\nDetails:\n  - first item\n  - second item"

        assert class_docstring(description) == '    """Summary line.\n\n    Details:\n      - first item\n      - second item\n    """'
        assert _rendered_docstring(description) == description

    @pytest.mark.parametrize(
        "description",
        [
            pytest.param("\nIntro:\n  - item one\n  - item two", id="every-later-line-indented"),
            pytest.param("\nIntro:\n\n  - item one", id="every-later-line-indented-after-a-blank-line"),
            pytest.param("\n  Deeper first line\n shallower line", id="first-line-deeper-than-the-rest"),
        ],
    )
    def test_text_whose_later_lines_share_an_indent_renders_escaped_and_opens_on_a_new_line(self, description: str):
        """The summary-first layout would lose the shared indent of the later lines, so the escaped one-line form is used."""
        rendered = class_docstring(description)

        assert rendered.startswith('    """\\n')
        assert "\n" not in rendered
        assert _rendered_docstring(description) == normalized_docstring_text(description)
        assert _rendered_docstring(description) == inspect.cleandoc(description)

    def test_text_whose_later_lines_share_no_indent_renders_verbatim(self):
        description = "\nIntro:\n  - item one\nclosing line"

        assert class_docstring(description) == '    """Intro:\n      - item one\n    closing line\n    """'
        assert _rendered_docstring(description) == "Intro:\n  - item one\nclosing line"

    def test_multi_line_text_ending_with_a_double_quote_keeps_the_double_quoted_delimiter(self):
        """The closing delimiter of a multi-line docstring sits on its own line, so the text's last quote never touches it."""
        description = 'First line\nends with "quoted"'

        assert class_docstring(description) == '    """First line\n    ends with "quoted"\n    """'

    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            pytest.param('"Quoted" at the start', '    """\\"Quoted\\" at the start"""', id="double-quote-first"),
            pytest.param('\'Quoted\' first, then """', '    """\'Quoted\' first, then \\"\\"\\""""', id="single-quote-first-beside-triple-quotes"),
            pytest.param(
                "A path C:\\dir\\\nand the next line", '    """A path C:\\\\dir\\\\\\n    and the next line"""', id="backslash-ending-a-line"
            ),
            pytest.param('Holds \\""" beside a backslash', '    """Holds \\\\\\"\\"\\" beside a backslash"""', id="backslash-beside-triple-quotes"),
        ],
    )
    def test_text_no_delimiter_leaves_unpadded_renders_escaped(self, description: str, expected: str):
        """`ruff format` pads an edge quote and reads a backslash in a raw docstring its own way, so such text is escaped."""
        assert class_docstring(description) == expected
        assert _rendered_docstring(description) == description

    @pytest.mark.parametrize("character", _SPLITLINES_ONLY_BREAKS)
    def test_characters_other_than_newline_read_back_unchanged(self, character: str):
        description = f"before{character}after\nsecond line{character}"

        assert _rendered_docstring(description) == description

    def test_randomized_descriptions_render_as_a_lone_docstring_that_reads_back(self):
        generator = random.Random(20261116)
        for _ in range(3000):
            description = "".join(generator.choice(_RANDOM_ALPHABET) for _ in range(generator.randint(0, 24)))
            assert _rendered_docstring(description) == normalized_docstring_text(description), repr(description)


class TestEscapePyString:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("plain", '"plain"', id="plain"),
            pytest.param("it's", '"it\'s"', id="single-quote"),
            pytest.param('say "hi"', "'say \"hi\"'", id="double-quotes"),
            pytest.param("'a' \"b\"", '"\'a\' \\"b\\""', id="tied-quotes"),
            pytest.param("back\\slash\nnewline", '"back\\\\slash\\nnewline"', id="backslash-and-newline"),
        ],
    )
    def test_escapes_as_ruff_leaves_it(self, value: str, expected: str):
        assert escape_py_string(value) == expected

    def test_randomized_values_evaluate_back_to_themselves(self):
        generator = random.Random(20261116)
        for _ in range(3000):
            value = "".join(generator.choice(_RANDOM_ALPHABET) for _ in range(generator.randint(0, 24)))
            literal = escape_py_string(value)
            assert ast.literal_eval(literal) == value, repr(value)
            assert literal[0] == ("'" if value.count("'") < value.count('"') else '"')
