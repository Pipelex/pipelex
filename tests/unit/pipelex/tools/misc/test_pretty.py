import re
import textwrap

import pytest
from pytest import CaptureFixture

from pipelex.tools.misc.pretty import pretty_print
from tests.unit.pipelex.tools.misc.conftest import ComplexUser


def remove_ansi_escape_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


@pytest.fixture
def widths() -> tuple[int, int]:
    """Return tuple of (width, console_width) for pretty print tests."""
    return (180, 200)


class TestPrettyPrint:
    def test_pretty_print_with_brackets_optional_edge_case(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="Optional[float]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)
        expected_output = textwrap.dedent("""\

            ╭─ title ─────────╮
            │                 │
            │ Optional[float] │
            │                 │
            ╰─────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_brackets_basic(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="SomethingBeforeBracketsAnd[SomethingBetweenBrackets]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ──────────────────────────────────────────────╮
            │                                                      │
            │ SomethingBeforeBracketsAnd[SomethingBetweenBrackets] │
            │                                                      │
            ╰──────────────────────────────────────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_nested_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="List[Optional[int]]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ─────────────╮
            │                     │
            │ List[Optional[int]] │
            │                     │
            ╰─────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_multiple_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="Union[str, List[int], Dict[str, Any]]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ───────────────────────────────╮
            │                                       │
            │ Union[str, List[int], Dict[str, Any]] │
            │                                       │
            ╰───────────────────────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_special_chars_and_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="@decorator[*args, **kwargs]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ─────────────────────╮
            │                             │
            │ @decorator[*args, **kwargs] │
            │                             │
            ╰─────────────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_empty_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="List[]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ─╮
            │         │
            │ List[]  │
            │         │
            ╰─────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_unmatched_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="Unmatched[bracket", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ───────────╮
            │                   │
            │ Unmatched[bracket │
            │                   │
            ╰───────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_with_unicode_and_brackets(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        pretty_print(content="🐍Python[版本3.11]", title="title", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ title ────────────╮
            │                    │
            │ 🐍Python[版本3.11] │
            │                    │
            ╰────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_pydantic_object(self, complex_user: ComplexUser, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths

        pretty_print(content=complex_user, title="Complex User", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""
            ╭─ Complex User ──────────────────────────────────────────────────────────────────────────────────╮
            │                                                                                                 │
            │ ComplexUser(                                                                                    │
            │     name='John Doe',                                                                            │
            │     age=30,                                                                                     │
            │     email='john@example.com',                                                                   │
            │     addresses=[                                                                                 │
            │         Address(street='123 Main St', city='Springfield', country='USA', postal_code='12345'),  │
            │         Address(street='456 Side St', city='Brooklyn', country='USA', postal_code=None)         │
            │     ],                                                                                          │
            │     preferences=UserPreferences(                                                                │
            │         theme='light',                                                                          │
            │         notifications=False,                                                                    │
            │         tags=['python', 'coding']                                                               │
            │     ),                                                                                          │
            │     metadata={'last_login': '2024-03-20', 'login_count': 42, 'is_active': True}                 │
            │ )                                                                                               │
            │                                                                                                 │
            ╰─────────────────────────────────────────────────────────────────────────────────────────────────╯

        """)

        assert output == expected_output, f"Make sure you enable pytest '-s' option. Output did not match expected:\n{output}"
