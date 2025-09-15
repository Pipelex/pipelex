"""Unit tests for dict_utils module."""

from typing import Any, Dict

from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.tools.misc.dict_utils import apply_to_strings_recursive, insert_before


class TestDictUtils:
    """Test class for dict_utils functions."""

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
        original = {"type": "PipeLLM", "definition": "Test pipe", "output": NativeConceptEnum.TEXT.value, "system_prompt": "Test prompt"}

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
        data: Dict[str, Any] = {"empty_dict": {}, "empty_list": [], "mixed": {"inner_empty": {}, "inner_list": []}}

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
