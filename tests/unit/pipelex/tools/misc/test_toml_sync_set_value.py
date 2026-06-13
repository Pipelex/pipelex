from typing import Any

import pytest
import tomlkit
from tomlkit import TOMLDocument

from pipelex.tools.misc.toml_sync import set_nested_value


def dump_doc(doc: TOMLDocument) -> str:
    """Serialize a tomlkit document back to TOML text."""
    return tomlkit.dumps(doc)  # pyright: ignore[reportUnknownMemberType]


NESTED_TOML_CONTENT = """title = "hello"

[section]
key = 42

[section.sub]
deep = "x"
"""


class TestTomlSyncSetValue:
    @pytest.mark.parametrize(
        ("key_path", "new_value"),
        [
            ("title", "world"),
            ("section.key", 99),
            ("section.sub.deep", "y"),
        ],
    )
    def test_set_existing_key(self, key_path: str, new_value: str | int) -> None:
        """Setting an existing top-level or nested key returns True and changes the value in the doc."""
        doc = tomlkit.parse(NESTED_TOML_CONTENT)
        result = set_nested_value(doc, key_path, new_value)
        assert result is True
        current: Any = doc
        for key in key_path.split("."):
            current = current[key]
        assert current == new_value

    @pytest.mark.parametrize(
        "key_path",
        [
            "brand_new",
            "section.brand_new",
            "absent_table.key",
            "title.sub",
            "title.sub.deeper",
            "section.key.sub",
        ],
    )
    def test_missing_key_returns_false_and_doc_untouched(self, key_path: str) -> None:
        """Missing final key, missing intermediate table or traversal through a scalar returns False and never creates the key."""
        doc = tomlkit.parse(NESTED_TOML_CONTENT)
        result = set_nested_value(doc, key_path, "intruder")
        assert result is False
        assert dump_doc(doc) == NESTED_TOML_CONTENT

    def test_set_value_preserves_inline_comment(self) -> None:
        """Replacing a value keeps the existing inline comment via trivia restoration."""
        doc = tomlkit.parse("timeout = 30  # seconds\n")
        result = set_nested_value(doc, "timeout", 60)
        assert result is True
        assert dump_doc(doc) == "timeout = 60  # seconds\n"

    def test_set_value_preserves_inline_comment_on_nested_key(self) -> None:
        """Trivia restoration also applies to keys inside a [section] table."""
        doc = tomlkit.parse('[section]\nname = "old"  # keep me\n')
        result = set_nested_value(doc, "section.name", "new")
        assert result is True
        assert dump_doc(doc) == '[section]\nname = "new"  # keep me\n'
