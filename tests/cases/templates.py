"""Template constants for testing."""

from typing import Any, ClassVar

from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat

from .registry import Fruit


class JINJA2TestCases:
    """Jinja2 template test constants."""

    # Template names
    JINJA2_NAME: ClassVar[list[str]] = [
        "jinja2_test_template",
    ]

    # Basic templates
    JINJA2_FOR_ANY: ClassVar[list[str]] = [
        "I want a {{ place_holder }} cocktail.",
    ]

    # Filter templates
    JINJA2_FILTER_TAG = """
Tag filter:
{{ place_holder | tag("some stuff") }}
"""

    JINJA2_FILTER_FORMAT = """
Format filter:
{{ place_holder | format }}
"""

    JINJA2_FILTER_FORMAT_PLAIN = """
Format filter plain:
{{ place_holder | format("plain") }}
"""

    JINJA2_FILTER_FORMAT_JSON = """
Format filter json:
{{ place_holder | format("json") }}
"""

    JINJA2_FILTER_FORMAT_MARKDOWN = """
Format filter markdown:
{{ place_holder | format("markdown") }}
"""

    JINJA2_FILTER_FORMAT_HTML = """
Format filter html:
{{ place_holder | format("html") }}
"""

    JINJA2_FILTER_FORMAT_SPREADSHEET = """
Format filter spreadsheet:
{{ place_holder | format("spreadsheet") }}
"""

    JINJA2_ALL_METHODS = """
Direct (no filter):
{{ place_holder }}

Format filter:
{{ place_holder | format }}

Tag filter:
{{ place_holder | tag("some stuff") }}

Format filter json:
{{ place_holder | format("json") }}

Format filter markdown:
{{ place_holder | format("markdown") }}

Format filter html:
{{ place_holder | format("html") }}

"""

    # Template collections
    JINJA2_FOR_STUFF: ClassVar[list[str]] = [
        JINJA2_FILTER_TAG,
        JINJA2_FILTER_FORMAT,
        JINJA2_FILTER_FORMAT_PLAIN,
        JINJA2_FILTER_FORMAT_JSON,
        JINJA2_FILTER_FORMAT_MARKDOWN,
        JINJA2_FILTER_FORMAT_HTML,
        JINJA2_FILTER_FORMAT_SPREADSHEET,
        JINJA2_ALL_METHODS,
    ]

    # Style configurations
    STYLE: ClassVar[list[PromptingStyle]] = [
        PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        ),
        PromptingStyle(
            tag_style=TagStyle.TICKS,
            text_format=TextFormat.MARKDOWN,
        ),
        PromptingStyle(
            tag_style=TagStyle.XML,
            text_format=TextFormat.HTML,
        ),
        PromptingStyle(
            tag_style=TagStyle.SQUARE_BRACKETS,
            text_format=TextFormat.JSON,
        ),
    ]

    # Test data
    COLOR: ClassVar[list[str]] = [
        "red",
        "blue",
        "green",
    ]

    FRUIT: ClassVar[list[Fruit]] = [
        Fruit(color="red", name="cherry"),
        Fruit(color="blue", name="blueberry"),
        Fruit(color="green", name="grape"),
    ]

    # Mixed object types for comprehensive testing
    ANY_OBJECT: ClassVar[list[tuple[str, Any]]] = [  # topic, any_object
        ("string", "test_string"),
        ("integer", 42),
        ("float", 3.14),
        ("boolean", True),
        ("list", ["item1", "item2", "item3"]),
        ("dict", {"key1": "value1", "key2": "value2"}),
        ("fruit_object", Fruit(color="red", name="apple")),
    ]
