import pytest

from pipelex.tools.misc.string_utils import (
    camel_to_snake_case,
    can_inject_text,
    is_none_or_has_text,
    is_not_none_and_has_text,
    is_pascal_case,
    is_snake_case,
    pascal_case_to_sentence,
    pascal_case_to_snake_case,
    snake_to_capitalize_first_letter,
    snake_to_pascal_case,
)


class BadStr:
    def __str__(self) -> str:  # pyright: ignore[reportImplicitOverride] pragma: no cover - used only for raising
        raise RuntimeError("boom")


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, True),
        ("abc", True),
        ("", False),
        ("   ", False),
        ("!!!", False),
        ("é", True),
    ],
)
def test_is_none_or_has_text(value: str | None, expected: bool) -> None:
    assert is_none_or_has_text(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, False),
        ("abc", True),
        ("", False),
        ("   ", False),
        ("###", False),
        ("é", True),
    ],
)
def test_is_not_none_and_has_text(value: str | None, expected: bool) -> None:
    assert is_not_none_and_has_text(value) is expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("abc", True),
        (0, False),
        ([], False),
        ([1], True),
        ("", False),
        (BadStr(), False),
    ],
)
def test_can_inject_text(value: object, expected: bool) -> None:
    assert can_inject_text(value) is expected


@pytest.mark.parametrize(
    "camel, expected",
    [
        ("thisIsATest", "this_is_a_test"),
        ("HTTPRequest", "http_request"),
        ("myURLParser", "my_url_parser"),
        ("already_snake", "already_snake"),
    ],
)
def test_camel_to_snake_case(camel: str, expected: str) -> None:
    assert camel_to_snake_case(camel) == expected


@pytest.mark.parametrize(
    "pascal, expected",
    [
        ("ThisIsATest", "this_is_a_test"),
        ("HTTPRequest", "http_request"),
        ("ParseJSONData", "parse_json_data"),
    ],
)
def test_pascal_case_to_snake_case(pascal: str, expected: str) -> None:
    assert pascal_case_to_snake_case(pascal) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("HelloWorld", "Hello world"),
        ("BOB LowKey", "Bob low key"),
        ("ParseJSONData", "Parse json data"),
        ("ACDPService", "Acdp service"),
        ("JSON2XMLConverter", "Json 2 xml converter"),
    ],
)
def test_pascal_case_to_sentence(text: str, expected: str) -> None:
    assert pascal_case_to_sentence(text) == expected


@pytest.mark.parametrize(
    "snake, expected",
    [
        ("hello_world", "HelloWorld"),
        ("my_name_is", "MyNameIs"),
        ("a", "A"),
        ("", ""),
    ],
)
def test_snake_to_pascal_case(snake: str, expected: str) -> None:
    assert snake_to_pascal_case(snake) == expected


@pytest.mark.parametrize(
    "snake, expected",
    [
        ("hello_world", "Hello world"),
        ("this_is_a_test", "This is a test"),
        ("HELLO_WORLD", "Hello world"),
        ("abc", "Abc"),
    ],
)
def test_snake_to_capitalize_first_letter(snake: str, expected: str) -> None:
    assert snake_to_capitalize_first_letter(snake) == expected


@pytest.mark.parametrize(
    "word, expected",
    [
        # Valid snake_case
        ("hello", True),
        ("hello_world", True),
        ("my_variable_name", True),
        ("test123", True),
        ("test_123", True),
        ("a", True),
        ("abc123def", True),
        ("snake_case_with_numbers_123", True),
        # Invalid snake_case
        ("Hello", False),  # Starts with uppercase
        ("HelloWorld", False),  # PascalCase
        ("helloWorld", False),  # camelCase
        ("_hello", False),  # Starts with underscore
        ("123hello", False),  # Starts with number
        ("", False),  # Empty string
        ("hello-world", False),  # Contains hyphen
        ("hello world", False),  # Contains space
        ("hello.world", False),  # Contains dot
        ("HELLO_WORLD", False),  # All uppercase
        ("Hello_World", False),  # Mixed case
        ("hello_World", False),  # Mixed case
        ("hello__world", True),  # Double underscore (valid)
        ("hello_", True),  # Ends with underscore (valid)
    ],
)
def test_is_snake_case(word: str, expected: bool) -> None:
    assert is_snake_case(word) is expected


@pytest.mark.parametrize(
    "word, expected",
    [
        # Valid PascalCase
        ("Hello", True),
        ("HelloWorld", True),
        ("MyVariableName", True),
        ("Test123", True),
        ("A", True),
        ("ABC", True),
        ("TestWithNumbers123", True),
        ("HTTPRequest", True),
        ("ParseJSONData", True),
        ("XMLParser", True),
        # Invalid PascalCase
        ("hello", False),  # Starts with lowercase
        ("helloWorld", False),  # camelCase
        ("hello_world", False),  # snake_case
        ("_Hello", False),  # Starts with underscore
        ("123Hello", False),  # Starts with number
        ("", False),  # Empty string
        ("Hello-World", False),  # Contains hyphen
        ("Hello World", False),  # Contains space
        ("Hello.World", False),  # Contains dot
        ("Hello_World", False),  # Contains underscore
        ("HELLO_WORLD", False),  # Contains underscore
        ("Hello$World", False),  # Contains special character
        ("Hello@World", False),  # Contains special character
    ],
)
def test_is_pascal_case(word: str, expected: bool) -> None:
    assert is_pascal_case(word) is expected
