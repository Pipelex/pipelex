from typing import Any

from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.tools.misc.dict_utils import apply_to_strings_in_list, apply_to_strings_recursive, insert_before


class TestDictUtils:
    def test_insert_before_basic(self) -> None:
        """Test basic insert_before functionality."""
        original = {"a": 1, "c": 3}
        result = insert_before(original, "c", "b", 2)

        expected_keys = ["a", "b", "c"]
        assert list(result.keys()) == expected_keys
        assert result["a"] == 1
        assert result["b"] == 2
        assert result["c"] == 3
        assert original != result  # Should return new dict, not modify original

    def test_insert_before_target_not_found(self) -> None:
        """Test insert_before when target key doesn't exist."""
        original = {"a": 1, "b": 2}
        result = insert_before(original, "z", "c", 3)

        expected_keys = ["a", "b", "c"]
        assert list(result.keys()) == expected_keys
        assert result["c"] == 3

    def test_preserve_original_dict(self) -> None:
        """Test that original dictionary is not modified."""
        original = {"a": 1, "b": 2, "c": 3}
        original_copy = original.copy()

        insert_before(original, "b", "x", 999)

        assert original == original_copy

    def test_complex_nested_structure(self) -> None:
        """Test with complex nested dictionary structure."""
        original = {"type": "PipeLLM", "definition": "Test pipe", "output": NativeConceptEnum.TEXT, "system_prompt": "Test prompt"}

        # Insert inputs before output
        result = insert_before(original, "output", "inputs", "InputText")

        expected_keys = ["type", "definition", "inputs", "output", "system_prompt"]
        assert list(result.keys()) == expected_keys
        assert result["inputs"] == "InputText"

    def test_apply_to_strings_recursive_simple_dict(self) -> None:
        """Test apply_to_strings_recursive with a simple dictionary."""
        data = {"name": "Hello ${USER}", "age": 25, "active": True}

        def uppercase_transform(s: str) -> str:
            return s.upper()

        result = apply_to_strings_recursive(data, uppercase_transform)

        assert result["name"] == "HELLO ${USER}"
        assert result["age"] == 25  # Non-string values unchanged
        assert result["active"] is True  # Non-string values unchanged

    def test_apply_to_strings_recursive_nested_dict(self) -> None:
        """Test apply_to_strings_recursive with nested dictionaries."""
        data = {"user": {"name": "john ${SUFFIX}", "settings": {"theme": "dark ${MODE}", "count": 10}}, "version": "1.0 ${BUILD}"}

        def env_substitute(s: str) -> str:
            return s.replace("${SUFFIX}", "_doe").replace("${MODE}", "_theme").replace("${BUILD}", "_final")

        result = apply_to_strings_recursive(data, env_substitute)

        assert result["user"]["name"] == "john _doe"
        assert result["user"]["settings"]["theme"] == "dark _theme"
        assert result["user"]["settings"]["count"] == 10
        assert result["version"] == "1.0 _final"

    def test_apply_to_strings_recursive_with_lists(self) -> None:
        """Test apply_to_strings_recursive with lists containing various types."""
        data = {"items": ["hello ${WORLD}", 42, "goodbye ${WORLD}"], "config": {"values": [1, "test ${ENV}", True, {"nested": "value ${VAR}"}]}}

        def substitute_vars(s: str) -> str:
            return s.replace("${WORLD}", "earth").replace("${ENV}", "production").replace("${VAR}", "123")

        result = apply_to_strings_recursive(data, substitute_vars)

        assert result["items"] == ["hello earth", 42, "goodbye earth"]
        assert result["config"]["values"][0] == 1
        assert result["config"]["values"][1] == "test production"
        assert result["config"]["values"][2] is True
        assert result["config"]["values"][3]["nested"] == "value 123"

    def test_apply_to_strings_recursive_empty_structures(self) -> None:
        """Test apply_to_strings_recursive with empty dictionaries and lists."""
        data: dict[str, Any] = {"empty_dict": {}, "empty_list": [], "mixed": {"inner_empty": {}, "inner_list": []}}

        def dummy_transform(s: str) -> str:
            return s.upper()

        result = apply_to_strings_recursive(data, dummy_transform)

        assert result["empty_dict"] == {}
        assert result["empty_list"] == []
        assert result["mixed"]["inner_empty"] == {}
        assert result["mixed"]["inner_list"] == []

    def test_apply_to_strings_recursive_preserves_original(self) -> None:
        """Test that apply_to_strings_recursive doesn't modify the original data."""
        original = {"text": "hello ${USER}", "nested": {"value": "world ${ENV}"}, "list": ["item ${VAR}"]}
        original_copy = {"text": "hello ${USER}", "nested": {"value": "world ${ENV}"}, "list": ["item ${VAR}"]}

        def transform(s: str) -> str:
            return s.replace("${USER}", "john").replace("${ENV}", "prod").replace("${VAR}", "test")

        result = apply_to_strings_recursive(original, transform)

        # Original should be unchanged
        assert original == original_copy

        # Result should be transformed
        assert result["text"] == "hello john"
        assert result["nested"]["value"] == "world prod"
        assert result["list"] == ["item test"]

    def test_apply_to_strings_in_list_basic(self) -> None:
        """Test apply_to_strings_in_list with basic string transformations."""
        data = ["hello ${USER}", "world", 42, True, "test ${ENV}"]

        def substitute_vars(s: str) -> str:
            return s.replace("${USER}", "john").replace("${ENV}", "production")

        result = apply_to_strings_in_list(data, substitute_vars)

        assert result == ["hello john", "world", 42, True, "test production"]
        assert result is not data  # Should return a new list

    def test_apply_to_strings_in_list_nested_lists(self) -> None:
        """Test apply_to_strings_in_list with nested lists."""
        data = ["outer ${VAR}", [1, "inner ${NESTED}", ["deep ${DEEP}", 3.14]], "final ${END}"]

        def transform(s: str) -> str:
            return s.replace("${VAR}", "variable").replace("${NESTED}", "nested").replace("${DEEP}", "deep").replace("${END}", "end")

        result = apply_to_strings_in_list(data, transform)

        assert result[0] == "outer variable"
        assert result[1][0] == 1
        assert result[1][1] == "inner nested"
        assert result[1][2][0] == "deep deep"
        assert result[1][2][1] == 3.14
        assert result[2] == "final end"

    def test_apply_to_strings_in_list_with_dictionaries(self) -> None:
        """Test apply_to_strings_in_list with dictionaries in the list."""
        data = ["list item ${VAR}", {"key1": "dict value ${DICT}", "key2": 100}, 42, {"nested": {"deep": "deep value ${DEEP}"}}, "another ${ITEM}"]

        def transform(s: str) -> str:
            return s.replace("${VAR}", "var").replace("${DICT}", "dict").replace("${DEEP}", "deep").replace("${ITEM}", "item")

        result = apply_to_strings_in_list(data, transform)

        assert result[0] == "list item var"
        assert result[1]["key1"] == "dict value dict"
        assert result[1]["key2"] == 100
        assert result[2] == 42
        assert result[3]["nested"]["deep"] == "deep value deep"
        assert result[4] == "another item"

    def test_apply_to_strings_in_list_empty_list(self) -> None:
        """Test apply_to_strings_in_list with empty list."""
        data: Any = []

        def dummy_transform(s: str) -> str:
            return s.upper()

        result = apply_to_strings_in_list(data, dummy_transform)

        assert result == []
        assert result is not data  # Should return a new list

    def test_apply_to_strings_in_list_no_strings(self) -> None:
        """Test apply_to_strings_in_list with list containing no strings."""
        data = [1, 2.5, True, None, {"key": "value"}, [1, 2, 3]]

        def transform(s: str) -> str:
            return s.upper()

        result = apply_to_strings_in_list(data, transform)

        assert result[0] == 1
        assert result[1] == 2.5
        assert result[2] is True
        assert result[3] is None
        assert result[4] == {"key": "VALUE"}  # Dict should be transformed by apply_to_strings_recursive
        assert result[5] == [1, 2, 3]  # Nested list with no strings

    def test_apply_to_strings_in_list_preserves_original(self) -> None:
        """Test that apply_to_strings_in_list doesn't modify the original list."""
        original = ["hello ${USER}", {"key": "value ${VAR}"}, ["nested ${NESTED}"]]
        original_copy = ["hello ${USER}", {"key": "value ${VAR}"}, ["nested ${NESTED}"]]

        def transform(s: str) -> str:
            return s.replace("${USER}", "john").replace("${VAR}", "variable").replace("${NESTED}", "nested")

        result = apply_to_strings_in_list(original, transform)

        # Original should be unchanged
        assert original == original_copy

        # Result should be transformed
        assert result[0] == "hello john"
        assert result[1]["key"] == "value variable"
        assert result[2][0] == "nested nested"

    def test_apply_to_strings_in_list_complex_nesting(self) -> None:
        """Test apply_to_strings_in_list with complex nested structures."""
        data = [
            "root ${ROOT}",
            {"dict_key": "dict value ${DICT}", "nested_list": ["nested item ${NESTED}", {"deep": "deep value ${DEEP}"}], "number": 42},
            ["list in list ${LIST}", [{"very_deep": "very deep value ${VERY_DEEP}"}, "deep list item ${DEEP_LIST}"]],
        ]

        def transform(s: str) -> str:
            replacements = {
                "${ROOT}": "root",
                "${DICT}": "dict",
                "${NESTED}": "nested",
                "${DEEP}": "deep",
                "${LIST}": "list",
                "${VERY_DEEP}": "very_deep",
                "${DEEP_LIST}": "deep_list",
            }
            result = s
            for old, new in replacements.items():
                result = result.replace(old, new)
            return result

        result = apply_to_strings_in_list(data, transform)

        assert result[0] == "root root"
        assert result[1]["dict_key"] == "dict value dict"
        assert result[1]["nested_list"][0] == "nested item nested"
        assert result[1]["nested_list"][1]["deep"] == "deep value deep"
        assert result[1]["number"] == 42
        assert result[2][0] == "list in list list"
        assert result[2][1][0]["very_deep"] == "very deep value very_deep"
        assert result[2][1][1] == "deep list item deep_list"
