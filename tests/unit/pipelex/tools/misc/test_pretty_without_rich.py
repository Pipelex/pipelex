import re
import textwrap

import pytest
from pytest import CaptureFixture

from pipelex.tools.misc.pretty import PrettyPrinter
from tests.unit.pipelex.tools.misc.conftest import ComplexUser


def remove_ansi_escape_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


@pytest.fixture
def widths() -> tuple[int, int]:
    """Return tuple of (width, console_width) for pretty print tests."""
    return (100, 150)


class TestPrettyPrintWithoutRich:
    def test_pretty_without_rich_empty_content(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        PrettyPrinter.pretty_print_without_rich(content="", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.err)

        expected_output = textwrap.dedent("""\
            ╭────╮
            │    │
            ╰────╯
        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_without_rich_none_content(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        PrettyPrinter.pretty_print_without_rich(content=None, title="title", subtitle="subtitle", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.err)

        expected_output = textwrap.dedent("""\
            ╭────────────╮
            │ title:     │
            │ subtitle:  │
            │ None       │
            ╰────────────╯
        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_without_rich_pydantic_object(self, complex_user: ComplexUser, widths: tuple[int, int], capsys: CaptureFixture[str]):
        width, console_width = widths
        PrettyPrinter.pretty_print_without_rich(content=complex_user, title="Complex User", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.err)

        expected_output = textwrap.dedent("""\
            ╭────────────────────────────────────────────────────────────────────────────────────────────────────────╮
            │ Complex User:                                                                                          │
            │ name='John Doe' age=30 email='john@example.com' addresses=[Address(street='123 Main St', city='Sprin   │
            │ gfield', country='USA', postal_code='12345'), Address(street='456 Side St', city='Brooklyn', country   │
            │ ='USA', postal_code=None)] preferences=UserPreferences(theme='light', notifications=False, tags=['py   │
            │ thon', 'coding']) metadata={'last_login': '2024-03-20', 'login_count': 42, 'is_active': True}          │
            ╰────────────────────────────────────────────────────────────────────────────────────────────────────────╯
        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"
