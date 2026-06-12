from typing import Any

import pytest
import tomlkit
from tomlkit import TOMLDocument

from pipelex.tools.misc.toml_sync import collect_leaf_key_paths, get_nested_value

NESTED_TOML_CONTENT = """title = "hello"

[section]
key = 42

[section.sub]
deep = "x"
"""


def make_doc(doc_kind: str) -> TOMLDocument | dict[str, Any]:
    """Build the same nested structure as a tomlkit document or a plain dict."""
    if doc_kind == "tomlkit":
        return tomlkit.parse(NESTED_TOML_CONTENT)
    return {"title": "hello", "section": {"key": 42, "sub": {"deep": "x"}}}


class TestTomlSyncNestedAccess:
    @pytest.mark.parametrize("doc_kind", ["tomlkit", "plain_dict"])
    @pytest.mark.parametrize(
        ("key_path", "expected_value"),
        [
            ("title", "hello"),
            ("section.key", 42),
            ("section.sub.deep", "x"),
        ],
    )
    def test_get_nested_value_found(self, doc_kind: str, key_path: str, expected_value: Any) -> None:
        """Existing top-level, 2-deep and 3-deep dotted paths are found with the right value."""
        doc = make_doc(doc_kind)
        found, value = get_nested_value(doc, key_path)
        assert found is True
        assert value == expected_value

    @pytest.mark.parametrize("doc_kind", ["tomlkit", "plain_dict"])
    @pytest.mark.parametrize(
        "key_path",
        [
            "missing",
            "section.missing",
            "absent_table.key",
            "title.sub",
            "section.key.sub",
        ],
    )
    def test_get_nested_value_not_found(self, doc_kind: str, key_path: str) -> None:
        """Missing leaves, missing intermediate tables and traversal through scalars all yield (False, None)."""
        doc = make_doc(doc_kind)
        found, value = get_nested_value(doc, key_path)
        assert found is False
        assert value is None

    def test_collect_leaf_key_paths_flat_doc(self) -> None:
        """A flat document yields its top-level keys as leaf paths."""
        doc = tomlkit.parse('alpha = 1\nbeta = "two"\ngamma = true\n')
        assert collect_leaf_key_paths(doc) == ["alpha", "beta", "gamma"]

    def test_collect_leaf_key_paths_nested_tables(self) -> None:
        """Nested [section.sub] tables produce dotted leaf paths."""
        doc = tomlkit.parse(NESTED_TOML_CONTENT)
        assert collect_leaf_key_paths(doc) == ["title", "section.key", "section.sub.deep"]

    def test_collect_leaf_key_paths_empty_doc(self) -> None:
        """An empty document has no leaf paths."""
        doc = tomlkit.parse("")
        assert collect_leaf_key_paths(doc) == []

    def test_collect_leaf_key_paths_array_is_single_leaf(self) -> None:
        """A plain array value is a single leaf, not recursed into."""
        doc = tomlkit.parse("nums = [1, 2, 3]\n")
        assert collect_leaf_key_paths(doc) == ["nums"]

    def test_collect_leaf_key_paths_aot_is_single_leaf(self) -> None:
        """An [[array-of-tables]] is not a dict so the whole array is one leaf (synced wholesale)."""
        doc = tomlkit.parse('[[servers]]\nname = "one"\n\n[[servers]]\nname = "two"\n')
        assert collect_leaf_key_paths(doc) == ["servers"]

    def test_collect_leaf_key_paths_inline_table_recurses(self) -> None:
        """An inline table is a dict subclass so its keys become dotted leaf paths."""
        doc = tomlkit.parse('inline = {alpha = 1, beta = "two"}\n')
        assert collect_leaf_key_paths(doc) == ["inline.alpha", "inline.beta"]
