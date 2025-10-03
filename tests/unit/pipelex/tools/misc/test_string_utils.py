import pytest

from pipelex.tools.misc.string_utils import (
    camel_to_snake_case,
    can_inject_text,
    is_none_or_has_text,
    is_not_none_and_has_text,
    is_pascal_case,
    is_snake_case,
    matches_wildcard_pattern,
    normalize_to_ascii,
    pascal_case_to_sentence,
    pascal_case_to_snake_case,
    snake_to_capitalize_first_letter,
    snake_to_pascal_case,
)


class BadStr:
    def __str__(self) -> str:  # pyright: ignore[reportImplicitOverride] pragma: no cover - used only for raising
        msg = "boom"
        raise RuntimeError(msg)


@pytest.mark.parametrize(
    ("value", "expected"),
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
    ("value", "expected"),
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
    ("value", "expected"),
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
    ("camel", "expected"),
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
    ("pascal", "expected"),
    [
        ("ThisIsATest", "this_is_a_test"),
        ("HTTPRequest", "http_request"),
        ("ParseJSONData", "parse_json_data"),
    ],
)
def test_pascal_case_to_snake_case(pascal: str, expected: str) -> None:
    assert pascal_case_to_snake_case(pascal) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
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
    ("snake", "expected"),
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
    ("snake", "expected"),
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
    ("word", "expected"),
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
    ("word", "expected"),
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # ASCII strings (should remain unchanged)
        ("Hello", "Hello"),
        ("HelloWorld", "HelloWorld"),
        ("hello_world", "hello_world"),
        ("Test123", "Test123"),
        ("my_variable_name", "my_variable_name"),
        ("", ""),
        # Accented characters (should be normalized)
        ("Café", "Cafe"),
        ("Naïve", "Naive"),
        ("résumé", "resume"),
        ("Über", "Uber"),
        ("crème_brûlée", "creme_brulee"),
        # Cyrillic lookalikes (should be removed)
        ("OppositeСoncept", "Oppositeoncept"),  # Cyrillic С (U+0421) removed, leaving Latin letters
        ("HelloМorld", "Helloorld"),  # Cyrillic М (U+041C) removed
        ("Concept_Идея", "Concept_"),  # Cyrillic letters removed
        # Greek lookalikes (should be removed)
        ("HelloΩorld", "Helloorld"),  # Greek Ω removed
        # Mixed scenarios
        ("Hëllo_Wörld123", "Hello_World123"),
        ("Test_Café_Naïve", "Test_Cafe_Naive"),
        # Special characters (should be removed, except underscores)
        ("Hello-World", "HelloWorld"),
        ("Hello World", "HelloWorld"),
        ("Hello.World", "HelloWorld"),
        ("Hello@World", "HelloWorld"),
        ("Hello$World", "HelloWorld"),
        ("Hello_World", "Hello_World"),  # Underscores are kept
        # Numbers
        ("123Test", "123Test"),
        # Edge cases
        ("_", "_"),
        ("___", "___"),
        ("123", "123"),
        ("абвгд", ""),  # All Cyrillic, all removed
        ("αβγδε", ""),  # All Greek, all removed
        ("café_résumé_123", "cafe_resume_123"),
    ],
)
def test_normalize_to_ascii(text: str, expected: str) -> None:
    assert normalize_to_ascii(text) == expected


class TestMatchesWildcardPattern:
    """Test class for the matches_wildcard_pattern function."""

    @pytest.mark.parametrize(
        ("text", "pattern", "expected"),
        [
            # Universal wildcard
            ("any-text", "*", True),
            ("", "*", True),
            ("claude-3-sonnet", "*", True),
            # Exact matches
            ("claude-3-sonnet", "claude-3-sonnet", True),
            ("gpt-4o-mini", "gpt-4o-mini", True),
            ("mistral-large", "mistral-large", True),
            ("exact-match", "different-text", False),
            ("", "", True),
            # Prefix wildcards (pattern ends with *)
            ("claude-3-sonnet", "claude-*", True),
            ("claude-3-haiku", "claude-*", True),
            ("gpt-4o-mini", "claude-*", False),
            ("claude", "claude-*", False),  # No dash after claude
            ("my-claude-model", "claude-*", False),  # claude not at start
            ("", "prefix-*", False),
            ("prefix", "prefix-*", False),  # No content after prefix
            ("prefix-something", "prefix-*", True),
            # Suffix wildcards (pattern starts with *)
            ("gpt-4o-mini", "*mini", True),
            ("claude-3-sonnet-mini", "*mini", True),
            ("mistral-large", "*large", True),
            ("mini-gpt", "*mini", False),  # mini not at end
            ("large-mistral", "*large", False),  # large not at end
            ("", "*suffix", False),
            ("suffix", "*suffix", True),
            ("my-suffix", "*suffix", True),
            ("suffixnot", "*suffix", False),
            # Contains wildcards (pattern starts and ends with *)
            ("claude-3-sonnet", "*sonnet*", True),
            ("my-sonnet-model", "*sonnet*", True),
            ("sonnet-based", "*sonnet*", True),
            ("sonnet", "*sonnet*", True),
            ("gpt-4o-mini", "*sonnet*", False),
            ("", "*middle*", False),
            ("middle", "*middle*", True),
            ("before-middle-after", "*middle*", True),
            ("middlepart", "*middle*", True),
            ("partmiddle", "*middle*", True),
            # Edge cases with empty middle pattern
            ("any-text", "**", True),  # Empty middle matches anything
            ("", "**", True),
            # Case sensitivity
            ("Claude-3-Sonnet", "claude-*", False),  # Case sensitive
            ("CLAUDE-3-SONNET", "*sonnet*", False),  # Case sensitive
            ("gpt-4O-MINI", "*mini", False),  # Case sensitive
            # Special characters in text and patterns
            ("model-v1.2", "model-*", True),
            ("my_model_name", "*_model_*", True),
            ("api.v2.endpoint", "api.*", True),
            ("test@domain.com", "*@*", True),
            ("file-name.ext", "*-name.*", True),
            # Multiple wildcards (only first and last are treated as wildcards)
            ("a-b-c-d", "*-b-*", True),  # Treated as contains pattern
            ("a*b*c", "*b*", True),  # Asterisks in text are literal
        ],
    )
    def test_matches_wildcard_pattern(self, text: str, pattern: str, expected: bool) -> None:
        assert matches_wildcard_pattern(text, pattern) is expected

    def test_matches_wildcard_pattern_model_routing_examples(self) -> None:
        """Test with real-world model routing examples."""
        # Claude models
        assert matches_wildcard_pattern("claude-3-sonnet", "claude-*") is True
        assert matches_wildcard_pattern("claude-3-haiku", "claude-*") is True
        assert matches_wildcard_pattern("claude-3.5-sonnet", "claude-*") is True

        # GPT models
        assert matches_wildcard_pattern("gpt-4o-mini", "gpt-*") is True
        assert matches_wildcard_pattern("gpt-4", "gpt-*") is True
        assert matches_wildcard_pattern("gpt-3.5-turbo", "gpt-*") is True

        # Mistral models
        assert matches_wildcard_pattern("mistral-large", "*large") is True
        assert matches_wildcard_pattern("mistral-medium", "*medium") is True
        assert matches_wildcard_pattern("mistral-small", "*small") is True

        # Contains patterns
        assert matches_wildcard_pattern("claude-3-sonnet", "*sonnet*") is True
        assert matches_wildcard_pattern("gpt-4o-mini", "*4o*") is True
        assert matches_wildcard_pattern("mistral-large-instruct", "*large*") is True

        # Negative cases
        assert matches_wildcard_pattern("gemini-pro", "claude-*") is False
        assert matches_wildcard_pattern("llama-2", "*gpt*") is False
        assert matches_wildcard_pattern("anthropic-claude", "*sonnet") is False
