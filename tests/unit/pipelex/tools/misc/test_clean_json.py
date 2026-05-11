from typing import Any

import pytest

from pipelex.tools.misc.json_utils import clean_json_content


class TestCleanJsonContent:
    """Strip-set behaviour of clean_json_content for both marker families.

    User-facing JSON output should never carry either kajson's __class__/__module__
    pair (from upstream encoder rehydration) or pipelex's __pipelex_class__/
    __pipelex_module__ pair (from dehydrated working_memory payloads).
    """

    @pytest.mark.parametrize(
        "marker_pair",
        [
            ("__class__", "__module__"),
            ("__pipelex_class__", "__pipelex_module__"),
        ],
        ids=["kajson_markers", "pipelex_markers"],
    )
    def test_strips_marker_pair_at_all_depths(self, marker_pair: tuple[str, str]) -> None:
        class_key, module_key = marker_pair
        nested: dict[str, Any] = {
            "outer_field": "keep",
            class_key: "SomeClass",
            module_key: "some.module",
            "inner": {
                "leaf": 42,
                class_key: "Inner",
                module_key: "some.module.inner",
            },
            "list_field": [
                {"item": 1, class_key: "Item", module_key: "x.y"},
                {"item": 2, class_key: "Item", module_key: "x.y"},
            ],
        }

        cleaned = clean_json_content(nested)

        assert class_key not in cleaned
        assert module_key not in cleaned
        assert class_key not in cleaned["inner"]
        assert module_key not in cleaned["inner"]
        for list_item in cleaned["list_field"]:
            assert class_key not in list_item
            assert module_key not in list_item

        assert cleaned["outer_field"] == "keep"
        assert cleaned["inner"]["leaf"] == 42
        assert cleaned["list_field"][0]["item"] == 1
        assert cleaned["list_field"][1]["item"] == 2
