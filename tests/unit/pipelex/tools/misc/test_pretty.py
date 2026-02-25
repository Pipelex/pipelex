import re
import textwrap

import pytest
from pytest import CaptureFixture

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.pretty import pretty_print
from tests.unit.pipelex.tools.misc.conftest import ComplexUser
from tests.unit.pipelex.tools.misc.test_data import ImageData


def remove_ansi_escape_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


@pytest.fixture
def widths() -> tuple[int, int]:
    """Return tuple of (width, console_width) for pretty print tests."""
    return (60, 80)


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
        """Test that BaseModel objects are rendered with Rich's Pretty formatting.

        Note: BaseModel objects are wrapped with make_truncated_wrapper to provide
        truncation of long values while preserving the original class name.
        """
        width, console_width = widths
        pretty_print(content=complex_user, title="Complex User", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\

            ╭─ Complex User ──────────────────────╮
            │                                     │
            │ ComplexUser(                        │
            │     name='John Doe',                │
            │     age=30,                         │
            │     email='john@example.com',       │
            │     addresses=[                     │
            │         Address(                    │
            │             street='123 Main St',   │
            │             city='Springfield',     │
            │             country='USA',          │
            │             postal_code='12345'     │
            │         ),                          │
            │         Address(                    │
            │             street='456 Side St',   │
            │             city='Brooklyn',        │
            │             country='USA',          │
            │             postal_code=None        │
            │         )                           │
            │     ],                              │
            │     preferences=UserPreferences(    │
            │         theme='light',              │
            │         notifications=False,        │
            │         tags=['python', 'coding']   │
            │     ),                              │
            │     metadata={                      │
            │         'last_login': '2024-03-20', │
            │         'login_count': 42,          │
            │         'is_active': True           │
            │     }                               │
            │ )                                   │
            │                                     │
            ╰─────────────────────────────────────╯

        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_pretty_print_pydantic_with_base64_truncation(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        """Test that long base64 strings are truncated in pretty print output."""
        # Create a long base64 string (typical for images)
        long_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" * 100
        image_data = ImageData(
            name="test_image.png",
            base_64=long_base64,
            url="data:image/png;base64," + long_base64,
        )

        width, console_width = widths
        pretty_print(content=image_data, title="Image Data", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Verify the full long strings are NOT in output (truncation worked)
        assert long_base64 not in output
        # Verify the output contains the data URL prefix (url field is present)
        assert "data:image/png;base64," in output
        # Verify the output is reasonably sized (not megabytes of base64)
        assert len(output) < 2000  # Should be much smaller than original

    def test_pretty_print_dict_with_base64_truncation(self, widths: tuple[int, int], capsys: CaptureFixture[str]):
        """Test that long base64 strings in dicts are also truncated."""
        long_base64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" * 50
        data = {
            "name": "test",
            "base_64": long_base64,
            "url": "data:image/jpeg;base64," + long_base64,
        }

        width, console_width = widths
        pretty_print(content=data, title="Dict with Base64", width=width, console_width=console_width)

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Verify the base_64 field is truncated (field name triggers truncation)
        assert long_base64 not in output
        # Verify the output is reasonably sized
        assert len(output) < 2000

    def test_attribute_polisher_should_truncate_any_long_string(self):
        """Test the base64 detection logic for long strings."""
        # Pure base64 string should be detected
        base64_str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" * 20
        assert AttributePolisher.should_truncate(value=base64_str)

        # Normal text should not be detected even if long
        normal_text = "This is a normal text with spaces and punctuation! " * 20
        assert not AttributePolisher.should_truncate(value=normal_text)

        # Data URL should be detected
        data_url = "data:image/png;base64," + base64_str
        assert AttributePolisher.should_truncate(value=data_url)

        # Short strings should not be truncated
        short_base64 = "iVBORw0KGgoAAAANSUhEUg=="
        assert not AttributePolisher.should_truncate(value=short_base64)
