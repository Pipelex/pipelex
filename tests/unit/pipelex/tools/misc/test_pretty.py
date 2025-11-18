import re
import textwrap

import pytest
from pydantic import BaseModel, Field
from pytest import CaptureFixture

from pipelex.tools.misc.pretty import PrettyPrinter, pretty_print


class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: str | None = None


class UserPreferences(BaseModel):
    theme: str = "dark"
    notifications: bool = True
    tags: list[str] = Field(default_factory=list)


class ComplexUser(BaseModel):
    name: str
    age: int
    email: str | None
    addresses: list[Address]
    preferences: UserPreferences
    metadata: dict[str, str | int | bool] = Field(default_factory=dict)


def remove_ansi_escape_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


class TestPrettyPrint:
    def test_pretty_print_with_brackets_optional_edge_case(self, capsys: CaptureFixture[str]):
        pretty_print(content="Optional[float]", title="title")

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

    def test_pretty_print_with_brackets_basic(self, capsys: CaptureFixture[str]):
        pretty_print(content="SomethingBeforeBracketsAnd[SomethingBetweenBrackets]", title="title")

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

    def test_pretty_print_with_nested_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="List[Optional[int]]", title="title")

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

    def test_pretty_print_with_multiple_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="Union[str, List[int], Dict[str, Any]]", title="title")

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

    def test_pretty_print_with_special_chars_and_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="@decorator[*args, **kwargs]", title="title")

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

    def test_pretty_print_with_empty_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="List[]", title="title")

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

    def test_pretty_print_with_unmatched_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="Unmatched[bracket", title="title")

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

    def test_pretty_print_with_unicode_and_brackets(self, capsys: CaptureFixture[str]):
        pretty_print(content="🐍Python[版本3.11]", title="title")

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

    # This test needs output to be displayed, so we disabled it by default in pyproject.toml
    # So to run it you must bypass the marker restrictions defined in the pyproject.toml pytest section
    # and make sure you turn on outputs with -s like this:
    # pytest -m "" -k test_pretty_print_pydantic_object -s
    @pytest.mark.gha_disabled
    @pytest.mark.codex_disabled
    @pytest.mark.needs_output
    def test_pretty_print_pydantic_object(self, capsys: CaptureFixture[str]):
        # Create a complex nested object
        user = ComplexUser(
            name="John Doe",
            age=30,
            email="john@example.com",
            addresses=[
                Address(street="123 Main St", city="Springfield", country="USA", postal_code="12345"),
                Address(street="456 Side St", city="Brooklyn", country="USA"),
            ],
            preferences=UserPreferences(theme="light", notifications=False, tags=["python", "coding"]),
            metadata={"last_login": "2024-03-20", "login_count": 42, "is_active": True},
        )

        pretty_print(content=user, title="Complex User")

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        expected_output = textwrap.dedent("""\
            ╭─ Complex User ──────────────────────────────────────────────────────────────────────────────────╮
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
            ╰─────────────────────────────────────────────────────────────────────────────────────────────────╯
        """)

        assert output == expected_output, f"Make sure you enable pytest '-s' option. Output did not match expected:\n{output}"


class TestPrettyPrintInSandbox:
    def test_empty_content(self, capsys: CaptureFixture[str]):
        PrettyPrinter.pretty_print_without_rich(content="")

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.err)

        expected_output = textwrap.dedent("""\
            ╭────╮
            │    │
            ╰────╯
        """)

        assert output == expected_output, f"Output did not match expected:\n{output}"

    def test_none_content(self, capsys: CaptureFixture[str]):
        PrettyPrinter.pretty_print_without_rich(content=None, title="title", subtitle="subtitle")

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
